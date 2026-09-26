"""Tests for the Runner singleton semantics."""

import logging
from typing import Any

import pytest

import adjourn.runner as runner_mod
from adjourn.runner import Runner


# Lightweight stand-ins for RuleSetStore.
# Only identity and equality matter for these tests.
class _StubStore:
    """Minimal store stand-in that exercises construction identity."""

    def __init__(self, label: str = "") -> None:
        self.label = label

    def clauses_for(self, hash_val: str) -> list:
        return []




class _RecordingStore:
    """Minimal store stand-in that records the hash passed to ``clauses_for``."""

    def __init__(self, label: str = "") -> None:
        self.label = label
        self.called_with: str | None = None

    def clauses_for(self, hash_val: str) -> list:
        self.called_with = hash_val
        return []
class _RecordingSeam:
    """Recording seam that captures calls for test assertions."""

    def __init__(self) -> None:
        self.stored: list[tuple[str, dict]] = []
        self.init_state: dict | None = None

    def store_state(self, name: str, state: dict) -> None:
        self.stored.append((name, state))

    def load_state(self, name: str) -> dict:
        return {}

    def store_init_state(self, state: dict) -> None:
        self.init_state = state


STORE_A = _StubStore("A")
STORE_B = _StubStore("B")


@pytest.fixture
def cached_behavior() -> None:
    """Temporarily disable ``RUNNER_ALWAYS_FORCE_NEW`` so the
    singleton caches and reuses instances.

    Must be used before the first ``Runner()`` construction in a test.
    """
    runner_mod.RUNNER_ALWAYS_FORCE_NEW = False
    Runner.reset_instance()
    yield
    # Restore the autouse default.
    runner_mod.RUNNER_ALWAYS_FORCE_NEW = True
    Runner.reset_instance()


