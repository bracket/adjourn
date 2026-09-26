"""Meta-interpreter helpers for the constraint package.

This module provides Python-side helpers for driving the continuation-style
Prolog meta-interpreter defined in ``meta.pl``.  Two public functions are
exposed:

- :func:`init_state` — pure-Python constructor; no Prolog invocation.
- :func:`resume_state` — load a ruleset's clauses, call ``step/3`` once, return
  the updated state dict.

State file schema (v0)::

    {
        "version": 0,
        "original_goal": "<prolog term string>",
        "branches": [
            { "orig_goal": "<goal string>", "goals": ["<goal string>", ...] }
        ],
        "status": "running | suspended | solution | done",
        "suspension": { "label": "<term string>" },  # only when suspended
        "bindings": { "<var>": "<term string>" },    # only when solution
        "ruleset_hash": "<hash string>",             # optional; pinned ruleset hash
        "resume_hash": "<hash string>"               # optional; pinned override hash for resume
    }

Notes on variable bindings
--------------------------
Each branch carries its own copy of the original goal (``orig_goal``) whose
variables are shared with that branch's resolvent goals.  When a branch's
resolvent empties, ``meta.pl`` emits ``solution(SolvedOrigGoal)`` and
``step_packed/4`` recovers the bindings by unifying the top-level
``original_goal`` (which retains the user's variable names because it is
rebuilt from the state dict's string every step) against the solved branch's
bound goal.  Distinct branches therefore bind the goal's variables to distinct
values, and multi-solution goals yield one ``solution`` event per branch.
"""

from __future__ import annotations

import sys
import tempfile
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any

import janus_swi as janus  # type: ignore[import-untyped]

from constraint.parser.ast import Clause
from constraint.store import hash_clauses

# Track which files have already been consulted in this process to avoid
# redundant reloading (SWI-Prolog is stateful within a process).
_consulted: set[str] = set()
_loaded_ruleset_hash: str | None = None
_ruleset_file_path = Path(tempfile.gettempdir()) / "constraint_runtime_ruleset.pl"


def resume_state(state: dict[str, Any], clauses: list[Clause]) -> dict[str, Any]:
    """Load *clauses*, call ``step/3`` once, and return the updated state dict.

    Args:
        state: A v0 state dictionary as produced by :func:`init_state` or a
               previous call to :func:`resume_state`.
        clauses: Parsed Prolog clauses that define the interpreted program.

    Returns:
        An updated v0 state dictionary reflecting the result of one ``step/3``
        call.  The returned dict always contains the same top-level keys as the
        input (``version``, ``original_goal``, ``branches``, ``status``).
        ``ruleset_hash`` and ``resume_hash`` are preserved when present in the input state.
        ``suspension`` is added when ``status == "suspended"``.
        ``bindings`` is added when ``status == "solution"``.

    Raises:
        RuntimeError: If ``step_packed/4`` fails unexpectedly.  A goal that
                      exhausts all alternatives is reported as ``done``, not
                      an error.
    """
    if state.get("status") == "done":
        # Already exhausted — return unchanged.
        return dict(state)

    if not clauses:
        raise ValueError(
            "Cannot resume against an empty ruleset: the interpreted program "
            "has no clauses. An empty program cannot resolve any goal and is "
            "not a meaningful input."
        )

    _ensure_meta_loaded()
    _ensure_query_compiler_loaded()
    _ensure_ruleset_loaded(clauses)
    _ensure_foreign_loaded()

    packed = _build_packed_atom(state)
    result = janus.query_once(
        "step_packed(PA, EA, POA, BP)",
        {"PA": packed},
    )

    if not result or result.get("truth") is False:
        raise RuntimeError(f"step_packed/4 failed for packed atom: {packed!r}")

    event_atom: str = result["EA"]
    packed_out: str = result["POA"]
    binding_flat: list[str] = result.get("BP") or []

    return _build_new_state(state, event_atom, packed_out, binding_flat)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _ensure_meta_loaded() -> None:
    """Consult ``meta.pl`` into SWI-Prolog if not already loaded."""
    key = "<constraint_meta.pl>"
    if key in _consulted:
        return
    ref = files("constraint").joinpath("meta.pl")
    with as_file(ref) as pl_path:
        janus.consult(str(pl_path))
    _consulted.add(key)


def _ensure_query_compiler_loaded() -> None:
    """Consult ``query_compiler.pl`` into SWI-Prolog if not already loaded."""
    key = "<constraint_query_compiler.pl>"
    if key in _consulted:
        return
    ref = files("constraint").joinpath("query_compiler.pl")
    with as_file(ref) as pl_path:
        janus.consult(str(pl_path))
    _consulted.add(key)


