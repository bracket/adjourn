"""Acceptance tests for query/3 reduction through the kernel.

Exercises the ``query/3`` ``reduce_goal/5`` clause in ``meta.pl`` by driving
the worked-example query through ``step/3`` and verifying the result
Prolog-side, following the same pattern as ``test_compiler.py``.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import janus_swi as janus
import pytest

from constraint import meta
from constraint.constraint_foreign import _registry
from constraint.store.mnestic_adapter import register as _register_adapter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_query_rules() -> None:
    """Assert the two descendant query_rule/2 facts into the Prolog store."""
    meta._ensure_query_compiler_loaded()
    fd, path = tempfile.mkstemp(suffix=".pl", prefix="test_query_reduce_rules_")
    os.close(fd)
    Path(path).write_text(
        ":- multifile user:query_rule/2.\n"
        ":- dynamic user:query_rule/2.\n"
        "\n"
        "user:query_rule(descendant(Anc, Desc), [ node(id: Desc, parent_id: Anc) ]).\n"
        "user:query_rule(descendant(Anc, Desc), [ descendant(Anc, Mid), node(id: Desc, parent_id: Mid) ]).\n"
    )
    janus.consult(path)


def _load_helpers() -> None:
    """Load Prolog helper predicates for query/3 reduction tests.

    Defines:
      - reduce_worked_example/1: reduces the worked-example query/3 goal
        through the kernel and returns the Bag as an atom.
      - reduce_query/1: reduces a parameterised query/3 goal and returns
        the Bag as an atom.
    """
    fd, path = tempfile.mkstemp(suffix=".pl", prefix="test_query_reduce_helpers_")
    os.close(fd)
    qc_path = str(Path(meta.__file__).parent / "query_compiler.pl")
    Path(path).write_text(
        f":- use_module('{qc_path}').\n"
        ":- use_module(library(janus)).\n"
        "\n"
        ":- multifile user:query_rule/2.\n"
        "user:query_rule(descendant(Anc, Desc), [ node(id: Desc, parent_id: Anc) ]).\n"
        "user:query_rule(descendant(Anc, Desc), [ descendant(Anc, Mid), node(id: Desc, parent_id: Mid) ]).\n"
        "\n"
        "reduce_worked_example(BagAtom) :-\n"
        "    Goal = query(source:result(outer_id, name_text, outer_start),\n"
        "                 ( node(id: outer_id, kind: 'function_definition', start_byte: outer_start),\n"
        "                   descendant(outer_id, inner_id),\n"
        "                   node(id: inner_id, kind: 'function_definition'),\n"
        "                   outer_id \\= inner_id,\n"
        "                   node(parent_id: outer_id, kind: 'identifier', text: name_text) ),\n"
        "                 Out),\n"
        "    constraint_meta:init(Goal, State0),\n"
        "    step_until_solution(State0),\n"
        "    term_to_atom(Out, BagAtom).\n"
        "\n"
        "reduce_query(Goal, BagAtom) :-\n"
        "    constraint_meta:init(Goal, State0),\n"
        "    step_until_solution(State0),\n"
        "    term_to_atom(Out, BagAtom).\n"
        "\n"
        "step_until_solution(State) :-\n"
        "    constraint_meta:step(State, Event, State1),\n"
        "    (   Event = solution(_) -> true\n"
        "    ;   Event = done -> fail\n"
        "    ;   step_until_solution(State1)\n"
        "    ).\n"
    )
    janus.consult(path)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _setup_engine() -> None:
    """Ensure the meta-interpreter, compiler, foreign registry, and query
    rules are loaded once per module run."""
    meta._ensure_meta_loaded()
    meta._ensure_query_compiler_loaded()
    meta._ensure_foreign_loaded()
    _load_query_rules()
    _load_helpers()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestQueryReduceWorkedExample:
    """Tests for the worked-example query/3 reduction."""

    @pytest.fixture(autouse=True)
    def _register_mock_store(self) -> Any:
        """Register a mock adapter for the 'source' store so the
        mnestic_query callout can resolve it."""
        from constraint.store.mnestic_adapter import MnesticAdapter

        class _MockAdapter:
            """Mock adapter that returns the canned worked-example data."""
            def compile_and_run(self, compiled_atom: str, obligations_atom: str) -> list[list[str | int]]:
                return [["n_outer", "outer_function", 0]]

        _register_adapter("source", _MockAdapter())  # type: ignore[arg-type]
        yield
        # Clean up the registry
        from constraint.store.mnestic_adapter import _registry as _adapter_registry
        _adapter_registry.pop("source", None)

    def test_worked_example_reduces_to_solution(self) -> None:
        """The worked-example query/3 must reduce to a solution event."""
        result = janus.query_once("reduce_worked_example(BA)")
        assert result is not None
        assert result.get("truth") is not False

    def test_worked_example_bag_is_result_list(self) -> None:
        """The Bag must unify with [result('n_outer', 'outer_function', 0)]."""
        result = janus.query_once("reduce_worked_example(BA)")
        assert result is not None and result.get("truth") is not False
        bag_atom = result["BA"]

        # Verify structure Prolog-side using read_term_from_atom + the
        # (Cond -> R = true ; R = false) idiom (same pattern as test_compiler.py).
        struct_ok = janus.query_once(
            "read_term_from_atom(Atom, _T, []), "
            "( _T = [result('n_outer', 'outer_function', 0)] "
            "  -> R = true ; R = false )",
            {"Atom": bag_atom},
        )
        assert struct_ok is not None
        assert struct_ok.get("R") == "true", (
            f"Bag {bag_atom} does not match [result('n_outer', 'outer_function', 0)]"
        )

    def test_worked_example_bag_has_single_result(self) -> None:
        """The Bag must be a list with exactly one result term."""
        result = janus.query_once("reduce_worked_example(BA)")
        assert result is not None and result.get("truth") is not False
        bag_atom = result["BA"]

        length_ok = janus.query_once(
            "read_term_from_atom(Atom, _T, []), "
            "( ( _T = [_], length(_T, 1) ) -> R = true ; R = false )",
            {"Atom": bag_atom},
        )
        assert length_ok is not None and length_ok.get("R") == "true", (
            f"Bag {bag_atom} is not a single-element list"
        )

    def test_worked_example_result_fields(self) -> None:
        """Each result term must have the correct functor and arity."""
        result = janus.query_once("reduce_worked_example(BA)")
        assert result is not None and result.get("truth") is not False
        bag_atom = result["BA"]

        fields_ok = janus.query_once(
            "read_term_from_atom(Atom, _T, []), "
            "( _T = [result('n_outer', 'outer_function', 0)] "
            "  -> R = true ; R = false )",
            {"Atom": bag_atom},
        )
        assert fields_ok is not None and fields_ok.get("R") == "true", (
            f"Bag {bag_atom} result fields do not match expected values"
        )


class TestQueryReduceEmptyResult:
    """Tests for query/3 reduction when the stub returns an empty result set."""

    _original_mnestic: Any = None

    @pytest.fixture(autouse=True)
    def _patch_stub_empty(self) -> Any:
        """Temporarily replace the mnestic_query stub to return []."""
        self._original_mnestic = _registry.get("mnestic_query")

        def _empty_stub(_arg: Any) -> list[list[str | int]]:
            return []

        _registry["mnestic_query"] = _empty_stub
        yield
        # Restore original
        if self._original_mnestic is not None:
            _registry["mnestic_query"] = self._original_mnestic
        else:
            _registry.pop("mnestic_query", None)

    def test_empty_result_reduces_to_solution(self) -> None:
        """A query/3 goal with empty stub result must still reach solution."""
        result = janus.query_once("reduce_worked_example(BA)")
        assert result is not None
        assert result.get("truth") is not False

    def test_empty_result_bag_is_empty_list(self) -> None:
        """The Bag must be [] when the stub returns no rows."""
        result = janus.query_once("reduce_worked_example(BA)")
        assert result is not None and result.get("truth") is not False
        bag_atom = result["BA"]

        empty_ok = janus.query_once(
            "read_term_from_atom(Atom, _T, []), "
            "( _T = [] -> R = true ; R = false )",
            {"Atom": bag_atom},
        )
        assert empty_ok is not None and empty_ok.get("R") == "true", (
            f"Bag {bag_atom} is not an empty list"
        )

    def test_empty_result_bag_length_zero(self) -> None:
        """The Bag must have length 0 when the stub returns no rows."""
        result = janus.query_once("reduce_worked_example(BA)")
        assert result is not None and result.get("truth") is not False
        bag_atom = result["BA"]

        length_ok = janus.query_once(
            "read_term_from_atom(Atom, _T, []), "
            "( ( _T = [], length(_T, 0) ) -> R = true ; R = false )",
            {"Atom": bag_atom},
        )
        assert length_ok is not None and length_ok.get("R") == "true", (
            f"Bag {bag_atom} is not an empty list"
        )
