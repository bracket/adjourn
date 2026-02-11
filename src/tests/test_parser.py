"""Tests for the Prolog parser module."""

from __future__ import annotations

from pathlib import Path

import pytest

from constraint.parser import (
    Atom,
    Clause,
    Compound,
    Directive,
    Float,
    Integer,
    List,
    Program,
    String,
    Variable,
    parse_clause,
    parse_file,
    parse_program,
    parse_term,
)


class TestAtoms:
    """Tests for parsing atoms."""

    def test_simple_atom(self) -> None:
        """Test parsing a simple lowercase atom."""
        result = parse_term("hello")
        assert isinstance(result, Atom)
        assert result.value == "hello"

    def test_atom_with_underscores(self) -> None:
        """Test parsing an atom with underscores."""
        result = parse_term("hello_world")
        assert isinstance(result, Atom)
        assert result.value == "hello_world"

    def test_atom_with_numbers(self) -> None:
        """Test parsing an atom with numbers."""
        result = parse_term("test123")
        assert isinstance(result, Atom)
        assert result.value == "test123"

    def test_quoted_atom(self) -> None:
        """Test parsing a quoted atom."""
        result = parse_term("'Hello World'")
        assert isinstance(result, Atom)
        assert result.value == "Hello World"

    def test_quoted_atom_with_escape(self) -> None:
        """Test parsing a quoted atom with escape sequences."""
        result = parse_term("'can\\'t'")
        assert isinstance(result, Atom)
        assert result.value == "can't"


class TestVariables:
    """Tests for parsing variables."""

    def test_simple_variable(self) -> None:
        """Test parsing a simple variable."""
        result = parse_term("X")
        assert isinstance(result, Variable)
        assert result.name == "X"

    def test_variable_with_underscores(self) -> None:
        """Test parsing a variable with underscores."""
        result = parse_term("My_Var")
        assert isinstance(result, Variable)
        assert result.name == "My_Var"

    def test_anonymous_variable(self) -> None:
        """Test parsing an anonymous variable."""
        result = parse_term("_")
        assert isinstance(result, Variable)
        assert result.name == "_"

    def test_named_anonymous_variable(self) -> None:
        """Test parsing a named anonymous variable."""
        result = parse_term("_Result")
        assert isinstance(result, Variable)
        assert result.name == "_Result"


class TestNumbers:
    """Tests for parsing numbers."""

    def test_positive_integer(self) -> None:
        """Test parsing a positive integer."""
        result = parse_term("42")
        assert isinstance(result, Integer)
        assert result.value == 42

    def test_negative_integer(self) -> None:
        """Test parsing a negative integer."""
        result = parse_term("-123")
        assert isinstance(result, Integer)
        assert result.value == -123

    def test_float(self) -> None:
        """Test parsing a float."""
        result = parse_term("3.14")
        assert isinstance(result, Float)
        assert result.value == 3.14

    def test_float_with_exponent(self) -> None:
        """Test parsing a float with exponent."""
        result = parse_term("1.5e10")
        assert isinstance(result, Float)
        assert result.value == 1.5e10


class TestStrings:
    """Tests for parsing strings."""

    def test_simple_string(self) -> None:
        """Test parsing a simple string."""
        result = parse_term('"hello"')
        assert isinstance(result, String)
        assert result.value == "hello"

    def test_string_with_spaces(self) -> None:
        """Test parsing a string with spaces."""
        result = parse_term('"hello world"')
        assert isinstance(result, String)
        assert result.value == "hello world"

    def test_empty_string(self) -> None:
        """Test parsing an empty string."""
        result = parse_term('""')
        assert isinstance(result, String)
        assert result.value == ""


