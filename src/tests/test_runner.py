"""Tests for the Runner singleton semantics."""

import logging

import pytest

import constraint.runner as runner_mod
from constraint.runner import Runner


# Lightweight stand-ins for RuleSetStore.
# Only identity and equality matter for these tests.
class _StubStore:
    """Minimal store stand-in that exercises construction identity."""

    def __init__(self, label: str = "") -> None:
        self.label = label

    def clauses_for(self, hash_val: str) -> list:
        return []


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
