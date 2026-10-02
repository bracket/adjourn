"""Tests for the Prolog parser module."""

from __future__ import annotations

from pathlib import Path

import pytest

from adjourn.parser import (
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


def find_git_root() -> Path | None:
    """Find the git repository root by searching upward for .git directory.

    Returns:
        Path to git root, or None if not found
    """
    current = Path.cwd()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return None


def get_example_file_path(relative_path: str) -> Path:
    """Get absolute path to example file, handling different test execution contexts.

    Args:
        relative_path: Path relative to git root (e.g., "examples/list_membership/list_member.pl")

    Returns:
        Absolute Path to the file

    Raises:
        pytest.skip: If git root not found or file doesn't exist
    """
    git_root = find_git_root()
    if git_root is None:
        pytest.skip("Git root not found - cannot locate example files")

    file_path = git_root / relative_path
    if not file_path.exists():
        pytest.skip(f"Example file not found: {file_path}")

    return file_path


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

    def test_rule_string_renders_infix_body(self) -> None:
        """Test clause string rendering uses infix style in body."""
        result = parse_clause("a :- b, c.")
        assert str(result) == "a :- b, c."

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
        filepath = get_example_file_path("examples/list_membership/list_member.pl")
        result = parse_file(str(filepath))
        assert isinstance(result, Program)
        assert len(result.items) == 2
        # Should have two clauses for member/2
        assert all(isinstance(item, Clause) for item in result.items)

    def test_input_callback_file(self) -> None:
        """Test parsing input_loop.pl example file."""
        filepath = get_example_file_path("examples/input_callback/input_loop.pl")
        result = parse_file(str(filepath))
        assert isinstance(result, Program)
        assert len(result.items) > 0

    def test_toy_graph_coloring_file(self) -> None:
        """Test parsing toy_graph_coloring.pl example file."""
        filepath = get_example_file_path("examples/graph_coloring/toy_graph_coloring.pl")
        result = parse_file(str(filepath))
        assert isinstance(result, Program)
        assert len(result.items) > 0
        # Should start with module directive
        assert isinstance(result.items[0], Directive)

    def test_toy_meta_file(self) -> None:
        """Test parsing toy_meta.pl example file."""
        filepath = get_example_file_path("examples/graph_coloring/toy_meta.pl")
        result = parse_file(str(filepath))
        assert isinstance(result, Program)
        assert len(result.items) > 0

    def test_spec_toy_graph_coloring_file(self) -> None:
        """Test parsing spec/toy_graph_coloring.pl example file."""
        filepath = get_example_file_path("examples/graph_coloring/spec/toy_graph_coloring.pl")
        result = parse_file(str(filepath))
        assert isinstance(result, Program)
        assert len(result.items) > 0

    def test_spec_toy_meta_file(self) -> None:
        """Test parsing spec/toy_meta.pl example file."""
        filepath = get_example_file_path("examples/graph_coloring/spec/toy_meta.pl")
        result = parse_file(str(filepath))
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
        for relative_path in example_files:
            try:
                filepath = get_example_file_path(relative_path)
                result = parse_file(str(filepath))
                assert isinstance(result, Program)
                assert len(result.items) > 0
                parsed_count += 1
            except pytest.skip.Exception:
                # File not found, skip it
                pass

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


class TestJSONRoundTrip:
    """Tests for JSON serialization and deserialization."""

    def test_atom_json_roundtrip(self) -> None:
        """Test JSON round-trip for atoms."""
        from adjourn.parser import from_dict

        original = Atom("hello")
        json_dict = original.to_dict()
        reconstructed = from_dict(json_dict)

        assert isinstance(reconstructed, Atom)
        assert reconstructed.value == original.value
        assert reconstructed == original

    def test_variable_json_roundtrip(self) -> None:
        """Test JSON round-trip for variables."""
        from adjourn.parser import from_dict

        original = Variable("X")
        json_dict = original.to_dict()
        reconstructed = from_dict(json_dict)

        assert isinstance(reconstructed, Variable)
        assert reconstructed.name == original.name
        assert reconstructed == original

    def test_integer_json_roundtrip(self) -> None:
        """Test JSON round-trip for integers."""
        from adjourn.parser import from_dict

        original = Integer(42)
        json_dict = original.to_dict()
        reconstructed = from_dict(json_dict)

        assert isinstance(reconstructed, Integer)
        assert reconstructed.value == original.value
        assert reconstructed == original

    def test_float_json_roundtrip(self) -> None:
        """Test JSON round-trip for floats."""
        from adjourn.parser import from_dict

        original = Float(3.14)
        json_dict = original.to_dict()
        reconstructed = from_dict(json_dict)

        assert isinstance(reconstructed, Float)
        assert reconstructed.value == original.value
        assert reconstructed == original

    def test_string_json_roundtrip(self) -> None:
        """Test JSON round-trip for strings."""
        from adjourn.parser import from_dict

        original = String("hello world")
        json_dict = original.to_dict()
        reconstructed = from_dict(json_dict)

        assert isinstance(reconstructed, String)
        assert reconstructed.value == original.value
        assert reconstructed == original

    def test_simple_compound_json_roundtrip(self) -> None:
        """Test JSON round-trip for simple compound terms."""
        from adjourn.parser import from_dict

        original = Compound("f", [Atom("a"), Atom("b")])
        json_dict = original.to_dict()
        reconstructed = from_dict(json_dict)

        assert isinstance(reconstructed, Compound)
        assert reconstructed.functor == original.functor
        assert len(reconstructed.args) == len(original.args)
        assert reconstructed == original

    def test_nested_compound_json_roundtrip(self) -> None:
        """Test JSON round-trip for nested compound terms."""
        from adjourn.parser import from_dict

        original = Compound("f", [
            Compound("g", [Atom("a")]),
            Compound("h", [Integer(1), Variable("X")])
        ])
        json_dict = original.to_dict()
        reconstructed = from_dict(json_dict)

        assert isinstance(reconstructed, Compound)
        assert reconstructed == original

    def test_simple_list_json_roundtrip(self) -> None:
        """Test JSON round-trip for simple lists."""
        from adjourn.parser import from_dict

        original = List([Atom("a"), Atom("b"), Atom("c")])
        json_dict = original.to_dict()
        reconstructed = from_dict(json_dict)

        assert isinstance(reconstructed, List)
        assert len(reconstructed.elements) == len(original.elements)
        assert reconstructed.tail == original.tail
        assert reconstructed == original

    def test_list_with_tail_json_roundtrip(self) -> None:
        """Test JSON round-trip for lists with tail."""
        from adjourn.parser import from_dict

        original = List([Atom("a"), Atom("b")], tail=Variable("T"))
        json_dict = original.to_dict()
        reconstructed = from_dict(json_dict)

        assert isinstance(reconstructed, List)
        assert reconstructed == original
        assert isinstance(reconstructed.tail, Variable)

    def test_fact_clause_json_roundtrip(self) -> None:
        """Test JSON round-trip for fact clauses."""
        from adjourn.parser import from_dict

        original = Clause(head=Compound("parent", [Atom("alice"), Atom("bob")]))
        json_dict = original.to_dict()
        reconstructed = from_dict(json_dict)

        assert isinstance(reconstructed, Clause)
        assert reconstructed.body is None
        assert reconstructed == original

    def test_rule_clause_json_roundtrip(self) -> None:
        """Test JSON round-trip for rule clauses."""
        from adjourn.parser import from_dict

        original = Clause(
            head=Compound("ancestor", [Variable("X"), Variable("Y")]),
            body=Compound("parent", [Variable("X"), Variable("Y")])
        )
        json_dict = original.to_dict()
        reconstructed = from_dict(json_dict)

        assert isinstance(reconstructed, Clause)
        assert reconstructed.body is not None
        assert reconstructed == original

    def test_directive_json_roundtrip(self) -> None:
        """Test JSON round-trip for directives."""
        from adjourn.parser import from_dict

        original = Directive(term=Compound("module", [Atom("test")]))
        json_dict = original.to_dict()
        reconstructed = from_dict(json_dict)

        assert isinstance(reconstructed, Directive)
        assert reconstructed == original

    def test_program_json_roundtrip(self) -> None:
        """Test JSON round-trip for programs."""
        from adjourn.parser import from_dict

        original = Program(items=[
            Clause(head=Compound("fact", [Atom("a")])),
            Directive(term=Compound("module", [Atom("test")])),
        ])
        json_dict = original.to_dict()
        reconstructed = from_dict(json_dict)

        assert isinstance(reconstructed, Program)
        assert len(reconstructed.items) == len(original.items)
        assert reconstructed == original

    def test_parsed_term_json_roundtrip(self) -> None:
        """Test JSON round-trip for a parsed term."""
        from adjourn.parser import from_dict

        original = parse_term("f(g(a), h(1, X))")
        json_dict = original.to_dict()
        reconstructed = from_dict(json_dict)

        assert reconstructed == original

    def test_parsed_clause_json_roundtrip(self) -> None:
        """Test JSON round-trip for a parsed clause."""
        from adjourn.parser import from_dict

        original = parse_clause("ancestor(X, Y) :- parent(X, Y).")
        json_dict = original.to_dict()
        reconstructed = from_dict(json_dict)

        assert reconstructed == original

    def test_json_dict_structure(self) -> None:
        """Test that JSON dict has correct structure."""
        term = Compound("f", [Atom("a"), Integer(1)])
        json_dict = term.to_dict()

        assert json_dict["type"] == "Compound"
        assert json_dict["functor"] == "f"
        assert len(json_dict["args"]) == 2
        assert json_dict["args"][0]["type"] == "Atom"
        assert json_dict["args"][0]["value"] == "a"
        assert json_dict["args"][1]["type"] == "Integer"
        assert json_dict["args"][1]["value"] == 1


class TestTermPrettyPrint:
    """Tests for term pretty-printing."""

    def test_format_atom(self) -> None:
        """Test formatting an atom."""
        from adjourn.parser import format_term

        term = Atom("hello")
        result = format_term(term)
        assert result == "hello"

    def test_format_variable(self) -> None:
        """Test formatting a variable."""
        from adjourn.parser import format_term

        term = Variable("X")
        result = format_term(term)
        assert result == "X"

    def test_format_integer(self) -> None:
        """Test formatting an integer."""
        from adjourn.parser import format_term

        term = Integer(42)
        result = format_term(term)
        assert result == "42"

    def test_format_float(self) -> None:
        """Test formatting a float."""
        from adjourn.parser import format_term

        term = Float(3.14)
        result = format_term(term)
        assert result == "3.14"

    def test_format_string(self) -> None:
        """Test formatting a string."""
        from adjourn.parser import format_term

        term = String("hello")
        result = format_term(term)
        assert result == '"hello"'

    def test_format_simple_compound(self) -> None:
        """Test formatting a simple compound with one arg."""
        from adjourn.parser import format_term

        term = Compound("f", [Atom("a")])
        result = format_term(term)
        assert result == "f(a)"

    def test_format_compound_no_args(self) -> None:
        """Test formatting a compound with no args."""
        from adjourn.parser import format_term

        term = Compound("f", [])
        result = format_term(term)
        assert result == "f"

    def test_format_multiarg_compound(self) -> None:
        """Test formatting a compound with multiple args."""
        from adjourn.parser import format_term

        term = Compound("f", [Atom("a"), Atom("b"), Atom("c")])
        result = format_term(term)
        lines = result.split("\n")

        assert lines[0] == "f("
        assert "  a," in lines[1]
        assert "  b," in lines[2]
        assert "  c" in lines[3]
        assert lines[4] == ")"

    def test_format_nested_compound(self) -> None:
        """Test formatting nested compound terms."""
        from adjourn.parser import format_term

        term = Compound("f", [
            Compound("g", [Atom("a")]),
            Compound("h", [Atom("b")])
        ])
        result = format_term(term)

        # Should have proper indentation
        assert "f(" in result
        assert "  g(a)," in result
        assert "  h(b)" in result
        assert ")" in result

    def test_format_empty_list(self) -> None:
        """Test formatting an empty list."""
        from adjourn.parser import format_term

        term = List([])
        result = format_term(term)
        assert result == "[]"

    def test_format_single_element_list(self) -> None:
        """Test formatting a list with one element."""
        from adjourn.parser import format_term

        term = List([Atom("a")])
        result = format_term(term)
        assert result == "[a]"

    def test_format_multielement_list(self) -> None:
        """Test formatting a list with multiple elements."""
        from adjourn.parser import format_term

        term = List([Atom("a"), Atom("b"), Atom("c")])
        result = format_term(term)
        lines = result.split("\n")

        assert lines[0] == "["
        assert "  a," in lines[1]
        assert "  b," in lines[2]
        assert "  c" in lines[3]
        assert lines[4] == "]"

    def test_format_list_with_tail(self) -> None:
        """Test formatting a list with tail."""
        from adjourn.parser import format_term

        term = List([Atom("a"), Atom("b")], tail=Variable("T"))
        result = format_term(term)

        assert "[" in result
        assert "  a," in result
        assert "  b" in result
        assert "  |T" in result
        assert "]" in result

    def test_format_parsed_list_with_tail_has_no_extra_comma(self) -> None:
        """Test formatting parsed [H|T] list has no comma before tail bar."""
        from adjourn.parser import format_term

        term = parse_term("[H|T]")
        result = format_term(term)
        assert result == "[H|T]"

    def test_format_parsed_member_list_tail(self) -> None:
        """Test formatting parsed member/2 renders list tail correctly."""
        from adjourn.parser import format_term

        term = parse_term("member(X, [H|T])")
        result = format_term(term)
        assert "[H|T]" in result
        assert ", |" not in result

    def test_format_parsed_clause_with_infix_body(self) -> None:
        """Test formatting parsed clause renders conjunction body as infix."""
        from adjourn.parser import format_term

        clause = parse_clause("a :- b, c.")
        result = format_term(clause)
        assert result == "a :- b, c."

    def test_format_with_custom_indent(self) -> None:
        """Test formatting with custom indentation."""
        from adjourn.parser import format_term

        term = Compound("f", [Atom("a"), Atom("b")])
        result = format_term(term, indent=1, indent_size=4)
        lines = result.split("\n")

        # Should start with 4 spaces (1 level * 4 spaces)
        assert lines[0] == "    f("
        # Args should have 8 spaces (2 levels * 4 spaces)
        assert "        a," in lines[1]

    def test_print_term_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test that print_term outputs the formatted string."""
        from adjourn.parser import print_term

        term = Atom("hello")
        print_term(term)
        captured = capsys.readouterr()
        assert captured.out == "hello\n"

    def test_format_parsed_term(self) -> None:
        """Test formatting a parsed term."""
        from adjourn.parser import format_term

        term = parse_term("f(a, b, c)")
        result = format_term(term)

        # Should format with multiple lines
        assert "f(" in result
        assert ")" in result
