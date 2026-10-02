"""Main Prolog parser implementation using Lark.

This module provides the main parser interface for parsing Prolog terms, clauses,
and programs into AST representations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lark import Lark, Token, Transformer

from adjourn.parser.ast import (
    Atom,
    Clause,
    Compound,
    Directive,
    Float,
    Integer,
    Program,
    String,
    Variable,
)
from adjourn.parser.ast import (
    List as ASTList,
)
from adjourn.parser.grammar import PROLOG_GRAMMAR


class PrologTransformer(Transformer):
    """Lark transformer that converts parse trees to AST nodes."""

    # Atoms and variables
    def atom(self, items: list[Any]) -> Atom:
        """Transform atom to Atom AST node."""
        # items[0] is the token string value
        value = str(items[0]) if items else ""
        # Remove quotes from quoted atoms
        if value.startswith("'") and value.endswith("'"):
            # Unescape the atom content
            value = value[1:-1].replace("\\'", "'").replace("\\\\", "\\")
        return Atom(value)

    def variable(self, items: list[Token]) -> Variable:
        """Transform variable token to Variable AST node."""
        return Variable(str(items[0]))

    # Numbers
    def integer(self, items: list[Token]) -> Integer:
        """Transform integer token to Integer AST node."""
        return Integer(int(items[0]))

    def float(self, items: list[Token]) -> Float:
        """Transform float token to Float AST node."""
        return Float(float(items[0]))

    def number(self, items: list[Any]) -> Any:
        """Pass through number nodes."""
        return items[0]

    # Strings
    def string(self, items: list[Token]) -> String:
        """Transform string token to String AST node."""
        value = str(items[0])
        # Remove quotes and unescape
        value = value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        return String(value)

    # Compounds
    def compound_no_args(self, items: list[Atom]) -> Compound:
        """Transform compound with no arguments."""
        functor = items[0]
        return Compound(functor.value, [])

    def compound_with_args(self, items: list[Any]) -> Compound:
        """Transform compound with arguments."""
        functor = items[0]
        # All remaining items are arguments
        args = items[1:]
        return Compound(functor.value, args)

    # Lists
    def empty_list(self, items: list[Any]) -> ASTList:
        """Transform empty list."""
        return ASTList([])

    def list_single(self, items: list[Any]) -> ASTList:
        """Transform single-element list."""
        return ASTList([items[0]])

    def list_elements(self, items: list[Any]) -> ASTList:
        """Transform list with multiple elements."""
        return ASTList(items)

    def list_with_tail(self, items: list[Any]) -> ASTList:
        """Transform list with tail [H|T]."""
        return ASTList([items[0]], tail=items[1])

    def list_elements_with_tail(self, items: list[Any]) -> ASTList:
        """Transform list with elements and tail [H1, H2|T]."""
        # All but last item are elements, last is tail
        return ASTList(items[:-1], tail=items[-1])

    def list(self, items: list[Any]) -> ASTList:
        """Pass through list node."""
        if not items:
            return ASTList([])
        return items[0]

    # Curly braces
    def empty_curly(self, items: list[Any]) -> Compound:
        """Transform {} to compound."""
        return Compound("{}", [])

    def curly_term(self, items: list[Any]) -> Compound:
        """Transform {Term} to compound."""
        return Compound("{}", items)

    # Cut
    def cut(self, items: list[Any]) -> Atom:
        """Transform ! to atom."""
        return Atom("!")

    # Binary operators - create compound terms
    def _make_op(self, op: str, items: list[Any]) -> Compound:
        """Helper to create operator compound terms."""
        return Compound(op, items)

    # Precedence 1200
    def op_if(self, items: list[Any]) -> Compound:
        return self._make_op(":-", items)

    def op_dcg(self, items: list[Any]) -> Compound:
        return self._make_op("-->", items)

    # Precedence 1150 - prefix operators
    def op_multifile(self, items: list[Any]) -> Compound:
        return self._make_op("multifile", items)

    def op_dynamic(self, items: list[Any]) -> Compound:
        return self._make_op("dynamic", items)

    def op_discontiguous(self, items: list[Any]) -> Compound:
        return self._make_op("discontiguous", items)

    def op_volatile(self, items: list[Any]) -> Compound:
        return self._make_op("volatile", items)

    def op_thread_local(self, items: list[Any]) -> Compound:
        return self._make_op("thread_local", items)

    def op_initialization(self, items: list[Any]) -> Compound:
        return self._make_op("initialization", items)

    def op_thread_initialization(self, items: list[Any]) -> Compound:
        return self._make_op("thread_initialization", items)

    def op_module_transparent(self, items: list[Any]) -> Compound:
        return self._make_op("module_transparent", items)

    def op_meta_predicate(self, items: list[Any]) -> Compound:
        return self._make_op("meta_predicate", items)

    def op_public(self, items: list[Any]) -> Compound:
        return self._make_op("public", items)

    def op_table(self, items: list[Any]) -> Compound:
        return self._make_op("table", items)

    # Precedence 1100
    def op_semicolon(self, items: list[Any]) -> Compound:
        return self._make_op(";", items)

    # Precedence 1050
    def op_if_then(self, items: list[Any]) -> Compound:
        return self._make_op("->", items)

    def op_soft_cut(self, items: list[Any]) -> Compound:
        return self._make_op("*->", items)

    # Precedence 1000
    def op_comma(self, items: list[Any]) -> Compound:
        return self._make_op(",", items)

    # Precedence 900
    def op_not(self, items: list[Any]) -> Compound:
        return self._make_op("\\+", items)

    # Precedence 700 - comparison
    def op_unify(self, items: list[Any]) -> Compound:
        return self._make_op("=", items)

    def op_not_unify(self, items: list[Any]) -> Compound:
        return self._make_op("\\=", items)

    def op_eq(self, items: list[Any]) -> Compound:
        return self._make_op("==", items)

    def op_neq(self, items: list[Any]) -> Compound:
        return self._make_op("\\==", items)

    def op_term_lt(self, items: list[Any]) -> Compound:
        return self._make_op("@<", items)

    def op_term_le(self, items: list[Any]) -> Compound:
        return self._make_op("@=<", items)

    def op_term_gt(self, items: list[Any]) -> Compound:
        return self._make_op("@>", items)

    def op_term_ge(self, items: list[Any]) -> Compound:
        return self._make_op("@>=", items)

    def op_univ(self, items: list[Any]) -> Compound:
        return self._make_op("=..", items)

    def op_is(self, items: list[Any]) -> Compound:
        return self._make_op("is", items)

    def op_arith_eq(self, items: list[Any]) -> Compound:
        return self._make_op("=:=", items)

    def op_arith_neq(self, items: list[Any]) -> Compound:
        return self._make_op("=\\=", items)

    def op_lt(self, items: list[Any]) -> Compound:
        return self._make_op("<", items)

    def op_le(self, items: list[Any]) -> Compound:
        return self._make_op("=<", items)

    def op_gt(self, items: list[Any]) -> Compound:
        return self._make_op(">", items)

    def op_ge(self, items: list[Any]) -> Compound:
        return self._make_op(">=", items)

    def op_partial_unify(self, items: list[Any]) -> Compound:
        return self._make_op(">:<", items)

    def op_selectchk(self, items: list[Any]) -> Compound:
        return self._make_op(":<", items)

    def op_structural_eq(self, items: list[Any]) -> Compound:
        return self._make_op("=@=", items)

    def op_structural_neq(self, items: list[Any]) -> Compound:
        return self._make_op("\\=@=", items)

    # Precedence 600
    def op_module_qual(self, items: list[Any]) -> Compound:
        return self._make_op(":", items)

    # Precedence 500
    def op_plus(self, items: list[Any]) -> Compound:
        return self._make_op("+", items)

    def op_minus(self, items: list[Any]) -> Compound:
        return self._make_op("-", items)

    def op_bitwise_and(self, items: list[Any]) -> Compound:
        return self._make_op("/\\", items)

    def op_bitwise_or(self, items: list[Any]) -> Compound:
        return self._make_op("\\/", items)

    # Precedence 400
    def op_multiply(self, items: list[Any]) -> Compound:
        return self._make_op("*", items)

    def op_divide(self, items: list[Any]) -> Compound:
        return self._make_op("/", items)

    def op_int_divide(self, items: list[Any]) -> Compound:
        return self._make_op("//", items)

    def op_div(self, items: list[Any]) -> Compound:
        return self._make_op("div", items)

    def op_rem(self, items: list[Any]) -> Compound:
        return self._make_op("rem", items)

    def op_mod(self, items: list[Any]) -> Compound:
        return self._make_op("mod", items)

    def op_shift_left(self, items: list[Any]) -> Compound:
        return self._make_op("<<", items)

    def op_shift_right(self, items: list[Any]) -> Compound:
        return self._make_op(">>", items)

    def op_rational_div(self, items: list[Any]) -> Compound:
        return self._make_op("rdiv", items)

    def op_xor(self, items: list[Any]) -> Compound:
        return self._make_op("xor", items)

    # Precedence 200
    def op_power(self, items: list[Any]) -> Compound:
        return self._make_op("**", items)

    def op_caret(self, items: list[Any]) -> Compound:
        return self._make_op("^", items)

    def op_unary_plus(self, items: list[Any]) -> Compound:
        return self._make_op("+", items)

    def op_unary_minus(self, items: list[Any]) -> Compound:
        return self._make_op("-", items)

    def op_bitwise_not(self, items: list[Any]) -> Compound:
        return self._make_op("\\", items)

    # Primary terms
    def primary(self, items: list[Any]) -> Any:
        """Pass through primary term."""
        return items[0]

    # Terms
    def term(self, items: list[Any]) -> Any:
        """Pass through term."""
        return items[0]

    def arg_term(self, items: list[Any]) -> Any:
        """Pass through arg_term (used in compounds and lists)."""
        return items[0]

    def term1200(self, items: list[Any]) -> Any:
        """Pass through term."""
        return items[0]

    def term1150(self, items: list[Any]) -> Any:
        """Pass through term."""
        return items[0]

    def term1100(self, items: list[Any]) -> Any:
        """Pass through term."""
        return items[0]

    def term1050(self, items: list[Any]) -> Any:
        """Pass through term."""
        return items[0]

    def term1000(self, items: list[Any]) -> Any:
        """Pass through term."""
        return items[0]

    def term900(self, items: list[Any]) -> Any:
        """Pass through term."""
        return items[0]

    def term700(self, items: list[Any]) -> Any:
        """Pass through term."""
        return items[0]

    def term600(self, items: list[Any]) -> Any:
        """Pass through term."""
        return items[0]

    def term500(self, items: list[Any]) -> Any:
        """Pass through term."""
        return items[0]

    def term400(self, items: list[Any]) -> Any:
        """Pass through term."""
        return items[0]

    def term200(self, items: list[Any]) -> Any:
        """Pass through term."""
        return items[0]

    # Clauses and directives
    def clause_term(self, items: list[Any]) -> Any:
        """Pass through clause term."""
        return items[0]

    def clause_body(self, items: list[Any]) -> Any:
        """Pass through clause body."""
        return items[0]

    def fact(self, items: list[Any]) -> Clause:
        """Transform fact (clause without body)."""
        return Clause(head=items[0], body=None)

    def rule(self, items: list[Any]) -> Clause:
        """Transform rule (clause with body)."""
        return Clause(head=items[0], body=items[1])

    def clause(self, items: list[Any]) -> Clause:
        """Pass through clause."""
        return items[0]

    def directive(self, items: list[Any]) -> Directive:
        """Transform directive."""
        return Directive(term=items[0])

    def item(self, items: list[Any]) -> Any:
        """Pass through program item."""
        return items[0]

    # Program
    def program(self, items: list[Any]) -> Program:
        """Transform program (list of clauses and directives)."""
        return Program(items=items)

    def start(self, items: list[Any]) -> Program:
        """Entry point - return program."""
        return items[0]


# Create the parser instance
_parser = Lark(PROLOG_GRAMMAR, parser="lalr", transformer=PrologTransformer())


def parse_term(text: str) -> Any:
    """Parse a Prolog term from a string.

    Args:
        text: String containing a Prolog term

    Returns:
        AST node representing the parsed term

    Raises:
        lark.exceptions.LarkError: If parsing fails
    """
    # Add a period to make it a valid program item for parsing
    result = _parser.parse(text.strip() + ".")
    # Extract the term from the clause
    if result.items and isinstance(result.items[0], Clause):
        return result.items[0].head
    return result


def parse_clause(text: str) -> Clause | Directive:
    """Parse a Prolog clause (fact or rule) or directive from a string.

    Args:
        text: String containing a Prolog clause or directive

    Returns:
        Clause or Directive AST node

    Raises:
        lark.exceptions.LarkError: If parsing fails
    """
    result = _parser.parse(text.strip())
    if result.items:
        return result.items[0]
    raise ValueError("No clause found in input")


def parse_program(text: str) -> Program:
    """Parse a complete Prolog program from a string.

    Args:
        text: String containing a Prolog program (multiple clauses/directives)

    Returns:
        Program AST node containing all clauses and directives

    Raises:
        lark.exceptions.LarkError: If parsing fails
    """
    return _parser.parse(text.strip())


def parse_file(filepath: str) -> Program:
    """Parse a Prolog file.

    Args:
        filepath: Path to the Prolog file

    Returns:
        Program AST node containing all clauses and directives

    Raises:
        lark.exceptions.LarkError: If parsing fails
        IOError: If file cannot be read
    """
    content = Path(filepath).read_text(encoding="utf-8")
    return parse_program(content)
