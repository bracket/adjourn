"""Unit tests for the subprocess foreign callout."""

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


def _noop(*args: Any, **kwargs: Any) -> None:
    """No-op stub for monkeypatching side-effect functions that return nothing."""


# ---------------------------------------------------------------------------
# Unit tests for the _subprocess callout function itself
# ---------------------------------------------------------------------------


class TestSubprocessCallout:
    """Unit tests for _subprocess argument validation and dispatch."""

    def test_raises_on_non_iterable_arg(self) -> None:
        """A non-iterable argument must raise ValueError."""
        from constraint.subprocess.subprocess import _subprocess

        with pytest.raises(ValueError):
            _subprocess(42)  # int is not iterable

    def test_raises_on_empty_list(self) -> None:
        """An empty list must raise ValueError."""
        from constraint.subprocess.subprocess import _subprocess

        with pytest.raises(ValueError, match="at least 2 elements"):
            _subprocess([])

    def test_raises_on_cwd_only(self) -> None:
        """A list with only a cwd and no argv must raise ValueError."""
        from constraint.subprocess.subprocess import _subprocess

        with pytest.raises(ValueError, match="at least 2 elements"):
            _subprocess(["."])

    def test_nonzero_exit_does_not_raise(self) -> None:
        """A nonzero exit code must be returned, not raised as an exception."""
        from constraint.subprocess.subprocess import _subprocess

        mock_completed = MagicMock()
        mock_completed.returncode = 3

        with patch("constraint.subprocess.subprocess.subprocess.run", return_value=mock_completed):
            result = _subprocess([".", "bash", "-c", "exit 3"])

        assert result == 3

    def test_zero_exit_returns_zero(self) -> None:
        """Exit code 0 must be returned correctly."""
        from constraint.subprocess.subprocess import _subprocess

        mock_completed = MagicMock()
        mock_completed.returncode = 0

        with patch("constraint.subprocess.subprocess.subprocess.run", return_value=mock_completed):
            result = _subprocess([".", "bash", "-c", "exit 0"])

        assert result == 0

    def test_cwd_is_honored(self) -> None:
        """The supplied cwd must be passed to subprocess.run."""
        from constraint.subprocess.subprocess import _subprocess

        mock_completed = MagicMock()
        mock_completed.returncode = 0

        captured_cwd: list[str] = []

        def fake_run(cmd: list[str], **kwargs: Any) -> Any:
            captured_cwd.append(kwargs.get("cwd", ""))
            return mock_completed

        test_cwd = "/some/test/directory"
        with patch("constraint.subprocess.subprocess.subprocess.run", side_effect=fake_run):
            _subprocess([test_cwd, "pwd"])

        assert captured_cwd == [test_cwd]

    def test_cwd_with_relative_path_file_check(self, tmp_path: Path) -> None:
        """A command that depends on the working directory must reflect the supplied cwd."""
        from constraint.subprocess.subprocess import _subprocess

        # Create a file in a subdirectory
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        marker = subdir / "marker.txt"
        marker.write_text("present")

        # Run a test -f command with cwd pointing to the subdir
        result = _subprocess([str(subdir), "test", "-f", "marker.txt"])
        assert result == 0

        # Run with cwd pointing to the parent - should fail since marker.txt is in subdir
        result = _subprocess([str(tmp_path), "test", "-f", "marker.txt"])
        assert result != 0

    def test_missing_binary_raises(self) -> None:
        """A missing binary must raise FileNotFoundError."""
        from constraint.subprocess.subprocess import _subprocess

        with pytest.raises(FileNotFoundError):
            _subprocess([".", "nonexistent_binary_xyz123"])


# ---------------------------------------------------------------------------
# Tests for foreign/3 reduction via the meta-interpreter (mirrors TestForeignGoal)
# ---------------------------------------------------------------------------


class TestSubprocessForeignGoal:
    """Tests for subprocess reduction via the foreign/3 meta-interpreter rule.

    Mirrors the conventions of ``TestForeignGoal`` in ``test_meta.py`` but
    exercises the ``subprocess`` callout. Subprocess calls are monkeypatched
    so no real system commands are run.
    """

    def setup_method(self) -> None:
        # A rule whose body is a single foreign/3 goal for subprocess.
        # The list argument uses Prolog atom syntax; janus marshals it to list[str].
        self.ruleset = _parse_rules(
            "rule(test_subprocess_call,"
            " foreign(subprocess, ['.', 'bash', '-c', 'exit 0'], _Out)).\n"
        )

    def _apply_callout_patches(self, monkeypatch: Any) -> None:
        """Apply common monkeypatches needed to stub out the callout side effects."""
        mock_completed = MagicMock()
        mock_completed.returncode = 0
        monkeypatch.setattr(
            "constraint.subprocess.subprocess.subprocess.run",
            lambda *args, **kwargs: mock_completed,
        )

    def test_subprocess_foreign_resolves_to_solution(
        self, monkeypatch: Any
    ) -> None:
        """A foreign(subprocess, ...) goal must reduce and reach solution."""
        from constraint.meta import init_state, resume_state

        self._apply_callout_patches(monkeypatch)

        state = init_state("test_subprocess_call")
        result = resume_state(state, self.ruleset)
        assert result["status"] == "solution"

    def test_subprocess_foreign_solution_has_bindings(
        self, monkeypatch: Any
    ) -> None:
        """Solution after foreign(subprocess) reduction must include bindings key."""
        from constraint.meta import init_state, resume_state

        self._apply_callout_patches(monkeypatch)

        state = init_state("test_subprocess_call")
        result = resume_state(state, self.ruleset)
        assert "bindings" in result

    def test_subprocess_foreign_no_suspension(
        self, monkeypatch: Any
    ) -> None:
        """A foreign(subprocess) reduction must not produce a suspended event."""
        from constraint.meta import init_state, resume_state

        self._apply_callout_patches(monkeypatch)

        state = init_state("test_subprocess_call")
        result = resume_state(state, self.ruleset)
        assert "suspension" not in result

    def test_subprocess_foreign_original_goal_preserved(
        self, monkeypatch: Any
    ) -> None:
        """original_goal must be unchanged after foreign(subprocess) reduction."""
        from constraint.meta import init_state, resume_state

        self._apply_callout_patches(monkeypatch)

        goal = "test_subprocess_call"
        state = init_state(goal)
        result = resume_state(state, self.ruleset)
        assert result["original_goal"] == goal


# ---------------------------------------------------------------------------
# Registry registration test
# ---------------------------------------------------------------------------


class TestSubprocessRegistration:
    """Verify that importing constraint_foreign registers subprocess."""

    def test_subprocess_in_registry_after_import(self) -> None:
        """subprocess must appear in the foreign registry after import."""
        import constraint.constraint_foreign as cf

        assert "subprocess" in cf._registry
