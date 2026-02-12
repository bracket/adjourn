"""Prolog parser submodule for the constraint checking system.

This module provides parsing capabilities for Prolog terms, clauses, and programs
using the Lark parser generator. It converts Prolog source code into Python AST
representations that can be used for further processing and serialization.

Public API:
    parse_term: Parse a Prolog term from a string
    parse_clause: Parse a Prolog clause or directive from a string
    parse_program: Parse a complete Prolog program from a string
    parse_file: Parse a Prolog file
    from_dict: Reconstruct an AST node from a JSON dictionary
    format_term: Format a term as a pretty-printed string
    print_term: Print a term with pretty-printing

AST Classes:
    Atom, Variable, Integer, Float, String, Compound, List, Clause, Directive, Program
"""

__all__ = [
    # Parser functions
    "parse_term",
    "parse_clause",
    "parse_program",
    "parse_file",
    # JSON serialization
    "from_dict",
    # Pretty-printing
    "format_term",
    "print_term",
    # AST classes
    "Atom",
    "Variable",
    "Integer",
    "Float",
    "String",
    "Compound",
    "List",
    "Clause",
    "Directive",
    "Program",
]

from constraint.parser.ast import (
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
    format_term,
    from_dict,
    print_term,
)
from constraint.parser.parser import (
    parse_clause,
    parse_file,
    parse_program,
    parse_term,
)