class TestCompounds:
    """Tests for parsing compound terms."""

    def test_compound_no_args(self) -> None:
        """Test parsing a compound term with no arguments."""
        result = parse_term("test()")
        assert isinstance(result, Compound)
        assert result.functor == "test"
        assert result.args == []

    def test_compound_one_arg(self) -> None:
        """Test parsing a compound term with one argument."""
        result = parse_term("f(a)")
        assert isinstance(result, Compound)
        assert result.functor == "f"
        assert len(result.args) == 1
        assert isinstance(result.args[0], Atom)
        assert result.args[0].value == "a"

    def test_compound_multiple_args(self) -> None:
        """Test parsing a compound term with multiple arguments."""
        result = parse_term("test(a, b, c)")
        assert isinstance(result, Compound)
        assert result.functor == "test"
        assert len(result.args) == 3
        assert all(isinstance(arg, Atom) for arg in result.args)

    def test_nested_compounds(self) -> None:
        """Test parsing nested compound terms."""
        result = parse_term("f(g(a), h(b, c))")
        assert isinstance(result, Compound)
        assert result.functor == "f"
        assert len(result.args) == 2
        assert isinstance(result.args[0], Compound)
        assert result.args[0].functor == "g"
        assert isinstance(result.args[1], Compound)
        assert result.args[1].functor == "h"


class TestLists:
    """Tests for parsing lists."""

    def test_empty_list(self) -> None:
        """Test parsing an empty list."""
        result = parse_term("[]")
        assert isinstance(result, List)
        assert result.elements == []
        assert result.tail is None

    def test_list_one_element(self) -> None:
        """Test parsing a list with one element."""
        result = parse_term("[1]")
        assert isinstance(result, List)
        assert len(result.elements) == 1
        assert isinstance(result.elements[0], Integer)
        assert result.elements[0].value == 1

    def test_list_multiple_elements(self) -> None:
        """Test parsing a list with multiple elements."""
        result = parse_term("[1, 2, 3]")
        assert isinstance(result, List)
        assert len(result.elements) == 3
        assert all(isinstance(e, Integer) for e in result.elements)

    def test_list_with_tail(self) -> None:
        """Test parsing a list with tail notation [H|T]."""
        result = parse_term("[H|T]")
        assert isinstance(result, List)
        assert len(result.elements) == 1
        assert isinstance(result.elements[0], Variable)
        assert result.elements[0].name == "H"
        assert isinstance(result.tail, Variable)
        assert result.tail.name == "T"

    def test_list_multiple_elements_with_tail(self) -> None:
        """Test parsing a list with multiple elements and tail."""
        result = parse_term("[1, 2, 3|Rest]")
        assert isinstance(result, List)
        assert len(result.elements) == 3
        assert isinstance(result.tail, Variable)
        assert result.tail.name == "Rest"

    def test_nested_lists(self) -> None:
        """Test parsing nested lists."""
        result = parse_term("[[1, 2], [3, 4]]")
        assert isinstance(result, List)
        assert len(result.elements) == 2
        assert all(isinstance(e, List) for e in result.elements)


class TestOperators:
    """Tests for parsing operators."""

    def test_arithmetic_plus(self) -> None:
        """Test parsing arithmetic plus operator."""
        result = parse_term("1 + 2")
        assert isinstance(result, Compound)
        assert result.functor == "+"
        assert len(result.args) == 2

    def test_arithmetic_precedence(self) -> None:
        """Test arithmetic operator precedence."""
        result = parse_term("1 + 2 * 3")
        assert isinstance(result, Compound)
        assert result.functor == "+"
        # 2 * 3 should be grouped first
        assert isinstance(result.args[1], Compound)
        assert result.args[1].functor == "*"

    def test_comparison_equals(self) -> None:
        """Test parsing equals operator."""
        result = parse_term("X = Y")
        assert isinstance(result, Compound)
        assert result.functor == "="
        assert len(result.args) == 2

    def test_module_qualification(self) -> None:
        """Test parsing module qualification operator."""
        result = parse_term("module:predicate")
        assert isinstance(result, Compound)
        assert result.functor == ":"
        assert len(result.args) == 2

    def test_unification_with_module_qualification(self) -> None:
        """Test parsing unification with module qualification."""
        result = parse_term("X = module:goal")
        assert isinstance(result, Compound)
        assert result.functor == "="
        # Right side should be module:goal
        assert isinstance(result.args[1], Compound)
        assert result.args[1].functor == ":"

    def test_conjunction(self) -> None:
        """Test parsing conjunction (comma) operator."""
        result = parse_term("(a, b)")
        assert isinstance(result, Compound)
        assert result.functor == ","
        assert len(result.args) == 2

    def test_disjunction(self) -> None:
        """Test parsing disjunction (semicolon) operator."""
        result = parse_term("(a ; b)")
        assert isinstance(result, Compound)
        assert result.functor == ";"
        assert len(result.args) == 2

    def test_if_then(self) -> None:
        """Test parsing if-then operator."""
        result = parse_term("(a -> b)")
        assert isinstance(result, Compound)
        assert result.functor == "->"
        assert len(result.args) == 2

    def test_if_then_else(self) -> None:
        """Test parsing if-then-else."""
        result = parse_term("(a -> b ; c)")
        assert isinstance(result, Compound)
        assert result.functor == ";"
        # Left side should be a -> b
        assert isinstance(result.args[0], Compound)
        assert result.args[0].functor == "->"

    def test_negation(self) -> None:
        """Test parsing negation operator."""
        result = parse_term("\\+ a")
        assert isinstance(result, Compound)
        assert result.functor == "\\+"
        assert len(result.args) == 1

    def test_cut(self) -> None:
        """Test parsing cut operator."""
        result = parse_term("!")
        assert isinstance(result, Atom)
        assert result.value == "!"


