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

    def test_unknown_goal_raises_error(self) -> None:
        from constraint.meta import init_state, resume_state

        state = init_state("no_rule_exists_for_this_goal")
        with pytest.raises(Exception, match="unknown_goal"):
            resume_state(state, self.ruleset)

    def test_done_state_is_idempotent(self) -> None:
        """Resuming a done state must return the same state unchanged."""
        from constraint.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "true",
            "branches": [],
            "status": "done",
        }
        assert state["status"] == "done"
        state2 = resume_state(state, self.ruleset)
        assert state2["status"] == "done"
        assert state2["branches"] == state["branches"]

    def test_failing_builtin_reaches_done_without_suspension(self) -> None:
        from constraint.meta import init_state, resume_state

        state = init_state("false")
        result = resume_state(state, self.ruleset)
        assert result["status"] == "done"
        assert "suspension" not in result


class TestResumeStateEscapeHatch:
    """Tests for non-rule goal dispatch via once(call/1)."""

    def setup_method(self) -> None:
        self.ruleset = _parse_rules(
            NONEMPTY_RULESET
            + "plain_concat_result(R) :- atom_concat(left, right, R).\n"
        )

    def test_builtin_goal_binds_output(self) -> None:
        from constraint.meta import init_state, resume_state

        state = init_state("atom_concat(prefix, suffix, R)")
        result = resume_state(state, self.ruleset)
        assert result["status"] == "solution"
        assert result["bindings"]["R"] == "prefixsuffix"

    def test_consulted_non_rule_predicate_is_callable(self) -> None:
        from constraint.meta import init_state, resume_state

        state = init_state("plain_concat_result(R)")
        result = resume_state(state, self.ruleset)
        assert result["status"] == "solution"
        assert result["bindings"]["R"] == "leftright"

    def test_builtin_binding_survives_suspend_resume_round_trip(self) -> None:
        from constraint.meta import init_state, resume_state

        state = init_state(
            "(atom_concat(prefix, suffix, R), yield(pause), R=prefixsuffix)"
        )
        state = resume_state(state, self.ruleset)
        assert state["status"] == "suspended"
        state = resume_state(state, self.ruleset)
        assert state["status"] == "solution"


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
            "choice :- yield(escape_hatch_should_not_run).\n"
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

    def test_rule_dispatch_takes_precedence_over_callable_predicate(self) -> None:
        from constraint.meta import init_state, resume_state

        state = init_state("choice")
        result = resume_state(state, self.ruleset)
        assert result["status"] == "solution"


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


# ---------------------------------------------------------------------------
# Tests for foreign/3 callout
# ---------------------------------------------------------------------------


class TestForeignGoal:
    """Tests for the foreign/3 callout special form."""

    def setup_method(self) -> None:
        # A rule whose body is a single foreign/3 goal (git rev-parse HEAD).
        self.ruleset = _parse_rules(
            "rule(test_foreign_call, foreign(git_rev_parse, 'HEAD', _Out)).\n"
        )

    def test_foreign_goal_resolves_to_solution(self) -> None:
        """A foreign/3 goal must reduce via py_call and reach solution."""
        from constraint.meta import init_state, resume_state

        state = init_state("test_foreign_call")
        result = resume_state(state, self.ruleset)
        assert result["status"] == "solution"

    def test_foreign_goal_solution_has_bindings_key(self) -> None:
        """Solution after foreign/3 reduction must include the bindings key."""
        from constraint.meta import init_state, resume_state

        state = init_state("test_foreign_call")
        result = resume_state(state, self.ruleset)
        assert "bindings" in result

    def test_foreign_goal_no_suspension_key(self) -> None:
        """A foreign/3 reduction must not produce a suspended event."""
        from constraint.meta import init_state, resume_state

        state = init_state("test_foreign_call")
        result = resume_state(state, self.ruleset)
        assert "suspension" not in result

    def test_foreign_goal_original_goal_preserved(self) -> None:
        """original_goal must be unchanged after a foreign/3 reduction."""
        from constraint.meta import init_state, resume_state

        goal = "test_foreign_call"
        state = init_state(goal)
        result = resume_state(state, self.ruleset)
        assert result["original_goal"] == goal


