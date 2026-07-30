"""Runner class for driving the constraint meta-interpreter.

The :class:`Runner` encapsulates a :class:`~constraint.store.RuleSetStore`
and provides a step-one-step method that reads a pinned ruleset hash from
a state dictionary, resolves clauses via the store, and calls
:func:`~constraint.meta.resume_state` to produce the next state.

The class is an implicit singleton controlled via ``__new__``.  A module-level
instance holder and an override flag (``RUNNER_ALWAYS_FORCE_NEW``) govern
whether a new instance is allocated or a cached one is returned.
"""

from __future__ import annotations

import logging
from typing import Any

from constraint.meta import resume_state
from constraint.state_store import JsonFileStateStore
from constraint.store import RuleSetStore

_logger = logging.getLogger(__name__)

#: Module-global holder for the singleton Runner instance.
instance_: Runner | None = None

#: When set to ``True``, every ``Runner()`` construction forces a fresh
#: allocation regardless of the per-call ``force_new`` parameter.
#: Intended for test use only.
RUNNER_ALWAYS_FORCE_NEW: bool = False


class Runner:
    """Drive one step of the constraint meta-interpreter through a store.

    Holds a :class:`~constraint.store.RuleSetStore` and provides a
    :meth:`step` method that reads the pinned ruleset hash from a state
    dict, resolves clauses via the store, calls ``resume_state``, and
    returns the next state dict.

    Construction is an implicit singleton -- see ``__new__``.

    Args:
        store: A :class:`~constraint.store.RuleSetStore` instance used to
            resolve clauses for a given ruleset hash.
    """

    def __new__(cls, *args: Any, force_new: bool = False, **kwargs: Any) -> Runner:
        global instance_
        # The override flag takes absolute precedence.
        effective_force = RUNNER_ALWAYS_FORCE_NEW or force_new

        if instance_ is not None and effective_force:
            Runner.reset_instance()

        if instance_ is not None:
            # Return the cached instance.  Warn if constructor arguments
            # differ from those the cached instance was built with.
            cached_args = instance_._construction_args
            if args != cached_args.get("args") or kwargs != cached_args.get("kwargs"):
                _logger.warning(
                    "Returning cached Runner instance, but constructor "
                    "arguments differ.  Passed args=%r, kwargs=%r; "
                    "cached instance was built with args=%r, kwargs=%r.",
                    args,
                    kwargs,
                    cached_args.get("args"),
                    cached_args.get("kwargs"),
                )
            return instance_

        # Allocate a fresh instance and install it as the global singleton.
        new_instance = super().__new__(cls)
        instance_ = new_instance
        return new_instance

    def __init__(self, store: RuleSetStore, **kwargs: Any) -> None:
        # Guard against re-initialisation when __new__ returns a cached
        # instance.  If we already have attrs, the cached instance was
        # returned and we must not clobber its original state.
        if hasattr(self, "_store"):
            return

        self._store = store
        self._state_store = JsonFileStateStore()
        # Retain construction arguments for the differing-args warning.
        self._construction_args: dict[str, Any] = {
            "args": (store,),
            "kwargs": {},
        }

    @classmethod
    def reset_instance(cls) -> None:
        """Tear down the current singleton and null the module-level holder.

        The teardown body is intentionally empty in this phase.  After this
        call, subsequent ``Runner()`` constructions will create a fresh
        instance.
        """
        # Teardown (empty body in this phase).
        global instance_
        instance_ = None

    def step(self, state: dict[str, Any]) -> dict[str, Any]:
        """Drive one meta-interpreter step using the held store.

        Reads the pinned ruleset hash from *state* (under the key
        ``"ruleset_hash"``), resolves the clauses via the held store, calls
        :func:`~constraint.meta.resume_state`, and returns the updated state
        dict.

        Args:
            state: A v0 state dictionary containing at minimum
                ``"ruleset_hash"`` (a non-empty ``str``).

        Returns:
            An updated v0 state dictionary as returned by ``resume_state``.

        Raises:
            KeyError: If *state* does not contain ``"ruleset_hash"``.
        """
        ruleset_hash: str = state["ruleset_hash"]
        clauses = self._store.clauses_for(ruleset_hash)
        return resume_state(state, clauses)

    def set_state_store(self, seam: Any) -> None:
        """Install a state-storage seam.

        The *seam* must provide both ``store_state`` and ``load_state``
        methods (and ``store_init_state``) so the store and load halves
        can never be set independently.

        Args:
            seam: An object implementing the state-store interface.
        """
        self._state_store = seam

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Drive the resume loop from *state* until a terminal or suspend.

        Loops calling :meth:`step`:

        - On a **checkpoint** boundary (``resume_kind == "checkpoint"``):
          stores the state via ``store_state(label, state)`` and continues.
        - On a **suspend** boundary (``resume_kind == "suspended"``):
          stores the state via ``store_state(label, state)`` and returns it.
        - On ``"solution"`` or ``"done"``: returns the final state.
        - On any exception: lets it propagate (no serialization on failure).

        Args:
            state: A v0 state dictionary.

        Returns:
            The final state dict (solution, done, or suspended).
        """

        while True:
            next_state = self.step(state)
            status = next_state.get("status")
            resume_kind = next_state.get("resume_kind")

            if resume_kind == "checkpoint":
                label = next_state["suspension"]["label"]
                self._state_store.store_state(label, next_state)
                state = next_state
                continue

            if resume_kind == "suspended":
                label = next_state["suspension"]["label"]
                self._state_store.store_state(label, next_state)
                return next_state

            if status in ("solution", "done"):
                return next_state

            state = next_state