class TestClauses:
    """Tests for parsing clauses."""

    def test_simple_fact(self) -> None:
        """Test parsing a simple fact."""
        result = parse_clause("parent(tom, bob).")
        assert isinstance(result, Clause)
        assert result.body is None
        assert isinstance(result.head, Compound)
        assert result.head.functor == "parent"

    def test_rule_with_simple_body(self) -> None:
        """Test parsing a rule with simple body."""
        result = parse_clause("ancestor(X, Y) :- parent(X, Y).")
        assert isinstance(result, Clause)
        assert isinstance(result.head, Compound)
        assert result.head.functor == "ancestor"
        assert isinstance(result.body, Compound)
        assert result.body.functor == "parent"

    def test_rule_with_conjunction(self) -> None:
        """Test parsing a rule with conjunction in body."""
        result = parse_clause("grandparent(X, Z) :- parent(X, Y), parent(Y, Z).")
        assert isinstance(result, Clause)
        assert isinstance(result.body, Compound)
        assert result.body.functor == ","

    def test_fact_with_list(self) -> None:
        """Test parsing a fact with list."""
        result = parse_clause("member(X, [X|_]).")
        assert isinstance(result, Clause)
        assert result.body is None
        assert isinstance(result.head, Compound)
        # Second argument should be a list
        assert isinstance(result.head.args[1], List)


class TestDirectives:
    """Tests for parsing directives."""

    def test_module_directive(self) -> None:
        """Test parsing module directive."""
        result = parse_clause(":- module(test, []).")
        assert isinstance(result, Directive)
        assert isinstance(result.term, Compound)
        assert result.term.functor == "module"

    def test_multifile_directive(self) -> None:
        """Test parsing multifile directive."""
        result = parse_clause(":- multifile rule/2.")
        assert isinstance(result, Directive)
        assert isinstance(result.term, Compound)
        assert result.term.functor == "multifile"

    def test_dynamic_directive(self) -> None:
        """Test parsing dynamic directive."""
        result = parse_clause(":- dynamic fact/1.")
        assert isinstance(result, Directive)
        assert isinstance(result.term, Compound)
        assert result.term.functor == "dynamic"


class TestPrograms:
    """Tests for parsing complete programs."""

    def test_empty_program(self) -> None:
        """Test parsing an empty program."""
        result = parse_program("")
        assert isinstance(result, Program)
        assert result.items == []

    def test_program_with_facts(self) -> None:
        """Test parsing a program with multiple facts."""
        code = """
        parent(tom, bob).
        parent(bob, ann).
        """
        result = parse_program(code)
        assert isinstance(result, Program)
        assert len(result.items) == 2
        assert all(isinstance(item, Clause) for item in result.items)

    def test_program_with_rules(self) -> None:
        """Test parsing a program with rules."""
        code = """
        ancestor(X, Y) :- parent(X, Y).
        ancestor(X, Z) :- parent(X, Y), ancestor(Y, Z).
        """
        result = parse_program(code)
        assert isinstance(result, Program)
        assert len(result.items) == 2
        assert all(isinstance(item, Clause) for item in result.items)
        assert all(item.body is not None for item in result.items)

    def test_program_with_directive(self) -> None:
        """Test parsing a program with directive."""
        code = """
        :- module(test, []).
        
        fact(a).
        """
        result = parse_program(code)
        assert isinstance(result, Program)
        assert len(result.items) == 2
        assert isinstance(result.items[0], Directive)
        assert isinstance(result.items[1], Clause)

    def test_program_with_comments(self) -> None:
        """Test parsing a program with comments."""
        code = """
        % This is a line comment
        parent(tom, bob).  % Another comment
        /* This is a
           block comment */
        parent(bob, ann).
        """
        result = parse_program(code)
        assert isinstance(result, Program)
        assert len(result.items) == 2


