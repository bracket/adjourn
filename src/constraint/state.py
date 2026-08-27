"""State construction and ruleset-hash resolution for the constraint package.

This module provides pure-Python functions for constructing initial state
dicts and resolving ruleset names to content hashes.  It does **not** import
``janus_swi``, ``constraint.meta``, or ``constraint.runner``.

Public functions:

- :func:`init_state` — build a v0 state dict with both ``ruleset_hash`` and
  ``resume_hash`` stamped.
- :func:`set_resume_hash` — set or update ``resume_hash`` on an existing state.
- :func:`resolve_ruleset_hash` — resolve a ruleset name/alias/hash to a known
  content hash via a store and config.
"""

from __future__ import annotations

from typing import Any

from constraint.config import Config
from constraint.store import AggregateRuleSetStore, StoreInfo


def resolve_ruleset_hash(
    ruleset_name: str,
    store: AggregateRuleSetStore,
    config: Config,
) -> str:
    """Resolve *ruleset_name* to a known ruleset content hash.

    Resolution order (same as the original CLI helper):

    1. ``@``-prefixed system alias (``@top``, ``@first``).
    2. Per-store name (configured ``name`` field on a store entry).
    3. Config alias (``config.aliases``).
    4. Raw hash string.

    The resolved hash is validated via ``store.owns()``.

    Args:
        ruleset_name: A ruleset alias, store name, ``@``-prefixed system
            alias, or raw 64-character hex hash.
        store: The aggregate ruleset store to validate against.
        config: The project configuration (used for alias resolution).

    Returns:
        The validated ruleset content hash as a hex string.

    Raises:
        ValueError: If *ruleset_name* cannot be resolved to a hash known to
            *store*.
    """
    if ruleset_name.startswith("@"):
        ruleset_hash = _resolve_system_alias(ruleset_name, store)
    elif (store_name_hash := _resolve_store_name_hash(ruleset_name, store)) is not None:
        ruleset_hash = store_name_hash
    elif ruleset_name in config.aliases:
        ruleset_hash = config.alias_hash(ruleset_name)
    else:
        ruleset_hash = ruleset_name
    if not store.owns(ruleset_hash):
        raise ValueError(
            f"Unknown ruleset '{ruleset_name}': not a configured alias or known hash"
        )
    return ruleset_hash


def _resolve_system_alias(
    name: str,
    store: AggregateRuleSetStore,
) -> str:
    """Resolve a reserved system alias to a ruleset hash."""
    if name == "@top":
        return store.ruleset_hash
    if name != "@first":
        raise ValueError(f"Unknown system alias: {name}")
    first_store_hash = _first_non_system_store_hash(store)
    if first_store_hash is None:
        raise ValueError("System alias '@first' requires at least one configured store")
    return first_store_hash


def _first_non_system_store_hash(store: AggregateRuleSetStore) -> str | None:
    """Return the hash of the first configured non-system store."""
    for store_info in store.store_info_list():
        if store_info.type != "system":
            return store_info.hash
    return None


def _resolve_store_name_hash(
    ruleset_name: str,
    store: AggregateRuleSetStore,
) -> str | None:
    """Resolve a configured per-store name to its ruleset hash."""
    for store_info in store.store_info_list():
        if store_info.name == ruleset_name:
            return store_info.hash
    return None


def init_state(
    goal: str,
    ruleset_name: str,
    store: AggregateRuleSetStore,
    config: Config,
) -> dict[str, Any]:
    """Construct the initial state dict for the given goal and ruleset.

    This is a pure-Python operation; it does **not** invoke Prolog.

    The returned state has both ``ruleset_hash`` and ``resume_hash`` set to
    the resolved ruleset content hash.

    Args:
        goal: A Prolog term as a string, e.g. ``"color(X, Y)"``.
        ruleset_name: A ruleset alias, store name, ``@``-prefixed system
            alias, or raw 64-character hex hash.
        store: The aggregate ruleset store used to resolve the hash.
        config: The project configuration used for alias resolution.

    Returns:
        A v0 state dictionary with the following keys:

        - ``version`` (int): schema version, always ``0``.
        - ``original_goal`` (str): the *goal* string, unchanged.
        - ``branches`` (list[dict]): one-element list ``[{"goals": [goal]}]``.
        - ``status`` (str): always ``"running"``.
        - ``ruleset_hash`` (str): the resolved ruleset content hash.
        - ``resume_hash`` (str): same as ``ruleset_hash``.
    """
    h = resolve_ruleset_hash(ruleset_name, store, config)
    return {
        "version": 0,
        "original_goal": goal,
        "branches": [{"goals": [goal]}],
        "status": "running",
        "ruleset_hash": h,
        "resume_hash": h,
    }


def set_resume_hash(
    state: dict[str, Any],
    ruleset_name: str,
    store: AggregateRuleSetStore,
    config: Config,
) -> dict[str, Any]:
    """Set or update the ``resume_hash`` on *state*.

    Resolves *ruleset_name* to a content hash and stamps
    ``state["resume_hash"]`` with it.  The input *state* is modified in
    place and also returned.

    This is a blind set: no check is performed that the incoming state has
    ``ruleset_hash`` or any other field.

    Args:
        state: A v0 state dictionary (any existing keys are preserved).
        ruleset_name: A ruleset alias, store name, ``@``-prefixed system
            alias, or raw 64-character hex hash.
        store: The aggregate ruleset store used to resolve the hash.
        config: The project configuration used for alias resolution.

    Returns:
        The *state* dict with ``resume_hash`` set.
    """
    h = resolve_ruleset_hash(ruleset_name, store, config)
    state["resume_hash"] = h
    return state