class TestRunnerSingleton:
    """Singleton-construction semantics of ``Runner``."""

    def test_cached_instance_returned(self, cached_behavior: None) -> None:
        """With ``RUNNER_ALWAYS_FORCE_NEW`` off, repeated no-flag
        construction returns the **same** instance (``is``)."""
        r1 = Runner(STORE_A)
        r2 = Runner(STORE_A)
        assert r1 is r2

    def test_force_new_yields_distinct_instance(
        self, cached_behavior: None
    ) -> None:
        """``force_new=True`` produces a distinct instance that
        becomes the new global singleton."""
        r_original = Runner(STORE_A)

        r_forced = Runner(STORE_B, force_new=True)
        assert r_forced is not r_original

        # Subsequent non-forced construction returns the forced instance.
        r_next = Runner(STORE_B)
        assert r_next is r_forced

    def test_runner_always_force_new_overrides(self) -> None:
        """With ``RUNNER_ALWAYS_FORCE_NEW = True`` every construction
        yields a fresh instance, regardless of the per-call flag."""
        r1 = Runner(STORE_A)
        r2 = Runner(STORE_A)  # force_new=False by default
        assert r1 is not r2

        r3 = Runner(STORE_A, force_new=True)
        assert r3 is not r2

    def test_reset_instance_creates_fresh_instance(
        self, cached_behavior: None
    ) -> None:
        """After ``reset_instance()`` the next construction allocates
        anew (not identical to the pre-reset instance)."""
        r_before = Runner(STORE_A)

        Runner.reset_instance()
        r_after = Runner(STORE_A)

        assert r_after is not r_before

    def test_differing_args_logs_warning(
        self, cached_behavior: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A cached-singleton construction with differing constructor
        arguments logs a warning.  The cached instance is still
        returned, and its retained args remain the original ones."""
        caplog.set_level(logging.WARNING)

        # First construction with STORE_A.
        r_first = Runner(STORE_A)
        original_store = r_first._store

        # Second construction with a different store.
        r_second = Runner(STORE_B)

        # The cached instance is returned.
        assert r_second is r_first

        # Its store is still the original one, not STORE_B.
        assert r_second._store is original_store
        assert r_second._store is STORE_A

        # A warning was logged about the differing arguments.
        assert len(caplog.records) >= 1
        warning_record = caplog.records[0]
        assert warning_record.levelno == logging.WARNING
        assert "differ" in warning_record.message.lower()
        assert "Runner" in warning_record.message

    def test_state_store_survives_cached_construction(
        self, cached_behavior: None
    ) -> None:
        """The ``_state_store`` attribute set on first init survives
        a cached-instance construction (re-init guard)."""
        r1 = Runner(STORE_A)
        original_state_store = r1._state_store

        # Second construction returns the cached instance.
        r2 = Runner(STORE_B)

        assert r2 is r1
        assert r2._state_store is original_state_store


class TestRunnerStep:
    """Tests for the ``step`` method (renamed from ``drive``)."""

    def test_step_raises_on_empty_ruleset(self) -> None:
        """``step`` with a stub store (empty clauses) raises
        ``ValueError``, matching the old ``drive`` behaviour."""
        runner = Runner(STORE_A)
        state = {"ruleset_hash": "abc", "status": "running"}
        with pytest.raises(ValueError, match="empty ruleset"):
            runner.step(state)




    def test_step_uses_resume_hash_when_present(self) -> None:
        """When ``resume_hash`` is present in state, ``step`` resolves
        clauses using the ``resume_hash`` value, not ``ruleset_hash``."""
        store = _RecordingStore("rec")
        runner = Runner(store)
        state = {"ruleset_hash": "abc", "resume_hash": "xyz", "status": "running"}
        with pytest.raises(ValueError, match="empty ruleset"):
            runner.step(state)
        assert store.called_with == "xyz"

    def test_step_uses_ruleset_hash_when_resume_hash_absent(self) -> None:
        """When ``resume_hash`` is absent, ``step`` resolves clauses
        using ``ruleset_hash``."""
        store = _RecordingStore("rec")
        runner = Runner(store)
        state = {"ruleset_hash": "abc", "status": "running"}
        with pytest.raises(ValueError, match="empty ruleset"):
            runner.step(state)
        assert store.called_with == "abc"

    def test_step_passes_empty_resume_hash_through(self) -> None:
        """A present-but-empty ``resume_hash`` (``""``) is passed through
        to the store rather than falling back to ``ruleset_hash``."""
        store = _RecordingStore("rec")
        runner = Runner(store)
        state = {"ruleset_hash": "abc", "resume_hash": "", "status": "running"}
        with pytest.raises(ValueError, match="empty ruleset"):
            runner.step(state)
        assert store.called_with == ""


class TestRunnerStateStore:
    """Tests for state-seam injection."""

    def test_default_state_store_is_json(self) -> None:
        """A freshly constructed Runner has a ``JsonFileStateStore``
        as its default state store."""
        runner = Runner(STORE_A)
        from adjourn.state_store import JsonFileStateStore
        assert isinstance(runner._state_store, JsonFileStateStore)

    def test_set_state_store_replaces_seam(self) -> None:
        """``set_state_store`` replaces the state-storage seam."""
        runner = Runner(STORE_A)
        seam = _RecordingSeam()
        runner.set_state_store(seam)
        assert runner._state_store is seam

    def test_seam_injectable_at_construction(self) -> None:
        """The seam can be injected after construction via
        ``set_state_store``."""
        runner = Runner(STORE_A)
        seam = _RecordingSeam()
        runner.set_state_store(seam)
        runner._state_store.store_state("test", {"key": "val"})
        assert seam.stored == [("test", {"key": "val"})]


class TestRunnerRun:
    """Tests for the ``run`` resume loop."""

    def test_run_continues_on_checkpoint(self) -> None:
        """``run`` continues the loop on a checkpoint boundary and
        stores the state with the checkpoint label."""
        runner = Runner(STORE_A)
        seam = _RecordingSeam()
        runner.set_state_store(seam)

        # We need to mock step to return a checkpoint state first,
        # then a solution.  We'll monkey-patch step on the runner.
        checkpoint_state = {
            "ruleset_hash": "abc",
            "status": "suspended",
            "resume_kind": "checkpoint",
            "suspension": {"label": "cp1"},
        }
        solution_state = {
            "ruleset_hash": "abc",
            "status": "solution",
            "bindings": {},
        }

        calls = iter([checkpoint_state, solution_state])

        def mock_step(state):
            return next(calls)

        runner.step = mock_step  # type: ignore[assignment]

        initial = {"ruleset_hash": "abc", "status": "running"}
        result = runner.run(initial)

        assert result is solution_state
        assert seam.stored == [("cp1", checkpoint_state)]

    def test_run_halts_on_suspend(self) -> None:
        """``run`` halts on a suspend boundary, stores the state,
        and returns the suspended state."""
        runner = Runner(STORE_A)
        seam = _RecordingSeam()
        runner.set_state_store(seam)

        suspended_state = {
            "ruleset_hash": "abc",
            "status": "suspended",
            "resume_kind": "suspended",
            "suspension": {"label": "sus1"},
        }

        def mock_step(state):
            return suspended_state

        runner.step = mock_step  # type: ignore[assignment]

        initial = {"ruleset_hash": "abc", "status": "running"}
        result = runner.run(initial)

        assert result is suspended_state
        assert seam.stored == [("sus1", suspended_state)]

    def test_run_stops_on_solution(self) -> None:
        """``run`` stops and returns the solution state."""
        runner = Runner(STORE_A)
        seam = _RecordingSeam()
        runner.set_state_store(seam)

        solution_state = {
            "ruleset_hash": "abc",
            "status": "solution",
            "bindings": {},
        }

        def mock_step(state):
            return solution_state

        runner.step = mock_step  # type: ignore[assignment]

        initial = {"ruleset_hash": "abc", "status": "running"}
        result = runner.run(initial)

        assert result is solution_state
        assert seam.stored == []  # No checkpoint/suspend to store

    def test_run_stops_on_done(self) -> None:
        """``run`` stops and returns the done state."""
        runner = Runner(STORE_A)
        seam = _RecordingSeam()
        runner.set_state_store(seam)

        done_state = {
            "ruleset_hash": "abc",
            "status": "done",
        }

        def mock_step(state):
            return done_state

        runner.step = mock_step  # type: ignore[assignment]

        initial = {"ruleset_hash": "abc", "status": "running"}
        result = runner.run(initial)

        assert result is done_state
        assert seam.stored == []

    def test_run_propagates_exception(self) -> None:
        """``run`` lets exceptions propagate without serializing."""
        runner = Runner(STORE_A)
        seam = _RecordingSeam()
        runner.set_state_store(seam)

        def mock_step(state):
            raise RuntimeError("step failed")

        runner.step = mock_step  # type: ignore[assignment]

        initial = {"ruleset_hash": "abc", "status": "running"}
        with pytest.raises(RuntimeError, match="step failed"):
            runner.run(initial)

        # Init state should still have been written.
        # No checkpoint/suspend stores should have happened.
        assert seam.stored == []

    def test_run_multiple_checkpoints(self) -> None:
        """``run`` handles multiple consecutive checkpoints before
        reaching a terminal state."""
        runner = Runner(STORE_A)
        seam = _RecordingSeam()
        runner.set_state_store(seam)

        cp1 = {
            "ruleset_hash": "abc",
            "status": "suspended",
            "resume_kind": "checkpoint",
            "suspension": {"label": "cp1"},
        }
        cp2 = {
            "ruleset_hash": "abc",
            "status": "suspended",
            "resume_kind": "checkpoint",
            "suspension": {"label": "cp2"},
        }
        done = {
            "ruleset_hash": "abc",
            "status": "done",
        }

        calls = iter([cp1, cp2, done])

        def mock_step(state):
            return next(calls)

        runner.step = mock_step  # type: ignore[assignment]

        initial = {"ruleset_hash": "abc", "status": "running"}
        result = runner.run(initial)

        assert result is done
        assert seam.stored == [("cp1", cp1), ("cp2", cp2)]


class TestRunnerRunIntegration:
    """End-to-end integration tests for the ``run`` resume loop
    with a real ruleset driving the meta-interpreter."""

    def test_run_checkpoint_then_yield(self, tmp_path):
        """``run`` with a ruleset containing checkpoint then yield:
        - auto-continues across the checkpoint (does not halt there)
        - store_state is invoked at the checkpoint boundary with the label
        - halts at the yield suspension
        - init state was written at run start
        """
        from adjourn.store import FileRuleSetStore