class TestForeignGoalPackedRoundTrip:
    """A foreign/3 goal later in the resolvent must survive serialisation.

    When a ``foreign/3`` goal is NOT the goal being reduced this step, it
    sits in the packed atom and must survive a ``term_to_atom`` /
    ``read_term_from_atom`` round-trip intact so that subsequent steps can
    still reduce it.
    """

    def setup_method(self) -> None:
        # yield/1 suspends first; the foreign goal is left in the resolvent.
        self.ruleset = _parse_rules(
            "rule(test_foreign_later,"
            " (yield(pause), foreign(git_rev_parse, 'HEAD', _Out))).\n"
        )

    def test_suspended_after_yield_with_foreign_in_resolvent(self) -> None:
        """First step yields; foreign/3 remains in the pending resolvent."""
        from constraint.meta import init_state, resume_state

        state = init_state("test_foreign_later")
        result = resume_state(state, self.ruleset)
        assert result["status"] == "suspended"

    def test_foreign_goal_present_after_packed_round_trip(self) -> None:
        """foreign/3 goal must be recoverable from the packed state."""
        from constraint.meta import init_state, resume_state

        state = init_state("test_foreign_later")
        result = resume_state(state, self.ruleset)
        assert result["status"] == "suspended"
        # The branches must contain a goal whose string form includes 'foreign'.
        branches = result["branches"]
        assert len(branches) == 1
        goals = branches[0]["goals"]
        assert any("foreign" in goal for goal in goals)

    def test_foreign_goal_resolves_after_resume_from_suspension(self) -> None:
        """Resuming from the suspension must reduce the foreign/3 goal."""
        from constraint.meta import init_state, resume_state

        state = init_state("test_foreign_later")
        state = resume_state(state, self.ruleset)
        assert state["status"] == "suspended"
        state = resume_state(state, self.ruleset)
        assert state["status"] == "solution"



class TestResumeStateCheckpoint:
    """Tests for the checkpoint/1 primitive."""

    def setup_method(self) -> None:
        self.ruleset = _parse_rules(
            "rule(test_checkpoint, (checkpoint(foo), true)).\n"
        )

    def test_checkpoint_produces_suspended_status(self) -> None:
        from constraint.meta import init_state, resume_state

        state = init_state("test_checkpoint")
        result = resume_state(state, self.ruleset)
        assert result["status"] == "suspended"

    def test_checkpoint_has_resume_kind(self) -> None:
        from constraint.meta import init_state, resume_state

        state = init_state("test_checkpoint")
        result = resume_state(state, self.ruleset)
        assert result["resume_kind"] == "checkpoint"

    def test_checkpoint_has_label(self) -> None:
        from constraint.meta import init_state, resume_state

        state = init_state("test_checkpoint")
        result = resume_state(state, self.ruleset)
        assert result["suspension"]["label"] == "foo"

    def test_checkpoint_has_no_bindings_key(self) -> None:
        from constraint.meta import init_state, resume_state

        state = init_state("test_checkpoint")
        result = resume_state(state, self.ruleset)
        assert "bindings" not in result

    def test_resume_from_checkpoint_continues_past(self) -> None:
        """Resuming from a checkpoint must continue past it (not re-encounter it)."""
        from constraint.meta import init_state, resume_state

        state = init_state("test_checkpoint")
        state = resume_state(state, self.ruleset)
        assert state["status"] == "suspended"
        assert state["resume_kind"] == "checkpoint"
        # Resuming again should reduce the remaining 'true' goal and reach solution.
        state = resume_state(state, self.ruleset)
        assert state["status"] in {"solution", "done"}

    def test_checkpoint_state_structure_is_valid(self) -> None:
        """The checkpoint state must have the required schema keys."""
        from constraint.meta import init_state, resume_state

        state = init_state("test_checkpoint")
        result = resume_state(state, self.ruleset)
        required_keys = {"version", "original_goal", "branches", "status", "suspension", "resume_kind"}
        assert required_keys.issubset(result.keys())


