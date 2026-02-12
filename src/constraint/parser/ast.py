"""AST node definitions for Prolog parse trees.

This module defines the AST (Abstract Syntax Tree) node classes used to represent
parsed Prolog terms, clauses, and programs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Atom:
    """Represents a Prolog atom (e.g., 'hello', 'a')."""

    value: str

    def __str__(self) -> str:
        return self.value


@dataclass
class Variable:
    """Represents a Prolog variable (e.g., X, _Result)."""

    name: str

    def __str__(self) -> str:
        return self.name


@dataclass
class Integer:
    """Represents an integer literal."""

    value: int

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class Float:
    """Represents a floating-point literal."""

    value: float

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class String:
    """Represents a string literal (e.g., "hello")."""

    value: str

    def __str__(self) -> str:
        return f'"{self.value}"'


@dataclass
class Compound:
    """Represents a compound term (e.g., f(a, b, c)).
    
    Args:
        functor: The functor name
        args: List of argument terms
    """

    functor: str
    args: list[Any]

    def __str__(self) -> str:
        if not self.args:
            return self.functor
        args_str = ", ".join(str(arg) for arg in self.args)
        return f"{self.functor}({args_str})"


@dataclass
class List:
    """Represents a Prolog list.
    
    Args:
        elements: List of elements
        tail: Optional tail variable (for [H|T] notation), can be None
    """

    elements: list[Any]
    tail: Any = None

    def __str__(self) -> str:
        if self.tail is not None:
            if not self.elements:
                return f"[|{self.tail}]"
            elements_str = ", ".join(str(e) for e in self.elements)
            return f"[{elements_str}|{self.tail}]"
        elements_str = ", ".join(str(e) for e in self.elements)
        return f"[{elements_str}]"


@dataclass
class Clause:
    """Represents a Prolog clause (fact or rule).
    
    Args:
        head: The head term
        body: The body term (None for facts)
    """

    head: Any
    body: Any = None

    def __str__(self) -> str:
        if self.body is None:
            return f"{self.head}."
        return f"{self.head} :- {self.body}."


@dataclass
class Directive:
    """Represents a Prolog directive (e.g., :- module(...)).
    
    Args:
        term: The directive term
    """

    term: Any

    def __str__(self) -> str:
        return f":- {self.term}."


@dataclass
class Program:
    """Represents a complete Prolog program (list of clauses and directives).
    
    Args:
        items: List of clauses and directives
    """

    items: list[Any]

    def __str__(self) -> str:
        return "\n".join(str(item) for item in self.items)
