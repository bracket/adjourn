"""Unit tests for the run_mini_swe foreign callout."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from constraint.parser.ast import Clause
from constraint.parser.parser import parse_file


# ---------------------------------------------------------------------------
# Helpers (mirrored from test_meta.py)
# ---------------------------------------------------------------------------


def _write_rules(content: str) -> Path:
    """Write Prolog rules to a temporary file and return its Path."""
    fd, path = tempfile.mkstemp(suffix=".pl", prefix="constraint_test_")
    os.close(fd)
    Path(path).write_text(content)
    return Path(path)


def _parse_rules(content: str) -> list[Clause]:
    """Parse Prolog rules into a clause list."""
    rules_path = _write_rules(content)
    try:
        program = parse_file(str(rules_path))
        return [item for item in program.items if isinstance(item, Clause)]
    finally:
        rules_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Unit tests for the run_mini_swe callout function itself
# ---------------------------------------------------------------------------


class TestRunMiniSweCallout:
    """Unit tests for _run_mini_swe argument validation and dispatch."""

    def test_raises_on_non_list_arg(self) -> None:
        """A non-iterable argument must raise ValueError."""
        from constraint.mini_swe.mini_swe import _run_mini_swe

        with pytest.raises(ValueError):
            _run_mini_swe(42)  # int is not iterable

    def test_raises_on_wrong_length(self, tmp_path: Path) -> None:
        """A list with != 2 elements must raise ValueError."""
        from constraint.mini_swe.mini_swe import _run_mini_swe

        with pytest.raises(ValueError, match="2"):
            _run_mini_swe([str(tmp_path)])

    def test_raises_on_missing_repo_root(self, tmp_path: Path) -> None:
        """A non-existent repo_root must raise ValueError."""
        from constraint.mini_swe.mini_swe import _run_mini_swe

        issue = tmp_path / "issue.md"
        issue.write_text("task")
        with pytest.raises(ValueError, match="repo_root"):
            _run_mini_swe([str(tmp_path / "no_such_dir"), str(issue)])

    def test_raises_on_missing_issue_file(self, tmp_path: Path) -> None:
        """A non-existent issue_file must raise ValueError."""
        from constraint.mini_swe.mini_swe import _run_mini_swe

        with pytest.raises(ValueError, match="issue_file"):
            _run_mini_swe([str(tmp_path), str(tmp_path / "no_such_file.md")])

    def test_runs_docker_compose_and_returns_rev(self, tmp_path: Path) -> None:
        """Successful run must invoke docker compose then git rev-parse HEAD."""
        from constraint.mini_swe.mini_swe import _run_mini_swe

        issue = tmp_path / "task.md"
        issue.write_text("do something")

        fake_rev = "abc1234def5678"
        mock_completed = MagicMock()
        mock_completed.stdout = fake_rev + "\n"

        call_args: list[Any] = []

        def fake_run(cmd: list[str], **kwargs: Any) -> MagicMock:
            call_args.append(cmd)
            return mock_completed

        with patch("constraint.mini_swe.mini_swe.subprocess.run", side_effect=fake_run):
            result = _run_mini_swe([str(tmp_path), str(issue)])

        assert result == fake_rev
        # First call is docker compose
        assert "docker" in call_args[0]
        assert "compose" in call_args[0]
        # Second call is git rev-parse HEAD
        assert call_args[1] == ["git", "rev-parse", "HEAD"]

    def test_env_file_cleaned_up_on_success(self, tmp_path: Path) -> None:
        """The temporary env file must be removed after a successful run."""
        import io

        from constraint.mini_swe.mini_swe import _run_mini_swe

        issue = tmp_path / "task.md"
        issue.write_text("do something")

        # Pre-create the file so the unlink() in the finally block can succeed.
        fake_env_path = str(tmp_path / "fake_env.env")
        Path(fake_env_path).touch()

        mock_completed = MagicMock()
        mock_completed.stdout = "deadbeef\n"

        # Patch os.fdopen so no real fd is needed; a StringIO satisfies the
        # context-manager write interface used by the implementation.
        with (
            patch("constraint.mini_swe.mini_swe.subprocess.run", return_value=mock_completed),
            patch(
                "constraint.mini_swe.mini_swe.tempfile.mkstemp",
                return_value=(0, fake_env_path),
            ),
            patch("constraint.mini_swe.mini_swe.os.fdopen", return_value=io.StringIO()),
        ):
            _run_mini_swe([str(tmp_path), str(issue)])

        assert not Path(fake_env_path).exists(), "env file was not cleaned up"

    def test_task_dir_cleaned_up_on_success(self, tmp_path: Path) -> None:
        """The temporary task directory must be removed after a successful run."""
        from constraint.mini_swe.mini_swe import _run_mini_swe

        issue = tmp_path / "task.md"
        issue.write_text("do something")

        fake_task_dir = str(tmp_path / "fake_task_dir")
        os.makedirs(fake_task_dir, exist_ok=True)

        mock_completed = MagicMock()
        mock_completed.stdout = "deadbeef\n"

        with (
            patch("constraint.mini_swe.mini_swe.subprocess.run", return_value=mock_completed),
            patch(
                "constraint.mini_swe.mini_swe.tempfile.mkdtemp",
                return_value=fake_task_dir,
            ),
            patch("constraint.mini_swe.mini_swe.shutil.copy2"),
        ):
            _run_mini_swe([str(tmp_path), str(issue)])

        assert not Path(fake_task_dir).exists(), "task dir was not cleaned up"


# ---------------------------------------------------------------------------
# Tests for foreign/3 reduction via the meta-interpreter (mirrors TestForeignGoal)
# ---------------------------------------------------------------------------


class TestRunMiniSweForeignGoal:
    """Tests for run_mini_swe reduction via the foreign/3 meta-interpreter rule.

    Mirrors the conventions of ``TestForeignGoal`` in ``test_meta.py`` but
    exercises the ``run_mini_swe`` callout. Docker and git subprocess calls are
    monkeypatched so no real container is started.
    """

    def setup_method(self) -> None:
        # A rule whose body is a single foreign/3 goal for run_mini_swe.
        # The list argument uses Prolog atom syntax; janus marshals it to list[str].
        self.ruleset = _parse_rules(
            "rule(test_run_mini_swe,"
            " foreign(run_mini_swe, ['/repo', '/issue.md'], _Out)).\n"
        )

    def _make_fake_run(self, fake_rev: str = "abc1234") -> Any:
        """Return a fake subprocess.run that succeeds and returns *fake_rev* for git."""
        mock_completed = MagicMock()
        mock_completed.stdout = fake_rev + "\n"

        def _fake_run(cmd: list[str], **kwargs: Any) -> MagicMock:
            return mock_completed

        return _fake_run

    def test_run_mini_swe_foreign_resolves_to_solution(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """A foreign(run_mini_swe, ...) goal must reduce and reach solution."""
        from constraint.meta import init_state, resume_state

        issue = tmp_path / "issue.md"
        issue.write_text("task")

        monkeypatch.setattr(
            "constraint.mini_swe.mini_swe.subprocess.run",
            self._make_fake_run(),
        )
        # Patch path validation so /repo and /issue.md are accepted.
        monkeypatch.setattr(
            "constraint.mini_swe.mini_swe.Path.is_dir",
            lambda self: True,
        )
        monkeypatch.setattr(
            "constraint.mini_swe.mini_swe.Path.is_file",
            lambda self: True,
        )
        # Patch shutil.copy2 so no real file copy is attempted.
        monkeypatch.setattr("constraint.mini_swe.mini_swe.shutil.copy2", lambda *a, **kw: None)

        state = init_state("test_run_mini_swe")
        result = resume_state(state, self.ruleset)
        assert result["status"] == "solution"

    def test_run_mini_swe_foreign_solution_has_bindings(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """Solution after foreign(run_mini_swe) reduction must include bindings key."""
        from constraint.meta import init_state, resume_state

        monkeypatch.setattr(
            "constraint.mini_swe.mini_swe.subprocess.run",
            self._make_fake_run(),
        )
        monkeypatch.setattr("constraint.mini_swe.mini_swe.Path.is_dir", lambda self: True)
        monkeypatch.setattr("constraint.mini_swe.mini_swe.Path.is_file", lambda self: True)
        monkeypatch.setattr("constraint.mini_swe.mini_swe.shutil.copy2", lambda *a, **kw: None)

        state = init_state("test_run_mini_swe")
        result = resume_state(state, self.ruleset)
        assert "bindings" in result

    def test_run_mini_swe_foreign_no_suspension(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """A foreign(run_mini_swe) reduction must not produce a suspended event."""
        from constraint.meta import init_state, resume_state

        monkeypatch.setattr(
            "constraint.mini_swe.mini_swe.subprocess.run",
            self._make_fake_run(),
        )
        monkeypatch.setattr("constraint.mini_swe.mini_swe.Path.is_dir", lambda self: True)
        monkeypatch.setattr("constraint.mini_swe.mini_swe.Path.is_file", lambda self: True)
        monkeypatch.setattr("constraint.mini_swe.mini_swe.shutil.copy2", lambda *a, **kw: None)

        state = init_state("test_run_mini_swe")
        result = resume_state(state, self.ruleset)
        assert "suspension" not in result

    def test_run_mini_swe_foreign_original_goal_preserved(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """original_goal must be unchanged after foreign(run_mini_swe) reduction."""
        from constraint.meta import init_state, resume_state

        monkeypatch.setattr(
            "constraint.mini_swe.mini_swe.subprocess.run",
            self._make_fake_run(),
        )
        monkeypatch.setattr("constraint.mini_swe.mini_swe.Path.is_dir", lambda self: True)
        monkeypatch.setattr("constraint.mini_swe.mini_swe.Path.is_file", lambda self: True)
        monkeypatch.setattr("constraint.mini_swe.mini_swe.shutil.copy2", lambda *a, **kw: None)

        goal = "test_run_mini_swe"
        state = init_state(goal)
        result = resume_state(state, self.ruleset)
        assert result["original_goal"] == goal


# ---------------------------------------------------------------------------
# Registry registration test
# ---------------------------------------------------------------------------


class TestRunMiniSweRegistration:
    """Verify that importing constraint_foreign registers run_mini_swe."""

    def test_run_mini_swe_in_registry_after_import(self) -> None:
        """run_mini_swe must appear in the foreign registry after import."""
        import constraint.constraint_foreign as cf

        assert "run_mini_swe" in cf._registry
