"""Shared fixtures for the adjourn test suite."""

import pytest
import adjourn.runner as runner_mod
from adjourn.runner import Runner


@pytest.fixture(autouse=True)
def runner_isolation() -> None:
    """Ensure every test starts with a fresh Runner singleton.

    Sets ``RUNNER_ALWAYS_FORCE_NEW = True`` by default so that
    construction always produces a fresh instance unless a test
    explicitly opts out.  Also resets the singleton before and
    after the test to prevent state leaking between tests.
    """
    old_force_new = runner_mod.RUNNER_ALWAYS_FORCE_NEW
    runner_mod.RUNNER_ALWAYS_FORCE_NEW = True
    Runner.reset_instance()
    yield
    runner_mod.RUNNER_ALWAYS_FORCE_NEW = old_force_new
    Runner.reset_instance()