def _ensure_foreign_loaded() -> None:
    """Register ``constraint_foreign`` in ``sys.modules`` for janus ``py_call``.

    The Prolog clause ``py_call(constraint_foreign:dispatch(Fn, In), Out)``
    resolves the module named ``constraint_foreign`` via Python's import
    machinery.  This function ensures the module is importable under that
    short name by registering it in ``sys.modules`` the first time it is
    needed.
    """
    if "constraint_foreign" not in sys.modules:
        import constraint.constraint_foreign as _cf
        sys.modules["constraint_foreign"] = _cf


def _ensure_ruleset_loaded(clauses: list[Clause]) -> None:
    """Load the user's ruleset clauses if not already loaded."""
    global _loaded_ruleset_hash

    ruleset_hash = hash_clauses(clauses)
    if _loaded_ruleset_hash == ruleset_hash:
        return

    _write_ruleset_file(clauses)
    janus.consult(str(_ruleset_file_path))
    _loaded_ruleset_hash = ruleset_hash


def _write_ruleset_file(clauses: list[Clause]) -> None:
    """Write the active ruleset clauses to the temp consult path."""
    content = "".join(f"{clause}\n" for clause in clauses) or "% empty ruleset\n"
    _ruleset_file_path.write_text(content, encoding="utf-8")


def _build_packed_atom(state: dict[str, Any]) -> str:
    """Build a ``constraint_meta_pack(OrigGoal, State)`` atom string.

    By combining the original goal and the state branches into a SINGLE Prolog
    term string, variable names that appear in both the original goal and the
    branch goals will refer to the same Prolog variable when the atom is
    parsed by SWI-Prolog's ``read_term_from_atom/3``.  This is the mechanism
    that allows variable binding extraction after a ``solution`` event (when
    the variable survives in the packed atom without going through
    ``findall`` copying).

    Args:
        state: A v0 state dictionary.

    Returns:
        Atom string of the form
        ``"constraint_meta_pack(<goal>, state([branch([...]), ...]))"``
    """
    orig_goal = state["original_goal"]
    branches = state.get("branches", [])
    branch_terms = []
    for branch in branches:
        # Each branch carries its OWN copy of the goal ("orig_goal") whose
        # variables are shared with that branch's resolvent goals.  This is
        # what lets distinct branches bind the goal's variables to distinct
        # values and have those bindings survive the pack round-trip.  Older
        # state dicts without "orig_goal" fall back to the top-level goal.
        branch_orig_goal = branch.get("orig_goal", orig_goal)
        goals = branch.get("goals", [])
        goals_list = "[" + ",".join(goals) + "]"
        # Parenthesise the goal: a goal whose principal functor is an operator
        # (e.g. a ','-conjunction, priority 1000) would otherwise be parsed as
        # extra arguments of branch/N when embedded in an argument position.
        branch_terms.append(f"branch(({branch_orig_goal}), {goals_list})")
    branches_list = "[" + ",".join(branch_terms) + "]"
    return f"constraint_meta_pack(({orig_goal}), state({branches_list}))"


def _parse_branches_from_packed(packed_out: str) -> list[dict[str, Any]]:
    """Parse a packed atom's state into a list of branch dicts.

    Calls ``parse_packed_branches/2`` in Prolog which returns a flat list
    of goal atom strings interleaved with ``'branch_start'`` markers.

    Args:
        packed_out: The packed atom string returned by ``step_packed/4``.

    Returns:
        List of ``{"orig_goal": "...", "goals": [...]}`` dicts.
    """
    result = janus.query_once(
        "parse_packed_branches(PA, FGL)",
        {"PA": packed_out},
    )
    if not result or result.get("truth") is False:
        return []
    flat: list[Any] = result.get("FGL") or []
    return _unflatten_branches(flat)


def _unflatten_branches(flat: list[Any]) -> list[dict[str, Any]]:
    """Convert a flat ``[branch_start, orig_goal, goal, ...]`` list to branch dicts.

    Immediately after each ``branch_start`` marker comes that branch's own
    copy of the original goal (``orig_goal``), followed by its resolvent goals.
    """
    branches: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    expect_orig_goal = False
    for item in flat:
        if item == "branch_start":
            if current is not None:
                branches.append(current)
            current = {"orig_goal": None, "goals": []}
            expect_orig_goal = True
        elif current is not None:
            if expect_orig_goal:
                current["orig_goal"] = str(item)
                expect_orig_goal = False
            else:
                current["goals"].append(str(item))
    if current is not None:
        branches.append(current)
    return branches


