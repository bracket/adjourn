"""AST node definitions for Prolog parse trees.

This module defines the AST (Abstract Syntax Tree) node classes used to represent
parsed Prolog terms, clauses, and programs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, TypeAlias

# Type alias for JSON-serializable data
JSONDict: TypeAlias = dict[str, Any]

# Atoms that match [a-z][a-zA-Z0-9_]* are safe to write unquoted.
# Any other atom (uppercase initial, special characters, etc.) must be
# single-quoted so that SWI-Prolog does not misread it as a variable.
_SIMPLE_ATOM = re.compile(r"^[a-z][a-zA-Z0-9_]*$")

_INFIX_OPS = frozenset(
    {",", ";", "->", ":-", "=", "\\=", "is", "<", ">", "=<", ">=", "==", "\\=="}
)


def _arg_str(arg: Any) -> str:
    """Serialize a term for use as an argument, parenthesizing infix
    operator compounds so they don't flatten into the enclosing functor's
    argument list (e.g. rule(p, (a, b)) must not render as rule(p, a, b))."""

    if isinstance(arg, Compound) and len(arg.args) == 2 and arg.functor in _INFIX_OPS:
        return f"({arg})"

    return str(arg)

def _format_infix(arg0: str, functor: str, arg1: str) -> str:
    """Format a binary infix expression."""
    if functor == ",":
        return f"{arg0}, {arg1}"
    return f"{arg0} {functor} {arg1}"


@dataclass
class Atom:
    """Represents a Prolog atom (e.g., 'hello', 'a')."""

    value: str

    def __str__(self) -> str:
        if _SIMPLE_ATOM.match(self.value):
            return self.value
        # Atoms that need quoting: escape backslashes first, then single quotes,
        # then wrap in single quotes so SWI-Prolog reads them as atoms rather
        # than variables or operators.
        escaped = self.value.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"

    def to_dict(self) -> JSONDict:
        """Convert to JSON-serializable dictionary."""
        return {"type": "Atom", "value": self.value}


@dataclass
class Variable:
    """Represents a Prolog variable (e.g., X, _Result)."""

    name: str

    def __str__(self) -> str:
        return self.name

    def to_dict(self) -> JSONDict:
        """Convert to JSON-serializable dictionary."""
        return {"type": "Variable", "name": self.name}


@dataclass
class Integer:
    """Represents an integer literal."""

    value: int

    def __str__(self) -> str:
        return str(self.value)

    def to_dict(self) -> JSONDict:
        """Convert to JSON-serializable dictionary."""
        return {"type": "Integer", "value": self.value}


@dataclass
class Float:
    """Represents a floating-point literal."""

    value: float

    def __str__(self) -> str:
        return str(self.value)

    def to_dict(self) -> JSONDict:
        """Convert to JSON-serializable dictionary."""
        return {"type": "Float", "value": self.value}


@dataclass
class String:
    """Represents a string literal (e.g., "hello")."""

    value: str

    def __str__(self) -> str:
        return f'"{self.value}"'

    def to_dict(self) -> JSONDict:
        """Convert to JSON-serializable dictionary."""
        return {"type": "String", "value": self.value}


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

        if len(self.args) == 2 and self.functor in _INFIX_OPS:
            return _format_infix(_arg_str(self.args[0]), self.functor, str(self.args[1]))

        args_str = ", ".join(_arg_str(arg) for arg in self.args)
        return f"{self.functor}({args_str})"

    def to_dict(self) -> JSONDict:
        """Convert to JSON-serializable dictionary."""
        return {
            "type": "Compound",
            "functor": self.functor,
            "args": [_term_to_dict(arg) for arg in self.args],
        }


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

    def to_dict(self) -> JSONDict:
        """Convert to JSON-serializable dictionary."""
        result: JSONDict = {
            "type": "List",
            "elements": [_term_to_dict(e) for e in self.elements],
        }
        if self.tail is not None:
            result["tail"] = _term_to_dict(self.tail)
        return result


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

    def to_dict(self) -> JSONDict:
        """Convert to JSON-serializable dictionary."""
        result: JSONDict = {
            "type": "Clause",
            "head": _term_to_dict(self.head),
        }
        if self.body is not None:
            result["body"] = _term_to_dict(self.body)
        return result


@dataclass
class Directive:
    """Represents a Prolog directive (e.g., :- module(...)).
    
    Args:
        term: The directive term
    """

    term: Any

    def __str__(self) -> str:
        return f":- {self.term}."

    def to_dict(self) -> JSONDict:
        """Convert to JSON-serializable dictionary."""
        return {
            "type": "Directive",
            "term": _term_to_dict(self.term),
        }


@dataclass
class Program:
    """Represents a complete Prolog program (list of clauses and directives).
    
    Args:
        items: List of clauses and directives
    """

    items: list[Any]

    def __str__(self) -> str:
        return "\n".join(str(item) for item in self.items)

    def to_dict(self) -> JSONDict:
        """Convert to JSON-serializable dictionary."""
        return {
            "type": "Program",
            "items": [_term_to_dict(item) for item in self.items],
        }


def _term_to_dict(term: Any) -> JSONDict | Any:
    """Convert a term to a JSON-serializable dictionary.
    
    Args:
        term: An AST node or primitive value
        
    Returns:
        JSON-serializable dictionary or primitive value
    """
    if hasattr(term, "to_dict"):
        return term.to_dict()
    return term


def from_dict(data: JSONDict) -> Any:
    """Reconstruct an AST node from a JSON-serializable dictionary.
    
    Args:
        data: Dictionary representation of an AST node
        
    Returns:
        Reconstructed AST node
        
    Raises:
        ValueError: If the type is unknown or data is invalid
    """
    if not isinstance(data, dict) or "type" not in data:
        return data
    
    node_type = data["type"]
    
    if node_type == "Atom":
        return Atom(value=data["value"])
    elif node_type == "Variable":
        return Variable(name=data["name"])
    elif node_type == "Integer":
        return Integer(value=data["value"])
    elif node_type == "Float":
        return Float(value=data["value"])
    elif node_type == "String":
        return String(value=data["value"])
    elif node_type == "Compound":
        return Compound(
            functor=data["functor"],
            args=[from_dict(arg) for arg in data["args"]],
        )
    elif node_type == "List":
        elements = [from_dict(e) for e in data["elements"]]
        tail = from_dict(data["tail"]) if "tail" in data else None
        return List(elements=elements, tail=tail)
    elif node_type == "Clause":
        head = from_dict(data["head"])
        body = from_dict(data["body"]) if "body" in data else None
        return Clause(head=head, body=body)
    elif node_type == "Directive":
        return Directive(term=from_dict(data["term"]))
    elif node_type == "Program":
        return Program(items=[from_dict(item) for item in data["items"]])
    else:
        raise ValueError(f"Unknown AST node type: {node_type}")

def _paren_if_infix(arg: Any, rendered: str) -> str:
    """Wrap an already-rendered arg string in parens if the term is an
    infix operator compound."""
    if isinstance(arg, Compound) and len(arg.args) == 2 and arg.functor in _INFIX_OPS:
        return f"({rendered})"

    return rendered

def format_term(term: Any, indent: int = 0, indent_size: int = 2) -> str:
    """Format a term as a pretty-printed string with indentation.
    
    Args:
        term: The term to format (should be an AST node)
        indent: Current indentation level (default: 0)
        indent_size: Number of spaces per indentation level (default: 2)
        
    Returns:
        Pretty-printed string representation of the term
    """
    prefix = " " * (indent * indent_size)
    
    if isinstance(term, (Atom, Variable, Integer, Float, String)):
        return f"{prefix}{term}"
    elif isinstance(term, Compound):
        if len(term.args) == 2 and term.functor in _INFIX_OPS:
            arg0_str = format_term(term.args[0], 0, indent_size).strip()
            arg1_str = format_term(term.args[1], 0, indent_size).strip()

            arg0_str = _paren_if_infix(term.args[0], arg0_str)
            arg1_str = _paren_if_infix(term.args[1], arg1_str)

            return f"{prefix}{_format_infix(arg0_str, term.functor, arg1_str)}"

        if not term.args:
            return f"{prefix}{term.functor}"

        if len(term.args) == 1:
            # Single arg can be on same line
            arg_str = format_term(term.args[0], 0, indent_size).strip()
            return f"{prefix}{term.functor}({arg_str})"

        # Multiple args: one per line
        lines = [f"{prefix}{term.functor}("]
        for i, arg in enumerate(term.args):
            arg_str = format_term(arg, indent + 1, indent_size).strip()
            arg_str = _paren_if_infix(arg, arg_str)

            separator = "," if i < len(term.args) - 1 else ""
            lines.append(f"{' ' * ((indent + 1) * indent_size)}{arg_str}{separator}")
        lines.append(f"{prefix})")
        return "\n".join(lines)
    elif isinstance(term, List):
        if not term.elements and term.tail is None:
            return f"{prefix}[]"
        if len(term.elements) == 1 and term.tail is None:
            # Single element can be on same line
            elem_str = format_term(term.elements[0], 0, indent_size).strip()
            return f"{prefix}[{elem_str}]"
        if len(term.elements) == 1 and term.tail is not None:
            elem_str = format_term(term.elements[0], 0, indent_size).strip()
            tail_str = format_term(term.tail, 0, indent_size).strip()
            return f"{prefix}[{elem_str}|{tail_str}]"
        # Multiple elements: one per line
        lines = [f"{prefix}["]
        for i, elem in enumerate(term.elements):
            elem_str = format_term(elem, indent + 1, indent_size).strip()
            separator = "," if i < len(term.elements) - 1 else ""
            lines.append(f"{' ' * ((indent + 1) * indent_size)}{elem_str}{separator}")
        if term.tail is not None:
            tail_str = format_term(term.tail, indent + 1, indent_size).strip()
            lines.append(f"{' ' * ((indent + 1) * indent_size)}|{tail_str}")
        lines.append(f"{prefix}]")
        return "\n".join(lines)
    else:
        # Fallback to string representation
        return f"{prefix}{term}"


def print_term(term: Any, indent: int = 0, indent_size: int = 2) -> None:
    """Print a term with pretty-printing and indentation.
    
    Args:
        term: The term to print (should be an AST node)
        indent: Current indentation level (default: 0)
        indent_size: Number of spaces per indentation level (default: 2)
    """
    print(format_term(term, indent, indent_size))
