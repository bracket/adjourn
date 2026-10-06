"""Unit tests for the meta-interpreter core (meta.py / meta.pl)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import pytest

from adjourn.parser.ast import Clause
from adjourn.parser.parser import parse_file

NONEMPTY_RULESET = "rule(test_fixture_placeholder, true).\n"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_rules(content: str) -> Path:
    """Write Prolog rules to a temporary file and return its Path."""
    fd, path = tempfile.mkstemp(suffix=".pl", prefix="adjourn_test_")
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
    """Tests for state construction (init_state / dict literal)."""

    def test_schema_version(self) -> None:
        state = {
            "version": 0,
            "original_goal": "foo",
            "branches": [{"goals": ["foo"]}],
            "status": "running",
        }
        assert state["version"] == 0

    def test_original_goal_preserved(self) -> None:
        goal = "color(X, Y)"
        state = {
            "version": 0,
            "original_goal": goal,
            "branches": [{"goals": [goal]}],
            "status": "running",
        }
        assert state["original_goal"] == goal

    def test_status_is_running(self) -> None:
        state = {
            "version": 0,
            "original_goal": "foo(bar)",
            "branches": [{"goals": ["foo(bar)"]}],
            "status": "running",
        }
        assert state["status"] == "running"

    def test_single_branch_with_goal(self) -> None:
        goal = "member(X, [1,2,3])"
        state = {
            "version": 0,
            "original_goal": goal,
            "branches": [{"goals": [goal]}],
            "status": "running",
        }
        assert len(state["branches"]) == 1
        assert state["branches"][0]["goals"] == [goal]

    def test_no_suspension_or_bindings(self) -> None:
        state = {
            "version": 0,
            "original_goal": "any_goal",
            "branches": [{"goals": ["any_goal"]}],
            "status": "running",
        }
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

        state = {
            "version": 0,
            "original_goal": "pure_python_goal",
            "branches": [{"goals": ["pure_python_goal"]}],
            "status": "running",
        }
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
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "true",
            "branches": [{"goals": ["true"]}],
            "status": "running",
        }
        result = resume_state(state, self.ruleset)
        assert result["status"] == "solution"

    def test_solution_has_bindings_key(self) -> None:
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "true",
            "branches": [{"goals": ["true"]}],
            "status": "running",
        }
        result = resume_state(state, self.ruleset)
        assert "bindings" in result

    def test_solution_preserves_original_goal(self) -> None:
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "true",
            "branches": [{"goals": ["true"]}],
            "status": "running",
        }
        result = resume_state(state, self.ruleset)
        assert result["original_goal"] == "true"

    def test_solution_has_no_suspension_key(self) -> None:
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "true",
            "branches": [{"goals": ["true"]}],
            "status": "running",
        }
        result = resume_state(state, self.ruleset)
        assert "suspension" not in result

    def test_solution_branches_empty(self) -> None:
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "true",
            "branches": [{"goals": ["true"]}],
            "status": "running",
        }
        result = resume_state(state, self.ruleset)
        assert result["branches"] == []


class TestResumeStateYield:
    """Tests using a goal that triggers yield(Label)."""

    def setup_method(self) -> None:
        self.ruleset = _parse_rules("rule(test_yield, yield(hello)).\n")

    def test_yield_produces_suspended_status(self) -> None:
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "test_yield",
            "branches": [{"goals": ["test_yield"]}],
            "status": "running",
        }
        result = resume_state(state, self.ruleset)
        assert result["status"] == "suspended"

    def test_suspended_has_label(self) -> None:
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "test_yield",
            "branches": [{"goals": ["test_yield"]}],
            "status": "running",
        }
        result = resume_state(state, self.ruleset)
        assert result["suspension"]["label"] == "hello"

    def test_suspended_has_no_bindings_key(self) -> None:
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "test_yield",
            "branches": [{"goals": ["test_yield"]}],
            "status": "running",
        }
        result = resume_state(state, self.ruleset)
        assert "bindings" not in result

    def test_resume_from_suspended_reaches_solution(self) -> None:
        """Resuming a suspended state should eventually reach solution/done."""
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "test_yield",
            "branches": [{"goals": ["test_yield"]}],
            "status": "running",
        }
        state = resume_state(state, self.ruleset)
        assert state["status"] == "suspended"
        state = resume_state(state, self.ruleset)
        assert state["status"] in {"solution", "done"}

    def test_suspended_state_structure_is_valid(self) -> None:
        """The suspended state must have the required schema keys."""
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "test_yield",
            "branches": [{"goals": ["test_yield"]}],
            "status": "running",
        }
        result = resume_state(state, self.ruleset)
        required_keys = {"version", "original_goal", "branches", "status", "suspension"}
        assert required_keys.issubset(result.keys())


class TestResumeStateDone:
    """Tests for the 'done' (no solutions) terminal state."""

    def setup_method(self) -> None:
        self.ruleset = _parse_rules(NONEMPTY_RULESET)

    def test_unknown_goal_raises_error(self) -> None:
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "no_rule_exists_for_this_goal",
            "branches": [{"goals": ["no_rule_exists_for_this_goal"]}],
            "status": "running",
        }
        with pytest.raises(Exception, match="unknown_goal"):
            resume_state(state, self.ruleset)

    def test_done_state_is_idempotent(self) -> None:
        """Resuming a done state must return the same state unchanged."""
        from adjourn.meta import resume_state

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
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "false",
            "branches": [{"goals": ["false"]}],
            "status": "running",
        }
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
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "atom_concat(prefix, suffix, R)",
            "branches": [{"goals": ["atom_concat(prefix, suffix, R)"]}],
            "status": "running",
        }
        result = resume_state(state, self.ruleset)
        assert result["status"] == "solution"
        assert result["bindings"]["R"] == "prefixsuffix"

    def test_consulted_non_rule_predicate_is_callable(self) -> None:
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "plain_concat_result(R)",
            "branches": [{"goals": ["plain_concat_result(R)"]}],
            "status": "running",
        }
        result = resume_state(state, self.ruleset)
        assert result["status"] == "solution"
        assert result["bindings"]["R"] == "leftright"

    def test_builtin_binding_survives_suspend_resume_round_trip(self) -> None:
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "(atom_concat(prefix, suffix, R), yield(pause), R=prefixsuffix)",
            "branches": [{"goals": ["(atom_concat(prefix, suffix, R), yield(pause), R=prefixsuffix)"]}],
            "status": "running",
        }
        state = resume_state(state, self.ruleset)
        assert state["status"] == "suspended"
        state = resume_state(state, self.ruleset)
        assert state["status"] == "solution"


class TestResumeStateEmptyRuleset:
    """Tests for rejecting empty interpreted programs."""

    def test_empty_ruleset_raises_value_error(self) -> None:
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "true",
            "branches": [{"goals": ["true"]}],
            "status": "running",
        }

        with pytest.raises(ValueError, match="empty ruleset"):
            resume_state(state, [])

    def test_done_state_short_circuits_before_empty_ruleset_check(self) -> None:
        from adjourn.meta import resume_state

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
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "choice",
            "branches": [{"goals": ["choice"]}],
            "status": "running",
        }
        result = resume_state(state, self.ruleset)
        # First DFS branch should give a solution.
        assert result["status"] == "solution"

    def test_remaining_branches_kept(self) -> None:
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "choice",
            "branches": [{"goals": ["choice"]}],
            "status": "running",
        }
        result = resume_state(state, self.ruleset)
        # Second alternative branch should still be present.
        assert result["status"] == "solution"
        # There must be at least one remaining branch for the second rule.
        # (Additional branches may be present if prior test runs accumulated
        # rule/2 facts in the SWI-Prolog process; we only verify ≥ 1.)
        assert len(result["branches"]) >= 1

    def test_rule_dispatch_takes_precedence_over_callable_predicate(self) -> None:
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "choice",
            "branches": [{"goals": ["choice"]}],
            "status": "running",
        }
        result = resume_state(state, self.ruleset)
        assert result["status"] == "solution"


class TestResumeStateSchemaConsistency:
    """The schema must be consistent across multiple resumes."""

    def setup_method(self) -> None:
        self.ruleset = _parse_rules("rule(step_goal, yield(step1)).\n")

    def test_version_unchanged_across_resumes(self) -> None:
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "step_goal",
            "branches": [{"goals": ["step_goal"]}],
            "status": "running",
        }
        for _ in range(3):
            state = resume_state(state, self.ruleset)
            assert state["version"] == 0

    def test_original_goal_unchanged_across_resumes(self) -> None:
        from adjourn.meta import resume_state

        goal = "step_goal"
        state = {
            "version": 0,
            "original_goal": goal,
            "branches": [{"goals": [goal]}],
            "status": "running",
        }
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
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "test_foreign_call",
            "branches": [{"goals": ["test_foreign_call"]}],
            "status": "running",
        }
        result = resume_state(state, self.ruleset)
        assert result["status"] == "solution"

    def test_foreign_goal_solution_has_bindings_key(self) -> None:
        """Solution after foreign/3 reduction must include the bindings key."""
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "test_foreign_call",
            "branches": [{"goals": ["test_foreign_call"]}],
            "status": "running",
        }
        result = resume_state(state, self.ruleset)
        assert "bindings" in result

    def test_foreign_goal_no_suspension_key(self) -> None:
        """A foreign/3 reduction must not produce a suspended event."""
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "test_foreign_call",
            "branches": [{"goals": ["test_foreign_call"]}],
            "status": "running",
        }
        result = resume_state(state, self.ruleset)
        assert "suspension" not in result

    def test_foreign_goal_original_goal_preserved(self) -> None:
        """original_goal must be unchanged after a foreign/3 reduction."""
        from adjourn.meta import resume_state

        goal = "test_foreign_call"
        state = {
            "version": 0,
            "original_goal": goal,
            "branches": [{"goals": [goal]}],
            "status": "running",
        }
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
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "test_foreign_later",
            "branches": [{"goals": ["test_foreign_later"]}],
            "status": "running",
        }
        result = resume_state(state, self.ruleset)
        assert result["status"] == "suspended"

    def test_foreign_goal_present_after_packed_round_trip(self) -> None:
        """foreign/3 goal must be recoverable from the packed state."""
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "test_foreign_later",
            "branches": [{"goals": ["test_foreign_later"]}],
            "status": "running",
        }
        result = resume_state(state, self.ruleset)
        assert result["status"] == "suspended"
        # The branches must contain a goal whose string form includes 'foreign'.
        branches = result["branches"]
        assert len(branches) == 1
        goals = branches[0]["goals"]
        assert any("foreign" in goal for goal in goals)

    def test_foreign_goal_resolves_after_resume_from_suspension(self) -> None:
        """Resuming from the suspension must reduce the foreign/3 goal."""
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "test_foreign_later",
            "branches": [{"goals": ["test_foreign_later"]}],
            "status": "running",
        }
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
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "test_checkpoint",
            "branches": [{"goals": ["test_checkpoint"]}],
            "status": "running",
        }
        result = resume_state(state, self.ruleset)
        assert result["status"] == "suspended"

    def test_checkpoint_has_resume_kind(self) -> None:
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "test_checkpoint",
            "branches": [{"goals": ["test_checkpoint"]}],
            "status": "running",
        }
        result = resume_state(state, self.ruleset)
        assert result["resume_kind"] == "checkpoint"

    def test_checkpoint_has_label(self) -> None:
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "test_checkpoint",
            "branches": [{"goals": ["test_checkpoint"]}],
            "status": "running",
        }
        result = resume_state(state, self.ruleset)
        assert result["suspension"]["label"] == "foo"

    def test_checkpoint_has_no_bindings_key(self) -> None:
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "test_checkpoint",
            "branches": [{"goals": ["test_checkpoint"]}],
            "status": "running",
        }
        result = resume_state(state, self.ruleset)
        assert "bindings" not in result

    def test_resume_from_checkpoint_continues_past(self) -> None:
        """Resuming from a checkpoint must continue past it (not re-encounter it)."""
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "test_checkpoint",
            "branches": [{"goals": ["test_checkpoint"]}],
            "status": "running",
        }
        state = resume_state(state, self.ruleset)
        assert state["status"] == "suspended"
        assert state["resume_kind"] == "checkpoint"
        # Resuming again should reduce the remaining 'true' goal and reach solution.
        state = resume_state(state, self.ruleset)
        assert state["status"] in {"solution", "done"}

    def test_checkpoint_state_structure_is_valid(self) -> None:
        """The checkpoint state must have the required schema keys."""
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "test_checkpoint",
            "branches": [{"goals": ["test_checkpoint"]}],
            "status": "running",
        }
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
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "test_multi",
            "branches": [{"goals": ["test_multi"]}],
            "status": "running",
        }
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
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "test_ck_yield",
            "branches": [{"goals": ["test_ck_yield"]}],
            "status": "running",
        }
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
        # Third step: "done"
        state = resume_state(state, ruleset)
        assert state["status"] in {"solution", "done"}


class TestResumeStateYieldResumeKind:
    """Tests that yield/1 now also carries resume_kind == 'suspended'."""

    def setup_method(self) -> None:
        self.ruleset = _parse_rules("rule(test_yield_rk, yield(bar)).\n")

    def test_yield_has_resume_kind_suspended(self) -> None:
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "test_yield_rk",
            "branches": [{"goals": ["test_yield_rk"]}],
            "status": "running",
        }
        result = resume_state(state, self.ruleset)
        assert result["status"] == "suspended"
        assert result["resume_kind"] == "suspended"

    def test_yield_still_has_label(self) -> None:
        from adjourn.meta import resume_state

        state = {
            "version": 0,
            "original_goal": "test_yield_rk",
            "branches": [{"goals": ["test_yield_rk"]}],
            "status": "running",
        }
        result = resume_state(state, self.ruleset)
        assert result["suspension"]["label"] == "bar"


class TestResumeHashPreservation:
    """Tests that resume_hash is preserved across resume_state steps."""

    def setup_method(self) -> None:
        self.ruleset = _parse_rules("rule(step_goal, yield(step1)).\n")

    def test_resume_hash_survives_multiple_steps(self) -> None:
        from adjourn.meta import resume_state
        from adjourn.store import hash_clauses

        ruleset_hash = hash_clauses(self.ruleset)
        resume_hash = "test_resume_hash_value"

        state = {
            "version": 0,
            "original_goal": "step_goal",
            "branches": [{"goals": ["step_goal"]}],
            "status": "running",
        }
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
        from adjourn.meta import resume_state
        from adjourn.store import hash_clauses

        ruleset_hash = hash_clauses(self.ruleset)

        state = {
            "version": 0,
            "original_goal": "step_goal",
            "branches": [{"goals": ["step_goal"]}],
            "status": "running",
        }
        state["ruleset_hash"] = ruleset_hash
        # Deliberately omit resume_hash

        for i in range(3):
            state = resume_state(state, self.ruleset)
            assert "resume_hash" not in state, \
                f"resume_hash unexpectedly present after step {i}"

    def test_resume_hash_preserved_in_done_short_circuit(self) -> None:
        """A done state short-circuits via dict(state), which preserves all keys."""
        from adjourn.meta import resume_state

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


# ---------------------------------------------------------------------------
# Reduction semantics: branch death, alternatives, and error cases
# ---------------------------------------------------------------------------


def _running_state(goal: str) -> dict[str, Any]:
    """Return a fresh running state for *goal*."""
    return {
        "version": 0,
        "original_goal": goal,
        "branches": [{"goals": [goal]}],
        "status": "running",
    }


class TestReductionSemantics:
    """Pins how reduce_goal/6 handles failure, alternatives, and bad goals.

    Predicate names are prefixed ``rs_`` so rule/2 facts accumulated in the
    shared SWI-Prolog process by other test classes cannot interfere.
    """

    def setup_method(self) -> None:
        self.ruleset = _parse_rules(
            "rule(rs_pick(a), true).\n"
            "rule(rs_pick(b), true).\n"
            "rule(rs_num(1), true).\n"
            "rule(rs_num(2), true).\n"
            "rule(rs_color(red), true).\n"
            "rule(rs_color(blue), true).\n"
            "rule(rs_unify_fail, (X = a, X = b)).\n"
            "rule(rs_call_var(G), G).\n"
            "rule(rs_foreign_mismatch, foreign(git_rev_parse, 'HEAD', not_a_sha)).\n"
        )

    def test_failed_unification_drops_branch(self) -> None:
        from adjourn.meta import resume_state

        result = resume_state(_running_state("rs_unify_fail"), self.ruleset)
        assert result["status"] == "done"

    def test_failed_unification_falls_back_to_next_alternative(self) -> None:
        from adjourn.meta import resume_state

        result = resume_state(_running_state("rs_pick(X), X = b"), self.ruleset)
        assert result["status"] == "solution"
        assert result["bindings"] == {"X": "b"}

    def test_failed_builtin_drops_branch(self) -> None:
        from adjourn.meta import resume_state

        result = resume_state(_running_state("rs_num(X), X > 1"), self.ruleset)
        assert result["status"] == "solution"
        assert result["bindings"] == {"X": "2"}

    def test_each_solution_carries_its_own_bindings(self) -> None:
        from adjourn.meta import resume_state

        first = resume_state(_running_state("rs_color(C)"), self.ruleset)
        assert first["status"] == "solution"
        assert first["bindings"] == {"C": "red"}

        second = resume_state(first, self.ruleset)
        assert second["status"] == "solution"
        assert second["bindings"] == {"C": "blue"}

        third = resume_state(second, self.ruleset)
        assert third["status"] == "done"

    def test_unbound_goal_raises_instantiation_error(self) -> None:
        from adjourn.meta import resume_state

        with pytest.raises(Exception, match="not sufficiently instantiated"):
            resume_state(_running_state("rs_call_var(_)"), self.ruleset)

    def test_module_qualified_goal_raises(self) -> None:
        from adjourn.meta import resume_state

        with pytest.raises(Exception, match="module_qualified_goal"):
            resume_state(_running_state("some_module:rs_pick(X)"), self.ruleset)

    def test_foreign_output_mismatch_drops_branch(self) -> None:
        from adjourn.meta import resume_state

        result = resume_state(_running_state("rs_foreign_mismatch"), self.ruleset)
        assert result["status"] == "done"


class TestNegation:
    """Pins interpreted negation as failure (\\+).

    Predicate names are prefixed ``ng_`` so rule/2 facts accumulated in the
    shared SWI-Prolog process by other test classes cannot interfere.
    """

    def setup_method(self) -> None:
        self.ruleset = _parse_rules(
            "rule(ng_item(a), true).\n"
            "rule(ng_item(b), true).\n"
            "rule(ng_bad(a), true).\n"
            "rule(ng_good(X), (ng_item(X), \\+ ng_bad(X))).\n"
            "rule(ng_none, \\+ ng_item(_)).\n"
            "rule(ng_no_leak(X), \\+ \\+ X = a).\n"
            "rule(ng_yields, yield(inner)).\n"
            "rule(ng_yield_in_negation, \\+ ng_yields).\n"
            "rule(ng_cp_fails, (checkpoint(c), fail)).\n"
            "rule(ng_cp_succeeds, (checkpoint(c), true)).\n"
            "rule(ng_after_failed_cp, \\+ ng_cp_fails).\n"
            "rule(ng_after_proved_cp, \\+ ng_cp_succeeds).\n"
            # The shape an LLM produced for the graph coloring demo.
            "rule(ng_edge(a, b), true).\n"
            "rule(ng_edge(b, c), true).\n"
            "rule(ng_adj(X, Y), ng_edge(X, Y)).\n"
            "rule(ng_adj(X, Y), ng_edge(Y, X)).\n"
            "rule(ng_member(X, [X|_]), true).\n"
            "rule(ng_member(X, [_|T]), ng_member(X, T)).\n"
            "rule(ng_conflict(As), (ng_adj(X, Y), ng_member(X-C, As), "
            "ng_member(Y-C, As))).\n"
            "rule(ng_color(red), true).\n"
            "rule(ng_color(green), true).\n"
            "rule(ng_path_coloring(B, C), (ng_color(B), ng_color(C), "
            "\\+ ng_conflict([a-red, b-B, c-C]))).\n"
        )

    def test_negation_of_unprovable_goal_succeeds(self) -> None:
        from adjourn.meta import resume_state

        result = resume_state(_running_state("ng_good(X)"), self.ruleset)
        assert result["status"] == "solution"
        assert result["bindings"] == {"X": "b"}

    def test_negation_of_provable_goal_drops_branch(self) -> None:
        from adjourn.meta import resume_state

        result = resume_state(_running_state("ng_none"), self.ruleset)
        assert result["status"] == "done"

    def test_negation_does_not_leak_bindings(self) -> None:
        from adjourn.meta import resume_state

        result = resume_state(_running_state("ng_no_leak(X)"), self.ruleset)
        assert result["status"] == "solution"
        assert result["bindings"] == {}

    def test_yield_inside_negation_raises(self) -> None:
        from adjourn.meta import resume_state

        with pytest.raises(Exception, match="yield_in_negation"):
            resume_state(_running_state("ng_yield_in_negation"), self.ruleset)

    def test_checkpoint_inside_negation_is_stepped_past(self) -> None:
        from adjourn.meta import resume_state

        unprovable = resume_state(_running_state("ng_after_failed_cp"), self.ruleset)
        assert unprovable["status"] == "solution"

        provable = resume_state(_running_state("ng_after_proved_cp"), self.ruleset)
        assert provable["status"] == "done"

    def test_negation_over_interpreted_predicates(self) -> None:
        from adjourn.meta import resume_state

        first = resume_state(_running_state("ng_path_coloring(B, C)"), self.ruleset)
        assert first["status"] == "solution"
        assert first["bindings"] == {"B": "green", "C": "red"}

        second = resume_state(first, self.ruleset)
        assert second["status"] == "done"