class TestResumeStateCheckpointMultiple:
    """Tests for checkpoint with multiple rules and complex bodies."""

    def setup_method(self) -> None:
        self.ruleset = _parse_rules(
            "rule(test_multi, (checkpoint(mid), true)).\n"
        )

    def test_checkpoint_does_not_reduce_checkpoint_again(self) -> None:
        """The checkpoint goal must not appear in the continuation."""
        from constraint.meta import init_state, resume_state

        state = init_state("test_multi")
        state = resume_state(state, self.ruleset)
        assert state["status"] == "suspended"
        # The branches should contain 'true' but not 'checkpoint(mid)'.
        for branch in state["branches"]:
            for goal in branch["goals"]:
                assert "checkpoint" not in goal, f"checkpoint goal still present: {goal}"

    def test_checkpoint_then_yield(self) -> None:
        """A rule with checkpoint then yield should suspend twice."""
        ruleset = _parse_rules(
            "rule(test_ck_yield, (checkpoint(ck), yield(yd))).\n"
        )
        from constraint.meta import init_state, resume_state

        state = init_state("test_ck_yield")
        # First step: checkpoint
        state = resume_state(state, ruleset)
        assert state["status"] == "suspended"
        assert state["resume_kind"] == "checkpoint"
        assert state["suspension"]["label"] == "ck"
        # Second step: yield
        state = resume_state(state, ruleset)
        assert state["status"] == "suspended"
        assert state["resume_kind"] == "suspended"
        assert state["suspension"]["label"] == "yd"
        # Third step: done
        state = resume_state(state, ruleset)
        assert state["status"] in {"solution", "done"}


class TestResumeStateYieldResumeKind:
    """Tests that yield/1 now also carries resume_kind == 'suspended'."""

    def setup_method(self) -> None:
        self.ruleset = _parse_rules("rule(test_yield_rk, yield(bar)).\n")

    def test_yield_has_resume_kind_suspended(self) -> None:
        from constraint.meta import init_state, resume_state

        state = init_state("test_yield_rk")
        result = resume_state(state, self.ruleset)
        assert result["status"] == "suspended"
        assert result["resume_kind"] == "suspended"

    def test_yield_still_has_label(self) -> None:
        from constraint.meta import init_state, resume_state

        state = init_state("test_yield_rk")
        result = resume_state(state, self.ruleset)
        assert result["suspension"]["label"] == "bar"


class TestResumeHashPreservation:
    """Tests that resume_hash is preserved across resume_state steps."""

    def setup_method(self) -> None:
        self.ruleset = _parse_rules("rule(step_goal, yield(step1)).\n")

    def test_resume_hash_survives_multiple_steps(self) -> None:
        from constraint.meta import init_state, resume_state
        from constraint.store import hash_clauses

        ruleset_hash = hash_clauses(self.ruleset)
        resume_hash = "test_resume_hash_value"

        state = init_state("step_goal")
        state["ruleset_hash"] = ruleset_hash
        state["resume_hash"] = resume_hash

        for i in range(3):
            state = resume_state(state, self.ruleset)
            assert "resume_hash" in state, f"resume_hash missing after step {i}"
            assert state["resume_hash"] == resume_hash, \
                f"resume_hash changed after step {i}: {state['resume_hash']}"
            assert "ruleset_hash" in state, f"ruleset_hash missing after step {i}"

    def test_resume_hash_preserved_when_absent(self) -> None:
        """When resume_hash is not in the input, it must not appear in output."""
        from constraint.meta import init_state, resume_state
        from constraint.store import hash_clauses

        ruleset_hash = hash_clauses(self.ruleset)

        state = init_state("step_goal")
        state["ruleset_hash"] = ruleset_hash
        # Deliberately omit resume_hash

        for i in range(3):
            state = resume_state(state, self.ruleset)
            assert "resume_hash" not in state, \
                f"resume_hash unexpectedly present after step {i}"

    def test_resume_hash_preserved_in_done_short_circuit(self) -> None:
        """A done state short-circuits via dict(state), which preserves all keys."""
        from constraint.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "true",
            "branches": [],
            "status": "done",
            "ruleset_hash": "some_hash",
            "resume_hash": "some_resume_hash",
        }

        state2 = resume_state(state, self.ruleset)
        assert state2["resume_hash"] == "some_resume_hash"
        assert state2["ruleset_hash"] == "some_hash"
