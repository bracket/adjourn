"""Tests for the constraint MCP server tools."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
import yaml

mcp = pytest.importorskip("constraint.mcp")

from constraint.config import Config
from constraint.mcp import (
    _allocate_rules_filename,
    _allocate_session_id,
    _config_path,
    _run_cli,
    _server_dir,
    _session_path,
    _sessions_dir,
    constraint_add_rules,
    constraint_init,
    constraint_resume,
)
from constraint.store import FileRuleSetStore

NONEMPTY_RULESET = "rule(test_fixture_placeholder, true).\n"


def _write_config(
    tmp_path: Path,
    rules: dict[str, str],
    *,
    aliases: dict[str, str] | None = None,
    store_names: dict[str, str] | None = None,
    prolog_modes: dict[str, str] | None = None,
) -> Path:
    """Create rules files plus a matching config file."""
    config_dir = tmp_path / ".constraint"
    rules_dir = tmp_path / "rules"
    config_dir.mkdir()
    rules_dir.mkdir()

    stores: list[dict[str, str]] = []
    computed_aliases: dict[str, str] = {}
    for name, content in rules.items():
        rules_path = rules_dir / f"{name}.pl"
        rules_path.write_text(content)
        prolog_mode = prolog_modes.get(name, "constraint") if prolog_modes else "constraint"
        store = FileRuleSetStore(rules_path, prolog=prolog_mode)
        ruleset_hash = store.known_rulesets()[0]
        store_config = {"type": "file", "path": str(Path("rules") / rules_path.name)}
        if store_names is not None and name in store_names:
            store_config["name"] = store_names[name]
        store_config["prolog"] = prolog_mode
        stores.append(store_config)
        computed_aliases[name] = ruleset_hash

    config_path = config_dir / "config.yaml"
    if aliases is None:
        aliases = computed_aliases
    config_path.write_text(yaml.safe_dump({"stores": stores, "aliases": aliases}))
    return config_path


class TestMCPSessionHelpers:
    """Tests for the MCP session helper functions."""

    def test_allocate_session_id(self) -> None:
        """Session ids should be non-empty hex strings."""
        sid = _allocate_session_id()
        assert isinstance(sid, str)
        assert len(sid) > 0
        # UUID hex is 32 chars
        assert len(sid) == 32

    def test_session_path(self, tmp_path: Path) -> None:
        """Session path should be <sessions_dir>/<id>.json."""
        sid = "abc123"
        path = _session_path(sid)
        assert path.name == "abc123.json"
        assert path.parent == _sessions_dir()

    def test_sessions_dir_created(self, tmp_path: Path) -> None:
        """_sessions_dir() should create the directory if missing."""
        # Point sessions dir to tmp_path subdir
        import constraint.mcp as mcp_mod
        old_dir = mcp_mod._SESSIONS_DIR
        test_dir = tmp_path / "mcp-sessions"
        mcp_mod._SESSIONS_DIR = test_dir
        try:
            assert not test_dir.exists()
            result = _sessions_dir()
            assert test_dir.exists()
            assert result == test_dir
        finally:
            mcp_mod._SESSIONS_DIR = old_dir

    def test_server_dir_uses_config_parent_parent(self, tmp_path: Path) -> None:
        """_server_dir() should resolve the directory that contains .constraint."""
        import constraint.mcp as mcp_mod

        old_config_path = mcp_mod._CONFIG_PATH
        config_path = tmp_path / ".constraint" / "config.yaml"
        mcp_mod._CONFIG_PATH = config_path
        try:
            assert _config_path() == config_path
            assert _server_dir() == tmp_path
        finally:
            mcp_mod._CONFIG_PATH = old_config_path

    def test_allocate_rules_filename_is_sequential(self, tmp_path: Path) -> None:
        """rules_NNN allocation should advance from the highest existing number."""
        assert _allocate_rules_filename(tmp_path) == "rules_001.pl"
        (tmp_path / "rules_001.pl").write_text("")
        assert _allocate_rules_filename(tmp_path) == "rules_002.pl"
        (tmp_path / "rules_010.pl").write_text("")
        (tmp_path / "rules_003.pl").write_text("")
        assert _allocate_rules_filename(tmp_path) == "rules_011.pl"


class TestMCPServerTools:
    """End-to-end tests for the MCP server tools."""

    def test_constraint_add_rules_is_registered(self) -> None:
        """constraint_add_rules should be exposed as an MCP tool."""
        tools = asyncio.run(mcp.mcp.list_tools())
        tool_names = {tool.name for tool in tools}
        assert "constraint_init" in tool_names
        assert "constraint_resume" in tool_names
        assert "constraint_add_rules" in tool_names

    def test_constraint_init_returns_session_and_projection(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """constraint_init should return a session id and a projection with status."""
        # Set up config and sessions dir
        config_path = _write_config(tmp_path, {"test_rules": NONEMPTY_RULESET})
        sessions_dir = tmp_path / "sessions"
        monkeypatch.setenv("CONSTRAINT_CONFIG", str(config_path))
        monkeypatch.setenv("CONSTRAINT_MCP_SESSIONS_DIR", str(sessions_dir))

        import constraint.mcp as mcp_mod
        old_sessions_dir = mcp_mod._SESSIONS_DIR
        mcp_mod._SESSIONS_DIR = sessions_dir
        try:
            result = constraint_init("true")
            assert "session" in result
            assert isinstance(result["session"], str)
            assert len(result["session"]) > 0
            assert result["status"] == "running"
            assert "ruleset_hash" in result
            assert "resume_hash" in result
            assert "label" in result
            # Session file should exist on disk
            state_path = sessions_dir / f"{result['session']}.json"
            assert state_path.exists()
            state = json.loads(state_path.read_text())
            assert state["status"] == "running"
        finally:
            mcp_mod._SESSIONS_DIR = old_sessions_dir

    def test_constraint_add_rules_writes_registers_and_resumes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """constraint_add_rules should write a numbered file and repoint resume_hash."""
        config_path = _write_config(tmp_path, {"test_rules": NONEMPTY_RULESET})
        sessions_dir = tmp_path / "sessions"
        monkeypatch.setenv("CONSTRAINT_CONFIG", str(config_path))
        monkeypatch.setenv("CONSTRAINT_MCP_SESSIONS_DIR", str(sessions_dir))

        import constraint.mcp as mcp_mod

        old_sessions_dir = mcp_mod._SESSIONS_DIR
        old_config_path = mcp_mod._CONFIG_PATH
        mcp_mod._SESSIONS_DIR = sessions_dir
        mcp_mod._CONFIG_PATH = config_path
        try:
            init_result = constraint_init("true")
            session_id = init_result["session"]
            before_resume_hash = init_result["resume_hash"]

            result = constraint_add_rules(session_id, "rule(extra_rule, true).\n")

            assert result["session"] == session_id
            assert result["status"] == "solution"
            assert result["resume_hash"] != before_resume_hash

            first_rules_path = tmp_path / "rules_001.pl"
            assert first_rules_path.read_text() == "rule(extra_rule, true).\n"

            config = Config(config_path)
            assert config.store_configs[-1]["path"] == "rules_001.pl"

            state = json.loads((sessions_dir / f"{session_id}.json").read_text())
            assert state["resume_hash"] == result["resume_hash"]

            follow_up = constraint_resume(session_id)
            assert follow_up["status"] == "done"
            assert follow_up["resume_hash"] == result["resume_hash"]
        finally:
            mcp_mod._SESSIONS_DIR = old_sessions_dir
            mcp_mod._CONFIG_PATH = old_config_path

    def test_constraint_add_rules_uses_server_dir_for_all_cli_calls(
        self, tmp_path: Path
    ) -> None:
        """constraint_add_rules should invoke every CLI step from the server directory."""
        import constraint.mcp as mcp_mod

        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        state_path = sessions_dir / "session.json"
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

        config_path = tmp_path / ".constraint" / "config.yaml"
        config_path.parent.mkdir()
        config_path.write_text(yaml.safe_dump({"stores": [], "aliases": {}}))

        old_sessions_dir = mcp_mod._SESSIONS_DIR
        old_config_path = mcp_mod._CONFIG_PATH
        old_run_cli = mcp_mod._run_cli
        mcp_mod._SESSIONS_DIR = sessions_dir
        mcp_mod._CONFIG_PATH = config_path

        calls: list[tuple[list[str], Path | None]] = []

        def fake_run_cli(args: list[str], cwd: Path | None = None) -> dict:
            calls.append((args, cwd))
            return {
                "status": "done",
                "label": None,
                "ruleset_hash": "a" * 64,
                "resume_hash": "b" * 64,
            }

        mcp_mod._run_cli = fake_run_cli
        try:
            result = constraint_add_rules("session", "rule(extra_rule, true).\n")
            assert result["status"] == "done"
            assert [call[0][:2] for call in calls] == [
                ["rules", "add"],
                ["set-resume", "@top"],
                ["resume", str(state_path.resolve())],
            ]
            assert all(cwd == tmp_path for _, cwd in calls)
            assert calls[0][0][2] == "rules_001.pl"
        finally:
            mcp_mod._SESSIONS_DIR = old_sessions_dir
            mcp_mod._CONFIG_PATH = old_config_path
            mcp_mod._run_cli = old_run_cli

    def test_constraint_add_rules_missing_session_raises(
        self, tmp_path: Path
    ) -> None:
        """constraint_add_rules should mirror constraint_resume for missing sessions."""
        import constraint.mcp as mcp_mod

        old_sessions_dir = mcp_mod._SESSIONS_DIR
        mcp_mod._SESSIONS_DIR = tmp_path / "sessions"
        try:
            with pytest.raises(RuntimeError, match="Session 'missing' not found"):
                constraint_add_rules("missing", "rule(extra_rule, true).\n")
        finally:
            mcp_mod._SESSIONS_DIR = old_sessions_dir

    def test_constraint_add_rules_on_done_session_returns_done(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """constraint_add_rules should return done when resuming a done session."""
        config_path = _write_config(tmp_path, {"test_rules": NONEMPTY_RULESET})
        sessions_dir = tmp_path / "sessions"
        monkeypatch.setenv("CONSTRAINT_CONFIG", str(config_path))
        monkeypatch.setenv("CONSTRAINT_MCP_SESSIONS_DIR", str(sessions_dir))

        import constraint.mcp as mcp_mod

        old_sessions_dir = mcp_mod._SESSIONS_DIR
        old_config_path = mcp_mod._CONFIG_PATH
        mcp_mod._SESSIONS_DIR = sessions_dir
        mcp_mod._CONFIG_PATH = config_path
        try:
            init_result = constraint_init("true")
            session_id = init_result["session"]
            assert constraint_resume(session_id)["status"] == "solution"
            assert constraint_resume(session_id)["status"] == "done"

            result = constraint_add_rules(session_id, "rule(done_rule, true).\n")

            assert result["session"] == session_id
            assert result["status"] == "done"
            assert (tmp_path / "rules_001.pl").exists()
        finally:
            mcp_mod._SESSIONS_DIR = old_sessions_dir
            mcp_mod._CONFIG_PATH = old_config_path

    def test_constraint_resume_advances_state(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """constraint_resume should advance the state and return updated projection."""
        config_path = _write_config(tmp_path, {"test_rules": NONEMPTY_RULESET})
        sessions_dir = tmp_path / "sessions"
        monkeypatch.setenv("CONSTRAINT_CONFIG", str(config_path))
        monkeypatch.setenv("CONSTRAINT_MCP_SESSIONS_DIR", str(sessions_dir))

        import constraint.mcp as mcp_mod
        old_sessions_dir = mcp_mod._SESSIONS_DIR
        mcp_mod._SESSIONS_DIR = sessions_dir
        try:
            # Init
            init_result = constraint_init("true")
            session_id = init_result["session"]
            assert init_result["status"] == "running"

            # Resume once — should reach solution
            resume_result = constraint_resume(session_id)
            assert resume_result["session"] == session_id
            assert resume_result["status"] in ("solution", "suspended", "running", "done")

            # Resume again — should eventually reach done
            resume_result2 = constraint_resume(session_id)
            assert resume_result2["session"] == session_id
            # For 'true' goal, after solution we should get done
            assert resume_result2["status"] in ("solution", "suspended", "running", "done")
        finally:
            mcp_mod._SESSIONS_DIR = old_sessions_dir

    def test_full_coroutine_loop_to_done(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Drive a session from init through resume to done."""
        config_path = _write_config(tmp_path, {"test_rules": NONEMPTY_RULESET})
        sessions_dir = tmp_path / "sessions"
        monkeypatch.setenv("CONSTRAINT_CONFIG", str(config_path))
        monkeypatch.setenv("CONSTRAINT_MCP_SESSIONS_DIR", str(sessions_dir))

        import constraint.mcp as mcp_mod
        old_sessions_dir = mcp_mod._SESSIONS_DIR
        mcp_mod._SESSIONS_DIR = sessions_dir
        try:
            result = constraint_init("true")
            session_id = result["session"]
            assert result["status"] == "running"

            # Resume to solution
            r1 = constraint_resume(session_id)
            assert r1["status"] == "solution"

            # Resume to done
            r2 = constraint_resume(session_id)
            assert r2["status"] == "done"

            # Resuming done is idempotent
            r3 = constraint_resume(session_id)
            assert r3["status"] == "done"
        finally:
            mcp_mod._SESSIONS_DIR = old_sessions_dir

    def test_resume_nonexistent_session_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Resuming a non-existent session should raise RuntimeError."""
        import constraint.mcp as mcp_mod
        old_sessions_dir = mcp_mod._SESSIONS_DIR
        mcp_mod._SESSIONS_DIR = Path("/tmp/nonexistent-sessions-dir-12345")
        try:
            with pytest.raises(RuntimeError, match="not found"):
                constraint_resume("nonexistent-session-id")
        finally:
            mcp_mod._SESSIONS_DIR = old_sessions_dir

    def test_run_cli_raises_on_failure(self) -> None:
        """_run_cli should raise RuntimeError on CLI failure."""
        with pytest.raises(RuntimeError, match="CLI command failed"):
            _run_cli(["init", "true", "/nonexistent/path/state.json", "--format", "json"])

    def test_sessions_are_disk_backed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Session state should persist on disk (no in-memory map)."""
        config_path = _write_config(tmp_path, {"test_rules": NONEMPTY_RULESET})
        sessions_dir = tmp_path / "sessions"
        monkeypatch.setenv("CONSTRAINT_CONFIG", str(config_path))
        monkeypatch.setenv("CONSTRAINT_MCP_SESSIONS_DIR", str(sessions_dir))

        import constraint.mcp as mcp_mod
        old_sessions_dir = mcp_mod._SESSIONS_DIR
        mcp_mod._SESSIONS_DIR = sessions_dir
        try:
            result = constraint_init("true")
            session_id = result["session"]
            state_path = sessions_dir / f"{session_id}.json"
            assert state_path.exists()

            # Read the file directly
            state = json.loads(state_path.read_text())
            assert state["status"] == "running"

            # Resume via file
            r1 = constraint_resume(session_id)
            state2 = json.loads(state_path.read_text())
            assert state2["status"] == r1["status"]
        finally:
            mcp_mod._SESSIONS_DIR = old_sessions_dir