class TestExampleFiles:
    """Tests for parsing the example Prolog files."""

    def test_list_member_file(self) -> None:
        """Test parsing list_member.pl example file."""
        filepath = "examples/list_membership/list_member.pl"
        if not Path(filepath).exists():
            pytest.skip(f"Example file not found: {filepath}")

        result = parse_file(filepath)
        assert isinstance(result, Program)
        assert len(result.items) == 2
        # Should have two clauses for member/2
        assert all(isinstance(item, Clause) for item in result.items)

    def test_input_callback_file(self) -> None:
        """Test parsing input_loop.pl example file."""
        filepath = "examples/input_callback/input_loop.pl"
        if not Path(filepath).exists():
            pytest.skip(f"Example file not found: {filepath}")

        result = parse_file(filepath)
        assert isinstance(result, Program)
        assert len(result.items) > 0

    def test_toy_graph_coloring_file(self) -> None:
        """Test parsing toy_graph_coloring.pl example file."""
        filepath = "examples/graph_coloring/toy_graph_coloring.pl"
        if not Path(filepath).exists():
            pytest.skip(f"Example file not found: {filepath}")

        result = parse_file(filepath)
        assert isinstance(result, Program)
        assert len(result.items) > 0
        # Should start with module directive
        assert isinstance(result.items[0], Directive)

    def test_toy_meta_file(self) -> None:
        """Test parsing toy_meta.pl example file."""
        filepath = "examples/graph_coloring/toy_meta.pl"
        if not Path(filepath).exists():
            pytest.skip(f"Example file not found: {filepath}")

        result = parse_file(filepath)
        assert isinstance(result, Program)
        assert len(result.items) > 0

    def test_spec_toy_graph_coloring_file(self) -> None:
        """Test parsing spec/toy_graph_coloring.pl example file."""
        filepath = "examples/graph_coloring/spec/toy_graph_coloring.pl"
        if not Path(filepath).exists():
            pytest.skip(f"Example file not found: {filepath}")

        result = parse_file(filepath)
        assert isinstance(result, Program)
        assert len(result.items) > 0

    def test_spec_toy_meta_file(self) -> None:
        """Test parsing spec/toy_meta.pl example file."""
        filepath = "examples/graph_coloring/spec/toy_meta.pl"
        if not Path(filepath).exists():
            pytest.skip(f"Example file not found: {filepath}")

        result = parse_file(filepath)
        assert isinstance(result, Program)
        assert len(result.items) > 0

    def test_all_example_files_parse(self) -> None:
        """Test that all example files can be parsed without errors."""
        example_files = [
            "examples/list_membership/list_member.pl",
            "examples/input_callback/input_loop.pl",
            "examples/graph_coloring/toy_graph_coloring.pl",
            "examples/graph_coloring/toy_meta.pl",
            "examples/graph_coloring/spec/toy_graph_coloring.pl",
            "examples/graph_coloring/spec/toy_meta.pl",
        ]

        parsed_count = 0
        for filepath in example_files:
            if Path(filepath).exists():
                result = parse_file(filepath)
                assert isinstance(result, Program)
                assert len(result.items) > 0
                parsed_count += 1

        # At least some files should be parsed
        assert parsed_count > 0


class TestParseErrors:
    """Tests for parse error handling."""

    def test_invalid_syntax(self) -> None:
        """Test that invalid syntax raises an error."""
        with pytest.raises(Exception):
            parse_term("@@@")

    def test_unclosed_list(self) -> None:
        """Test that unclosed list raises an error."""
        with pytest.raises(Exception):
            parse_term("[1, 2, 3")

    def test_unclosed_compound(self) -> None:
        """Test that unclosed compound raises an error."""
        with pytest.raises(Exception):
            parse_term("f(a, b")

    def test_missing_clause_terminator(self) -> None:
        """Test that missing clause terminator raises an error."""
        with pytest.raises(Exception):
            parse_clause("fact(a)")
