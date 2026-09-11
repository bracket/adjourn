"""End-to-end acceptance test for query/3 through the real mnestic callout.

Builds a tiny rocksdb with hand-written node rows, registers the store
with a descendant support rule, and drives the worked-example query/3
through the real adapter callout (not a stub).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import janus_swi as janus
import pytest

from constraint import meta
from constraint.store.mnestic_store import MnesticRuleSetStore
from constraint.store.mnestic_adapter import _registry as _adapter_registry


def _create_mnestic_db(path: str, relation_script: str) -> None:
    """Create and populate a mnestic rocksdb database with the given relation."""
    from mnestic import CozoDbPy

    db = CozoDbPy("rocksdb", path, "")
    db.run_script(relation_script, {}, immutable=False)
    db.close()


def _load_query_rules() -> None:
    """Assert the two descendant query_rule/2 facts into the Prolog store."""
    meta._ensure_query_compiler_loaded()
    fd, path = tempfile.mkstemp(suffix=".pl", prefix="test_mnestic_query_rules_")
    os.close(fd)
    Path(path).write_text(
        ":- multifile user:query_rule/2.\n"
        ":- dynamic user:query_rule/2.\n"
        "\n"
        "user:query_rule(descendant(Anc, Desc), [ node(id: Desc, parent_id: Anc) ]).\n"
        "user:query_rule(descendant(Anc, Desc), [ descendant(Anc, Mid), node(id: Desc, parent_id: Mid) ]).\n"
    )
    janus.consult(path)


def _load_helpers(store_name: str) -> None:
    """Load Prolog helper predicates for the acceptance test.

    Defines reduce_acceptance/1 that drives the worked-example query/3
    through the kernel and returns the Bag as an atom.
    """
    fd, path = tempfile.mkstemp(suffix=".pl", prefix="test_mnestic_query_helpers_")
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
        f"reduce_acceptance(BagAtom) :-\n"
        f"    Goal = query({store_name}:result(outer_id, name_text, outer_start),\n"
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
        "step_until_solution(State) :-\n"
        "    constraint_meta:step(State, Event, State1),\n"
        "    (   Event = solution(_) -> true\n"
        "    ;   Event = done -> fail\n"
        "    ;   step_until_solution(State1)\n"
        "    ).\n"
    )
    janus.consult(path)


@pytest.fixture(autouse=True)
def _setup_engine() -> None:
    """Ensure the meta-interpreter, compiler, and foreign registry are loaded."""
    meta._ensure_meta_loaded()
    meta._ensure_query_compiler_loaded()
    meta._ensure_foreign_loaded()


class TestMnesticQueryAcceptance:
    """End-to-end acceptance test for query/3 through the real callout."""

    @pytest.fixture(autouse=True)
    def _setup_store_and_rules(self, tmp_path: Path) -> None:
        """Create a rocksdb with hand-written node data, register the store,
        and load query_rule/2 facts into Prolog."""
        # 1. Create the rocksdb with a node relation
        db_path = tmp_path / "acceptance.db"
        _create_mnestic_db(
            str(db_path),
            (
                ":create node {"
                "    id: Int"
                "    =>"
                "    kind: String,"
                "    parent_id: Int?,"
                "    start_byte: Int,"
                "    end_byte: Int,"
                "    start_row: Int,"
                "    start_col: Int,"
                "    end_row: Int,"
                "    end_col: Int,"
                "    is_named: Bool,"
                "    text: String,"
                "}"
            ),
        )

        # 2. Insert hand-written data forming a minimal nested-function shape
        from mnestic import CozoDbPy
        db = CozoDbPy("rocksdb", str(db_path), "")
        db.import_relations(data={
            "node": {
                "headers": [
                    "id", "kind", "parent_id", "start_byte", "end_byte",
                    "start_row", "start_col", "end_row", "end_col",
                    "is_named", "text"
                ],
                "rows": [
                    # Outer function definition (id=1), no parent
                    [1, "function_definition", None, 0, 50, 0, 0, 2, 10, True, "outer_fn"],
                    # Inner function definition (id=2), parent_id=1 (child of outer)
                    [2, "function_definition", 1, 20, 40, 1, 0, 1, 20, True, "inner_fn"],
                    # Identifier node (id=3), parent_id=1 (direct child of outer),
                    # text is the outer function's name
                    [3, "identifier", 1, 5, 10, 0, 5, 0, 10, True, "outer_fn"],
                ],
            }
        })
        db.close()

        # 3. Create a MnesticRuleSetStore with a name to register its adapter
        self._store = MnesticRuleSetStore(str(db_path), name="source")
        # Trigger _load() to register the adapter
        _ = self._store.ruleset_hash

        # 4. Load query_rule/2 facts into Prolog for the query compiler
        _load_query_rules()

        # 5. Load Prolog helpers
        _load_helpers("source")

        yield

        # Clean up the adapter registry
        _adapter_registry.pop("source", None)

    def test_acceptance_reduces_to_solution(self) -> None:
        """The worked-example query/3 must reduce to a solution event."""
        result = janus.query_once("reduce_acceptance(BA)")
        assert result is not None
        assert result.get("truth") is not False

    def test_acceptance_bag_is_single_result(self) -> None:
        """The Bag must be [result(1, 'outer_fn', 0)]."""
        result = janus.query_once("reduce_acceptance(BA)")
        assert result is not None and result.get("truth") is not False
        bag_atom = result["BA"]

        struct_ok = janus.query_once(
            "read_term_from_atom(Atom, _T, []), "
            "( _T = [result(1, 'outer_fn', 0)] "
            "  -> R = true ; R = false )",
            {"Atom": bag_atom},
        )
        assert struct_ok is not None
        assert struct_ok.get("R") == "true", (
            f"Bag {bag_atom} does not match [result(1, 'outer_fn', 0)]"
        )

    def test_acceptance_bag_has_single_element(self) -> None:
        """The Bag must be a list with exactly one result term."""
        result = janus.query_once("reduce_acceptance(BA)")
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

    def test_acceptance_result_fields(self) -> None:
        """Each result term must have the correct functor and arity."""
        result = janus.query_once("reduce_acceptance(BA)")
        assert result is not None and result.get("truth") is not False
        bag_atom = result["BA"]

        fields_ok = janus.query_once(
            "read_term_from_atom(Atom, _T, []), "
            "( _T = [result(1, 'outer_fn', 0)] "
            "  -> R = true ; R = false )",
            {"Atom": bag_atom},
        )
        assert fields_ok is not None and fields_ok.get("R") == "true", (
            f"Bag {bag_atom} result fields do not match expected values"
        )
