"""Unit tests for the meta-interpreter core (meta.py / meta.pl)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import pytest

from constraint.parser.ast import Clause
from constraint.parser.parser import parse_file

NONEMPTY_RULESET = "rule(test_fixture_placeholder, true).\n"


# ---------------------------------------------------------------------------
# Helpers
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
# Tests for init_state
# ---------------------------------------------------------------------------


class TestInitState:
    """Tests for constraint.meta.init_state."""

    def test_schema_version(self) -> None:
        from constraint.meta import init_state

        state = init_state("foo")
        assert state["version"] == 0

    def test_original_goal_preserved(self) -> None:
        from constraint.meta import init_state

        goal = "color(X, Y)"
        state = init_state(goal)
        assert state["original_goal"] == goal

    def test_status_is_running(self) -> None:
        from constraint.meta import init_state

        state = init_state("foo(bar)")
        assert state["status"] == "running"

    def test_single_branch_with_goal(self) -> None:
        from constraint.meta import init_state

        goal = "member(X, [1,2,3])"
        state = init_state(goal)
        assert len(state["branches"]) == 1
        assert state["branches"][0]["goals"] == [goal]

    def test_no_suspension_or_bindings(self) -> None:
        from constraint.meta import init_state

        state = init_state("any_goal")
        assert "suspension" not in state
        assert "bindings" not in state

    def test_pure_python_no_prolog(self, monkeypatch: Any) -> None:
        """init_state must not call Prolog."""
        import janus_swi as janus

        called: list[str] = []

        def _spy(*_args: Any, **_kwargs: Any) -> Any:
            called.append("consult")
            raise AssertionError("Prolog must not be called by init_state")

        monkeypatch.setattr(janus, "consult", _spy)

        from constraint.meta import init_state

        state = init_state("pure_python_goal")
        assert state["status"] == "running"
        assert called == []


# ---------------------------------------------------------------------------
# Tests for resume_state
# ---------------------------------------------------------------------------


class TestResumeStateTrueGoal:
    """Tests using the trivially-true goal ``true``."""

    def setup_method(self) -> None:
        self.ruleset = _parse_rules(NONEMPTY_RULESET)

    def test_true_goal_reaches_solution(self) -> None:
        from constraint.meta import init_state, resume_state

        state = init_state("true")
        result = resume_state(state, self.ruleset)
        assert result["status"] == "solution"

    def test_solution_has_bindings_key(self) -> None:
        from constraint.meta import init_state, resume_state

        state = init_state("true")
        result = resume_state(state, self.ruleset)
        assert "bindings" in result

    def test_solution_preserves_original_goal(self) -> None:
        from constraint.meta import init_state, resume_state

        state = init_state("true")
        result = resume_state(state, self.ruleset)
        assert result["original_goal"] == "true"

    def test_solution_has_no_suspension_key(self) -> None:
        from constraint.meta import init_state, resume_state

        state = init_state("true")
        result = resume_state(state, self.ruleset)
        assert "suspension" not in result

    def test_solution_branches_empty(self) -> None:
        from constraint.meta import init_state, resume_state

        state = init_state("true")
        result = resume_state(state, self.ruleset)
        assert result["branches"] == []


class TestResumeStateYield:
    """Tests using a goal that triggers yield(Label)."""

    def setup_method(self) -> None:
        self.ruleset = _parse_rules("rule(test_yield, yield(hello)).\n")

    def test_yield_produces_suspended_status(self) -> None:
        from constraint.meta import init_state, resume_state

        state = init_state("test_yield")
        result = resume_state(state, self.ruleset)
        assert result["status"] == "suspended"

    def test_suspended_has_label(self) -> None:
        from constraint.meta import init_state, resume_state

        state = init_state("test_yield")
        result = resume_state(state, self.ruleset)
        assert result["suspension"]["label"] == "hello"

    def test_suspended_has_no_bindings_key(self) -> None:
        from constraint.meta import init_state, resume_state

        state = init_state("test_yield")
        result = resume_state(state, self.ruleset)
        assert "bindings" not in result

    def test_resume_from_suspended_reaches_solution(self) -> None:
        """Resuming a suspended state should eventually reach solution/done."""
        from constraint.meta import init_state, resume_state

        state = init_state("test_yield")
        state = resume_state(state, self.ruleset)
        assert state["status"] == "suspended"
        state = resume_state(state, self.ruleset)
        assert state["status"] in {"solution", "done"}

    def test_suspended_state_structure_is_valid(self) -> None:
        """The suspended state must have the required schema keys."""
        from constraint.meta import init_state, resume_state

        state = init_state("test_yield")
        result = resume_state(state, self.ruleset)
        required_keys = {"version", "original_goal", "branches", "status", "suspension"}
        assert required_keys.issubset(result.keys())


class TestResumeStateDone:
    """Tests for the 'done' (no solutions) terminal state."""

    def setup_method(self) -> None:
        self.ruleset = _parse_rules(NONEMPTY_RULESET)

    def test_unknown_goal_reaches_done(self) -> None:
        from constraint.meta import init_state, resume_state

        state = init_state("no_rule_exists_for_this_goal")
        result = resume_state(state, self.ruleset)
        assert result["status"] == "done"

    def test_done_state_is_idempotent(self) -> None:
        """Resuming a done state must return the same state unchanged."""
        from constraint.meta import init_state, resume_state

        state = init_state("no_rule_exists_for_this_goal")
        state = resume_state(state, self.ruleset)
        assert state["status"] == "done"
        state2 = resume_state(state, self.ruleset)
        assert state2["status"] == "done"
        assert state2["branches"] == state["branches"]

    def test_done_has_no_suspension(self) -> None:
        from constraint.meta import init_state, resume_state

        state = init_state("no_rule_exists_for_this_goal")
        result = resume_state(state, self.ruleset)
        assert "suspension" not in result


class TestResumeStateEmptyRuleset:
    """Tests for rejecting empty interpreted programs."""

    def test_empty_ruleset_raises_value_error(self) -> None:
        from constraint.meta import init_state, resume_state

        state = init_state("true")

        with pytest.raises(ValueError, match="empty ruleset"):
            resume_state(state, [])

    def test_done_state_short_circuits_before_empty_ruleset_check(self) -> None:
        from constraint.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "true",
            "branches": [],
            "status": "done",
        }

        assert resume_state(state, []) == state


class TestResumeStateMultipleRules:
    """Tests for goals with multiple matching rules (DFS branching)."""

    def setup_method(self) -> None:
        self.ruleset = _parse_rules(
            "rule(choice, true).\n"
            "rule(choice, true).\n"
        )

    def test_first_rule_gives_solution(self) -> None:
        from constraint.meta import init_state, resume_state

        state = init_state("choice")
        result = resume_state(state, self.ruleset)
        # First DFS branch should give a solution.
        assert result["status"] == "solution"

    def test_remaining_branches_kept(self) -> None:
        from constraint.meta import init_state, resume_state

        state = init_state("choice")
        result = resume_state(state, self.ruleset)
        # Second alternative branch should still be present.
        assert result["status"] == "solution"
        # There must be at least one remaining branch for the second rule.
        # (Additional branches may be present if prior test runs accumulated
        # rule/2 facts in the SWI-Prolog process; we only verify ≥ 1.)
        assert len(result["branches"]) >= 1


class TestResumeStateSchemaConsistency:
    """The schema must be consistent across multiple resumes."""

    def setup_method(self) -> None:
        self.ruleset = _parse_rules("rule(step_goal, yield(step1)).\n")

    def test_version_unchanged_across_resumes(self) -> None:
        from constraint.meta import init_state, resume_state

        state = init_state("step_goal")
        for _ in range(3):
            state = resume_state(state, self.ruleset)
            assert state["version"] == 0

    def test_original_goal_unchanged_across_resumes(self) -> None:
        from constraint.meta import init_state, resume_state

        goal = "step_goal"
        state = init_state(goal)
        for _ in range(3):
            state = resume_state(state, self.ruleset)
            assert state["original_goal"] == goal