def _extract_bindings(
    original_goal: str,
    packed_out: str,
) -> dict[str, str]:
    """Attempt to extract variable bindings after a ``solution`` event.

    Calls ``extract_bindings_str/4`` in Prolog, which unifies the original
    goal string with the bound goal in the packed solution atom and collects
    variable name → value mappings.  Returns ``{}`` when the original goal
    has no variables or the unification fails (the common case; see module
    docstring).

    Args:
        original_goal: The original goal as a string (e.g. ``"color(X, Y)"``).
        packed_out: The packed output atom from ``step_packed/4`` (solution).

    Returns:
        Dict mapping variable name strings to their bound term strings.
    """
    result = janus.query_once(
        "extract_bindings_str(OGS, PSA, VN, VV)",
        {"OGS": original_goal, "PSA": packed_out},
    )
    if not result or result.get("truth") is False:
        return {}
    names: Any = result.get("VN") or []
    values: Any = result.get("VV") or []
    if not isinstance(names, list) or not isinstance(values, list):
        return {}
    return {str(n): str(v) for n, v in zip(names, values)}


def _build_new_state(
    old_state: dict[str, Any],
    event_atom: str,
    packed_out: str,
    binding_flat: list[str],
) -> dict[str, Any]:
    """Build the updated state dict from the Prolog step results.

    Args:
        old_state: The previous state dictionary.
        event_atom: The event atom string (e.g. ``"done"``, ``"solution"``,
                    ``"suspended(hello)"``).
        packed_out: The new packed atom string from ``step_packed/4``.
        binding_flat: Flat list ``[Name1, Value1, Name2, Value2, ...]`` of
                      bindings from ``step_packed/4`` (often empty).

    Returns:
        Updated v0 state dictionary.
    """
    new_branches = _parse_branches_from_packed(packed_out)

    new_state: dict[str, Any] = {
        "version": old_state.get("version", 0),
        "original_goal": old_state["original_goal"],
        "branches": new_branches,
    }
    if "ruleset_hash" in old_state:
        new_state["ruleset_hash"] = old_state["ruleset_hash"]
    if "resume_hash" in old_state:
        new_state["resume_hash"] = old_state["resume_hash"]

    if event_atom == "done":
        new_state["status"] = "done"

    elif event_atom == "solution":
        new_state["status"] = "solution"
        # Try to recover bindings from the packed atom (best-effort).
        bindings: dict[str, str] = {}
        # First use the flat list from step_packed (works when OrigGoal in
        # the packed atom is ground at solution time).
        if binding_flat:
            it = iter(binding_flat)
            try:
                for name in it:
                    value = next(it)
                    bindings[str(name)] = str(value)
            except StopIteration:
                pass
        # Fall back to extract_bindings_str.
        if not bindings:
            bindings = _extract_bindings(old_state["original_goal"], packed_out)
        new_state["bindings"] = bindings

    elif event_atom.startswith("suspended("):
        new_state["status"] = "suspended"
        new_state["resume_kind"] = "suspended"
        new_state["suspension"] = {"label": _get_suspension_label(event_atom)}

    elif event_atom.startswith("checkpoint("):
        new_state["status"] = "suspended"
        new_state["resume_kind"] = "checkpoint"
        new_state["suspension"] = {"label": _get_suspension_label(event_atom)}

    else:
        # Any other event.
        new_state["status"] = "running"

    return new_state


def _get_suspension_label(event_atom: str) -> str:
    """Extract the label string from a ``suspended(Label)`` or ``checkpoint(Label)`` event atom.

    Uses Prolog to parse the label so arbitrary Prolog terms are handled.

    Args:
        event_atom: e.g. ``"suspended(hello)"`` or ``"checkpoint(foo)"``.

    Returns:
        The label as a string, e.g. ``"hello"`` or ``"foo"``.
    """
    # Determine the wrapper functor name.
    for prefix in ("suspended(", "checkpoint("):
        if event_atom.startswith(prefix):
            wrapper = prefix[:-1]  # e.g. "suspended" or "checkpoint"
            result = janus.query_once(
                f"term_to_atom({wrapper}(L), EA), term_to_atom(L, LA)",
                {"EA": event_atom},
            )
            if result and result.get("truth") is not False:
                return str(result["LA"])
            # Fallback: simple string slicing for simple atom labels.
            if event_atom.endswith(")"):
                return event_atom[len(prefix):-1]
            return event_atom
    return event_atom
