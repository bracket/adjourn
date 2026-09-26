"""Foreign Python function registry for the adjourn meta-interpreter.

Provides a decorator-based registry of named Python callables that can be
invoked synchronously from Prolog via janus
``py_call(adjourn_foreign:dispatch(Fn, In), Out)``.

Usage (Python side)::

    from adjourn.adjourn_foreign import register

    @register("my_fn")
    def _my_fn(arg):
        return str(arg).upper()

Usage (Prolog side)::

    foreign(my_fn, 'hello', Out)   % Out is unified with 'HELLO'
"""

from __future__ import annotations

import importlib
import subprocess
from collections.abc import Callable
from typing import Any

_registry: dict[str, Callable[[Any], Any]] = {}


def register(name: str) -> Callable[[Callable[[Any], Any]], Callable[[Any], Any]]:
    """Decorator that registers a callable under *name* in the foreign registry.

    Args:
        name: The atom name used to invoke this function from Prolog via
              ``foreign(name, In, Out)``.

    Returns:
        The original callable, unchanged.
    """
    def _decorator(fn: Callable[[Any], Any]) -> Callable[[Any], Any]:
        _registry[name] = fn
        return fn
    return _decorator


def dispatch(fn_name: str, arg: Any) -> Any:
    """Look up *fn_name* in the registry and call it with *arg*.

    Called by the Prolog meta-interpreter via
    ``py_call(adjourn_foreign:dispatch(Fn, In), Out)``.

    Args:
        fn_name: Atom name of the registered function (marshalled by janus
                 from a Prolog atom to a Python string).
        arg:     Input term, marshalled by janus from Prolog to Python.

    Returns:
        The function's return value; janus marshals it back to a Prolog term
        that is unified with ``Out``.

    Raises:
        KeyError: If *fn_name* has not been registered.
    """
    fn = _registry[fn_name]
    return fn(arg)


def load_foreign_plugins(names: list[str]) -> None:
    """Import each named module so its ``@register`` decorators fire.

    Args:
        names: Importable dotted module names in loading order.

    Raises:
        ImportError: If any module cannot be imported.
    """
    for name in names:
        importlib.import_module(name)


# ---------------------------------------------------------------------------
# Additional callout subpackages — imported here so their @register decorators
# fire at module load time and populate the registry.
# ---------------------------------------------------------------------------

import adjourn.subprocess.subprocess as _subprocess_module  # noqa: F401

# ---------------------------------------------------------------------------
# Built-in POC callout: git rev-parse
# ---------------------------------------------------------------------------


@register("git_rev_parse")
def _git_rev_parse(arg: Any) -> str:
    """Run ``git rev-parse <arg>`` and return its stripped stdout.

    Args:
        arg: The argument to pass to ``git rev-parse`` (e.g. ``"HEAD"``).

    Returns:
        The stripped stdout output of the subprocess.

    Raises:
        subprocess.CalledProcessError: If ``git rev-parse`` exits with a
            non-zero status (e.g. the argument is not a valid ref).
    """
    result = subprocess.run(
        ["git", "rev-parse", str(arg)],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()

# ---------------------------------------------------------------------------
# Mnestic query callout (query/3 reduction)
# ---------------------------------------------------------------------------

from adjourn.parser import Compound, parse_term
from adjourn.store.mnestic_adapter import MnesticAdapter, lookup


@register("mnestic_query")
def _mnestic_query(arg: Any) -> list[list[str | int]]:
    """Execute a compiled query against a registered mnestic store.

    Accepts a 2-element list ``[CompiledTermAtom, ObligationsAtom]`` where
    both elements are atom strings (marshalled from Prolog).  Parses the
    compiled term to extract the store name, resolves the adapter via the
    module-level registry, assembles and executes the CozoScript, and
    returns the raw value-lists.

    Args:
        arg: A 2-element list ``[compiled_term_atom, obligations_atom]``.

    Returns:
        A list of value-lists, each in projection column order.

    Raises:
        ValueError: If the compiled term is malformed or the store name is
            not registered.
    """
    if not isinstance(arg, list) or len(arg) != 2:
        raise ValueError(
            f"mnestic_query expects a 2-element list [CompiledAtom, ObligationsAtom], "
            f"got {arg!r}"
        )
    compiled_atom, obligations_atom = arg

    # Parse the compiled atom enough to read the store(Name) field.
    compiled = parse_term(compiled_atom)
    if not isinstance(compiled, Compound) or compiled.functor != "compiled_query":
        raise ValueError(
            f"Expected compiled_query/4 term, got "
            f"{compiled.functor if isinstance(compiled, Compound) else type(compiled).__name__}"
        )
    if len(compiled.args) != 4:
        raise ValueError(
            f"Expected compiled_query/4 with 4 arguments, got {len(compiled.args)}"
        )
    store_term = compiled.args[0]
    store_name = MnesticAdapter._extract_store_name(store_term)

    # Resolve the adapter via the registry.
    try:
        adapter = lookup(store_name)
    except KeyError:
        raise ValueError(
            f"mnestic_query: store '{store_name}' is not registered. "
            "Ensure the store is configured and loaded before running queries."
        ) from None

    # Delegate to compile_and_run and return raw value-lists.
    return adapter.compile_and_run(compiled_atom, obligations_atom)
