"""Tests for the query/3 compiler (compile_query/3)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import pytest
import janus_swi as janus

from constraint import meta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_query_rules() -> None:
    """Assert the two descendant query_rule/2 facts into the Prolog store."""
    meta._ensure_query_compiler_loaded()
    # Declare the predicate and add the two transitive-closure rules.
    fd, path = tempfile.mkstemp(suffix=".pl", prefix="test_compiler_rules_")
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
    """Load Prolog helper predicates used by the test methods.

    Defines:
      - compile_demo/2: serializes compiled term and obligations for the
        worked example query.
      - compile_demo_obligations/1: returns just the obligations atom.
      - compile_unsupported/1: returns 'error_thrown' or 'no_error'.
    """
    fd, path = tempfile.mkstemp(suffix=".pl", prefix="test_compiler_helpers_")
    os.close(fd)
    Path(path).write_text(
        ":-( use_module('" + str(Path(meta.__file__).parent / "query_compiler.pl") + "') ).\n"
        "\n"
        ":- multifile user:query_rule/2.\n"
        "user:query_rule(descendant(Anc, Desc), [ node(id: Desc, parent_id: Anc) ]).\n"
        "user:query_rule(descendant(Anc, Desc), [ descendant(Anc, Mid), node(id: Desc, parent_id: Mid) ]).\n"
        "\n"
        "compile_demo(CompiledAtom, ObligationsAtom) :-\n"
        "    Query = query(source:result(OuterId, NameText, OuterStart), \n"
        "                  ( node(id: OuterId, kind: 'function_definition', start_byte: OuterStart),\n"
        "                    descendant(OuterId, InnerId),\n"
        "                    node(id: InnerId, kind: 'function_definition'),\n"
        "                    OuterId \\= InnerId,\n"
        "                    node(parent_id: OuterId, kind: 'identifier', text: NameText) ),\n"
        "                  Out),\n"
        "    query_compiler:compile_query(Query, CompiledAtom, Obligations),\n"
        "    term_to_atom(Obligations, ObligationsAtom).\n"
        "\n"
        "compile_demo_obligations(ObligationsAtom) :-\n"
        "    compile_demo(_, ObligationsAtom).\n"
        "\n"
        "compile_unsupported(Status) :-\n"
        "    catch(\n"
        "        (Query = query(source:result(X), (X > 5), _),\n"
        "         query_compiler:compile_query(Query, _, _),\n"
        "         Status = 'no_error'),\n"
        "        error(unsupported_builtin(_), _),\n"
        "        (Status = 'error_thrown')\n"
        "    ).\n"
        "\n"
        "compile_supported_neq(CompiledAtom) :-\n"
        "    Query = query(source:result(X, Y), (X \\= Y), _),\n"
        "    query_compiler:compile_query(Query, CompiledAtom, _).\n"
    )
    janus.consult(path)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _setup_compiler() -> None:
    """Ensure compiler and query rules are loaded once per module run."""
    _load_query_rules()
    _load_helpers()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCompileQuery:
    """Tests for the compile_query/3 predicate."""

    def test_emitted_term_structure(self) -> None:
        """The compiled term must have the expected structure.

        Surface Key:Value pairs are normalized to Key-Value; the inequality
        guard is emitted as '!='; derived clauses carry the full transitive
        closure of descendant/2 (including the recursive rule).
        """
        result = janus.query_once("compile_demo(CA, _)")
        assert result is not None
        assert result.get("truth") is not False

        comp_atom = result["CA"]

        # Verify structure entirely Prolog-side; only a bare atom crosses janus
        # (a term with unbound vars cannot be marshalled back to Python).
        struct_ok = janus.query_once(
            "read_term_from_atom(Atom, _T, []), "
            "( _T = compiled_query(store(_), template(result, _), derived(_), goals(_)) "
            "  -> R = true ; R = false )",
            {"Atom": comp_atom},
        )
        assert struct_ok is not None
        assert struct_ok.get("R") == "true", (
            f"Compiled term {comp_atom} does not match "
            f"compiled_query(store(_), template(result, _), derived(_), goals(_))"
        )

    def test_emitted_term_key_value_normalization(self) -> None:
        """Key: Value pairs in surface syntax must be normalized to Key-Value."""
        result = janus.query_once("compile_demo(CA, _)")
        assert result is not None and result.get("truth") is not False
        comp_atom = result["CA"]

        # All :/2 pairs should have become -/2 pairs.
        contains_colon = janus.query_once(
            "read_term_from_atom(Atom, Term, []), "
            "sub_term(Sub, Term), nonvar(Sub), Sub = (_:_)",
            {"Atom": comp_atom},
        )
        # If truth is True, a colon pair was found, which is wrong.
        assert contains_colon.get("truth") is not True, (
            f"Compiled term {comp_atom} still contains Key:Value pairs "
            f"instead of normalized Key-Value"
        )

    def test_emitted_term_inequality_as_bang_equal(self) -> None:
        """The \\= guard must be translated to '!=' in the emitted term."""
        result = janus.query_once("compile_demo(CA, _)")
        assert result is not None and result.get("truth") is not False
        comp_atom = result["CA"]

        neq_ok = janus.query_once(
            "read_term_from_atom(Atom, _T, []), "
            "( ( sub_term(_S, _T), _S = '!='(_, _) ) -> R = true ; R = false )",
            {"Atom": comp_atom},
        )
        assert neq_ok is not None and neq_ok.get("R") == "true", (
            f"Compiled term {comp_atom} does not contain '!='(_, _)"
        )

    def test_emitted_term_derived_contains_closure(self) -> None:
        """The derived list must contain the recursive descendant clause."""
        result = janus.query_once("compile_demo(CA, _)")
        assert result is not None and result.get("truth") is not False
        comp_atom = result["CA"]

        # Check for the recursive rule: rule(descendant(_, _), [descendant(_, _), ...])
        derived_ok = janus.query_once(
            "read_term_from_atom(Atom, _T, []), "
            "( ( _T = compiled_query(_, _, derived(_D), _), "
            "    member(rule(descendant(_, _), [descendant(_, _)|_]), _D) ) "
            "  -> R = true ; R = false )",
            {"Atom": comp_atom},
        )
        assert derived_ok is not None and derived_ok.get("R") == "true", (
            f"Compiled term {comp_atom} missing recursive descendant rule in derived"
        )

    def test_obligations_shape(self) -> None:
        """Obligations must be [Projection | BaseObligations].

        Projection is the template columns list; base obligations cover the
        columns touched by the query, order-insensitive.
        """
        result = janus.query_once("compile_demo_obligations(OA)")
        assert result is not None and result.get("truth") is not False
        obl_atom = result["OA"]

        # Parse: [[OuterId, NameText, OuterStart], node(Cols...)]
        parse_ok = janus.query_once(
            "read_term_from_atom(Atom, _T, []), "
            "( ( _T = [_ProjCols | _], length(_ProjCols, 3) ) -> R = true ; R = false )",
            {"Atom": obl_atom},
        )
        assert parse_ok is not None and parse_ok.get("R") == "true", (
            f"Obligations {obl_atom} does not start with a 3-element projection list"
        )

        # Check that there's exactly one base obligation: node/5
        node_ok = janus.query_once(
            "read_term_from_atom(Atom, _T, []), "
            "( _T = [_, node(id, kind, parent_id, start_byte, text)] "
            "  -> R = true ; R = false )",
            {"Atom": obl_atom},
        )
        assert node_ok is not None and node_ok.get("R") == "true", (
            f"Obligations {obl_atom} does not contain "
            f"node(id, kind, parent_id, start_byte, text)"
        )

    def test_obligations_no_derived_or_guard(self) -> None:
        """Derived relations and guards must NOT appear in the obligations list."""
        result = janus.query_once("compile_demo_obligations(OA)")
        assert result is not None and result.get("truth") is not False
        obl_atom = result["OA"]

        # Check no descendant obligation
        no_desc = janus.query_once(
            "read_term_from_atom(Atom, Term, []), "
            "sub_term(Sub, Term), nonvar(Sub), "
            "(Sub = descendant(_, _) ; Sub = '!='(_, _))",
            {"Atom": obl_atom},
        )
        # truth should be False (no sub_term match for descendant or '!=')
        assert no_desc.get("truth") is not True, (
            f"Obligations {obl_atom} unexpectedly contains descendant/2 or '!='/2"
        )

    def test_unsupported_builtin_raises_error(self) -> None:
        """A query with an unsupported builtin must raise a compile error."""
        result = janus.query_once("compile_unsupported(S)")
        assert result is not None and result.get("truth") is not False
        assert result["S"] == "error_thrown", (
            f"Expected error_thrown for unsupported builtin, got {result['S']}"
        )

    def test_supported_neq_does_not_raise(self) -> None:
        """The supported \\= builtin must compile successfully."""
        result = janus.query_once("compile_supported_neq(CA)")
        assert result is not None and result.get("truth") is not False
        comp_atom = result["CA"]

        # Verify '!=' appears in the compiled output.
        neq_ok = janus.query_once(
            "read_term_from_atom(Atom, _T, []), "
            "( ( sub_term(_S, _T), _S = '!='(_, _) ) -> R = true ; R = false )",
            {"Atom": comp_atom},
        )
        assert neq_ok is not None and neq_ok.get("R") == "true", (
            f"Compiled term {comp_atom} does not contain '!=' translation"
        )
