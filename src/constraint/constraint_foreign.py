"""Foreign Python function registry for the constraint meta-interpreter.

Provides a decorator-based registry of named Python callables that can be
invoked synchronously from Prolog via janus
``py_call(constraint_foreign:dispatch(Fn, In), Out)``.

Usage (Python side)::

    from constraint.constraint_foreign import register

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
    ``py_call(constraint_foreign:dispatch(Fn, In), Out)``.

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

import constraint.subprocess.subprocess as _subprocess_module  # noqa: F401

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
