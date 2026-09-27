"""Tests for the Workspace class in adjourn.tools."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from adjourn.config import Config
from adjourn.tools import Workspace
from tests.helpers import NONEMPTY_RULESET, write_config


def _write_session_state(sessions_dir: Path, session: str) -> Path:
    """Write a minimal running state file for *session* and return its path."""
    sessions_dir.mkdir(parents=True, exist_ok=True)
    state_path = sessions_dir / f"{session}.json"
    state_path.write_text(
        json.dumps(
            {
                "version": 0,
                "original_goal": "true",
                "branches": [{"orig_goal": "true", "goals": ["true"]}],
                "status": "running",
                "ruleset_hash": "a" * 64,
                "resume_hash": "a" * 64,
            }
        )
    )
    return state_path


class TestWorkspaceConstruction:
    """Tests for Workspace construction and configuration."""

    def test_config_path_is_resolved(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A relative config path should be stored as an absolute path."""
        monkeypatch.chdir(tmp_path)
        ws = Workspace(".adjourn/config.yaml")
        assert ws.config_path == (tmp_path / ".adjourn" / "config.yaml").resolve()
        assert ws.config_path.is_absolute()

    def test_default_sessions_dir_is_config_relative(self, tmp_path: Path) -> None:
        """The default sessions dir should sit next to the config file."""
        config_path = tmp_path / ".adjourn" / "config.yaml"
        ws = Workspace(config_path)
        assert ws.sessions_dir == config_path.parent / "mcp-sessions"

    def test_explicit_sessions_dir_used_as_given(self, tmp_path: Path) -> None:
        """An explicit sessions dir should be stored as given, not resolved."""
        config_path = tmp_path / ".adjourn" / "config.yaml"
        ws = Workspace(config_path, sessions_dir="sessions")
        assert ws.sessions_dir == Path("sessions")
        assert not ws.sessions_dir.is_absolute()

    def test_sessions_dir_can_be_reassigned(self, tmp_path: Path) -> None:
        """Reassigning sessions_dir should be honoured by _session_path."""
        config_path = tmp_path / ".adjourn" / "config.yaml"
        ws = Workspace(config_path, sessions_dir=tmp_path / "sessions")
        new_dir = tmp_path / "other-sessions"
        ws.sessions_dir = new_dir
        path = ws._session_path("abc123")
        assert path.parent == new_dir
        assert path.name == "abc123.json"

    def test_constructor_does_not_create_sessions_dir(self, tmp_path: Path) -> None:
        """The constructor should not touch the filesystem."""
        config_path = tmp_path / ".adjourn" / "config.yaml"
        sessions_dir = tmp_path / "sessions"
        ws = Workspace(config_path, sessions_dir=sessions_dir)
        assert not sessions_dir.exists()
        assert ws._sessions_dir() == sessions_dir
        assert sessions_dir.exists()

    def test_server_dir_is_config_parent_parent(self, tmp_path: Path) -> None:
        """server_dir should be the directory that contains .adjourn."""
        config_path = tmp_path / ".adjourn" / "config.yaml"
        ws = Workspace(config_path)
        assert ws.server_dir == tmp_path

    def test_from_env_with_sessions_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """from_env should read ADJOURN_MCP_SESSIONS_DIR when set."""
        config_path = tmp_path / ".adjourn" / "config.yaml"
        sessions_dir = tmp_path / "sessions"
        monkeypatch.setenv("ADJOURN_CONFIG", str(config_path))
        monkeypatch.setenv("ADJOURN_MCP_SESSIONS_DIR", str(sessions_dir))
        monkeypatch.setenv("ADJOURN_MCP_TIMEOUT", "42")
        ws = Workspace.from_env()
        assert ws.config_path == config_path.resolve()
        assert ws.sessions_dir == sessions_dir
        assert ws.timeout == 42

    def test_from_env_without_sessions_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """from_env should fall back to the config-relative sessions dir."""
        config_path = tmp_path / ".adjourn" / "config.yaml"
        monkeypatch.setenv("ADJOURN_CONFIG", str(config_path))
        monkeypatch.delenv("ADJOURN_MCP_SESSIONS_DIR", raising=False)
        monkeypatch.delenv("ADJOURN_MCP_TIMEOUT", raising=False)
        ws = Workspace.from_env()
        assert ws.sessions_dir == ws.config_path.parent / "mcp-sessions"
        assert ws.timeout == 60

    def test_from_env_defaults(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """from_env should apply defaults when no env vars are set."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("ADJOURN_CONFIG", raising=False)
        monkeypatch.delenv("ADJOURN_MCP_SESSIONS_DIR", raising=False)
        monkeypatch.delenv("ADJOURN_MCP_TIMEOUT", raising=False)
        ws = Workspace.from_env()
        assert ws.config_path == (tmp_path / ".adjourn" / "config.yaml").resolve()
        assert ws.sessions_dir == ws.config_path.parent / "mcp-sessions"
        assert ws.timeout == 60


class TestWorkspaceSessionHelpers:
    """Tests for the Workspace private helper methods."""

    def test_allocate_session_id(self, tmp_path: Path) -> None:
        """Session ids should be 32-character hex strings."""
        ws = Workspace(tmp_path / ".adjourn" / "config.yaml")
        sid = ws._allocate_session_id()
        assert isinstance(sid, str)
        assert len(sid) == 32
        int(sid, 16)

    def test_session_path(self, tmp_path: Path) -> None:
        """_session_path should be <sessions_dir>/<id>.json."""
        ws = Workspace(tmp_path / ".adjourn" / "config.yaml", sessions_dir=tmp_path / "sessions")
        path = ws._session_path("abc123")
        assert path.name == "abc123.json"
        assert path.parent == ws.sessions_dir

    def test_allocate_rules_filename_is_sequential(self, tmp_path: Path) -> None:
        """rules_NNN allocation should advance from the highest existing number."""
        ws = Workspace(tmp_path / ".adjourn" / "config.yaml")
        assert ws._allocate_rules_filename(tmp_path) == "rules_001.pl"
        (tmp_path / "rules_001.pl").write_text("")
        assert ws._allocate_rules_filename(tmp_path) == "rules_002.pl"
        (tmp_path / "rules_010.pl").write_text("")
        (tmp_path / "rules_003.pl").write_text("")
        assert ws._allocate_rules_filename(tmp_path) == "rules_011.pl"

    def test_write_rules_file_skips_existing_filename(self, tmp_path: Path) -> None:
        """_write_rules_file should create the next free numbered rules file."""
        ws = Workspace(tmp_path / ".adjourn" / "config.yaml")
        existing = tmp_path / "rules_001.pl"
        existing.write_text("rule(existing, true).\n")

        created = ws._write_rules_file(tmp_path, "rule(new_rule, true).\n")

        assert created == "rules_002.pl"
        assert existing.read_text() == "rule(existing, true).\n"
        assert (tmp_path / created).read_text() == "rule(new_rule, true).\n"

    def test_run_cli_raises_on_failure(self, tmp_path: Path) -> None:
        """_run_cli should raise RuntimeError on CLI failure."""
        ws = Workspace(tmp_path / ".adjourn" / "config.yaml")
        with pytest.raises(RuntimeError, match="CLI command failed"):
            ws._run_cli(["init", "true", "/nonexistent/path/state.json", "--format", "json"])


class TestWorkspaceTools:
    """End-to-end tests for the Workspace public methods."""

    def test_init_returns_session_and_projection(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """init should return a session id and a projection with status."""
        config_path = write_config(tmp_path, {"test_rules": NONEMPTY_RULESET})
        monkeypatch.delenv("ADJOURN_CONFIG", raising=False)
        ws = Workspace(config_path, sessions_dir=tmp_path / "sessions")

        result = ws.init("true")

        assert "session" in result
        assert isinstance(result["session"], str)
        assert len(result["session"]) == 32
        assert result["status"] == "running"
        assert "ruleset_hash" in result
        assert "resume_hash" in result
        assert "label" in result
        state_path = tmp_path / "sessions" / f"{result['session']}.json"
        assert state_path.exists()
        state = json.loads(state_path.read_text())
        assert state["status"] == "running"

    def test_resume_drives_to_solution_then_done(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """resume should drive true to solution, then done, and stay done."""
        config_path = write_config(tmp_path, {"test_rules": NONEMPTY_RULESET})
        monkeypatch.delenv("ADJOURN_CONFIG", raising=False)
        ws = Workspace(config_path, sessions_dir=tmp_path / "sessions")

        init_result = ws.init("true")
        session_id = init_result["session"]
        assert init_result["status"] == "running"

        r1 = ws.resume(session_id)
        assert r1["status"] == "solution"

        r2 = ws.resume(session_id)
        assert r2["status"] == "done"

        r3 = ws.resume(session_id)
        assert r3["status"] == "done"

    def test_resume_missing_session_raises(self, tmp_path: Path) -> None:
        """Resuming a non-existent session should raise RuntimeError."""
        ws = Workspace(tmp_path / ".adjourn" / "config.yaml", sessions_dir=tmp_path / "sessions")
        with pytest.raises(RuntimeError, match="Session 'missing' not found"):
            ws.resume("missing")

    def test_add_rules_missing_session_raises(self, tmp_path: Path) -> None:
        """add_rules should mirror resume for missing sessions."""
        ws = Workspace(tmp_path / ".adjourn" / "config.yaml", sessions_dir=tmp_path / "sessions")
        with pytest.raises(RuntimeError, match="Session 'missing' not found"):
            ws.add_rules("missing", "rule(extra_rule, true).\n")

    def test_add_rules_writes_registers_and_resumes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """add_rules should write a numbered file and repoint resume_hash."""
        config_path = write_config(tmp_path, {"test_rules": NONEMPTY_RULESET})
        monkeypatch.delenv("ADJOURN_CONFIG", raising=False)
        ws = Workspace(config_path, sessions_dir=tmp_path / "sessions")

        init_result = ws.init("true")
        session_id = init_result["session"]
        before_resume_hash = init_result["resume_hash"]

        result = ws.add_rules(session_id, "rule(extra_rule, true).\n")

        assert result["session"] == session_id
        assert result["status"] == "solution"
        assert result["resume_hash"] != before_resume_hash

        first_rules_path = tmp_path / "rules_001.pl"
        assert first_rules_path.read_text() == "rule(extra_rule, true).\n"

        config = Config(config_path)
        assert config.store_configs[-1]["path"] == "rules_001.pl"

        state = json.loads((tmp_path / "sessions" / f"{session_id}.json").read_text())
        assert state["resume_hash"] == result["resume_hash"]

        follow_up = ws.resume(session_id)
        assert follow_up["status"] == "done"
        assert follow_up["resume_hash"] == result["resume_hash"]

    def test_add_rules_on_done_session_returns_done(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """add_rules should return done when resuming a done session."""
        config_path = write_config(tmp_path, {"test_rules": NONEMPTY_RULESET})
        monkeypatch.delenv("ADJOURN_CONFIG", raising=False)
        ws = Workspace(config_path, sessions_dir=tmp_path / "sessions")

        init_result = ws.init("true")
        session_id = init_result["session"]
        assert ws.resume(session_id)["status"] == "solution"
        assert ws.resume(session_id)["status"] == "done"

        result = ws.add_rules(session_id, "rule(done_rule, true).\n")

        assert result["session"] == session_id
        assert result["status"] == "done"
        assert (tmp_path / "rules_001.pl").exists()

    def test_add_rules_uses_server_dir_for_all_cli_calls(self, tmp_path: Path) -> None:
        """add_rules should invoke every CLI step from the server directory."""
        sessions_dir = tmp_path / "sessions"
        state_path = _write_session_state(sessions_dir, "session")

        config_path = tmp_path / ".adjourn" / "config.yaml"
        config_path.parent.mkdir()
        config_path.write_text(yaml.safe_dump({"stores": [], "aliases": {}}))

        ws = Workspace(config_path, sessions_dir=sessions_dir)
        calls: list[tuple[list[str], Path | None]] = []

        def fake_run_cli(args: list[str], cwd: Path | None = None) -> dict:
            calls.append((args, cwd))
            return {
                "status": "done",
                "label": None,
                "ruleset_hash": "a" * 64,
                "resume_hash": "b" * 64,
            }

        ws._run_cli = fake_run_cli

        result = ws.add_rules("session", "rule(extra_rule, true).\n")

        assert result["status"] == "done"
        assert [call[0][:2] for call in calls] == [
            ["rules", "add"],
            ["set-resume", "@top"],
            ["resume", str(state_path.resolve())],
        ]
        assert all(cwd == tmp_path for _, cwd in calls)
        assert calls[0][0][2] == "rules_001.pl"

    def test_init_and_resume_pass_config_and_server_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """init and resume should pass --config and run from server_dir.

        A relative sessions dir must still yield absolute state paths, so the
        CLI finds them regardless of the subprocess cwd.
        """
        monkeypatch.chdir(tmp_path)
        config_path = tmp_path / ".adjourn" / "config.yaml"
        ws = Workspace(config_path, sessions_dir="sessions")
        calls: list[tuple[list[str], Path | None]] = []

        def fake_run_cli(args: list[str], cwd: Path | None = None) -> dict:
            calls.append((args, cwd))
            if args[0] == "init":
                Path(args[2]).write_text("{}")
            return {"status": "running", "label": None}

        ws._run_cli = fake_run_cli

        session_id = ws.init("true")["session"]
        ws.resume(session_id)

        state_path = (tmp_path / "sessions" / f"{session_id}.json").resolve()
        assert [c[0][0] for c in calls] == ["init", "resume"]
        for args, cwd in calls:
            assert cwd == ws.server_dir
            assert args[args.index("--config") + 1] == str(ws.config_path)
            assert str(state_path) in args

    def test_add_rules_leaves_written_file_on_cli_failure(self, tmp_path: Path) -> None:
        """add_rules should preserve the new rules file if a CLI step fails."""
        sessions_dir = tmp_path / "sessions"
        _write_session_state(sessions_dir, "session")

        config_path = tmp_path / ".adjourn" / "config.yaml"
        config_path.parent.mkdir()
        config_path.write_text(yaml.safe_dump({"stores": [], "aliases": {}}))

        ws = Workspace(config_path, sessions_dir=sessions_dir)

        def failing_run_cli(args: list[str], cwd: Path | None = None) -> dict:
            del args, cwd
            raise RuntimeError("boom")

        ws._run_cli = failing_run_cli

        with pytest.raises(RuntimeError, match="boom"):
            ws.add_rules("session", "rule(extra_rule, true).\n")
        assert (tmp_path / "rules_001.pl").read_text() == "rule(extra_rule, true).\n"

    def test_add_rules_keeps_registered_store_on_late_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """add_rules should preserve earlier side effects on later failure."""
        config_path = write_config(tmp_path, {"test_rules": NONEMPTY_RULESET})
        monkeypatch.delenv("ADJOURN_CONFIG", raising=False)
        ws = Workspace(config_path, sessions_dir=tmp_path / "sessions")

        init_result = ws.init("true")
        session_id = init_result["session"]
        state_path = tmp_path / "sessions" / f"{session_id}.json"
        resume_hash_before = json.loads(state_path.read_text())["resume_hash"]

        original_run_cli = ws._run_cli

        def fail_on_set_resume(args: list[str], cwd: Path | None = None) -> dict:
            if args[:2] == ["set-resume", "@top"]:
                raise RuntimeError("late failure")
            return original_run_cli(args, cwd=cwd)

        ws._run_cli = fail_on_set_resume

        with pytest.raises(RuntimeError, match="late failure"):
            ws.add_rules(session_id, "rule(extra_rule, true).\n")

        config = Config(config_path)
        assert config.store_configs[-1]["path"] == "rules_001.pl"
        assert (tmp_path / "rules_001.pl").read_text() == "rule(extra_rule, true).\n"
        state_after = json.loads(state_path.read_text())
        assert state_after["resume_hash"] == resume_hash_before
