"""Prolog parser submodule for the constraint checking system.

This module provides parsing capabilities for Prolog terms, clauses, and programs
using the Lark parser generator. It converts Prolog source code into Python AST
representations that can be used for further processing and serialization.

Public API:
    parse_term: Parse a Prolog term from a string
    parse_clause: Parse a Prolog clause or directive from a string
    parse_program: Parse a complete Prolog program from a string
    parse_file: Parse a Prolog file

AST Classes:
    Atom, Variable, Integer, Float, String, Compound, List, Clause, Directive, Program
"""

__all__ = [
    # Parser functions
    "parse_term",
    "parse_clause",
    "parse_program",
    "parse_file",
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
)
from constraint.parser.parser import (
    parse_clause,
    parse_file,
    parse_program,
    parse_term,
)
