"""subprocess foreign callout for the constraint meta-interpreter.

Registers a ``subprocess`` callout in the ``constraint_foreign`` registry so the
Prolog meta-interpreter can invoke it via::

    foreign(subprocess, [Cwd, Arg0, Arg1, ...], ExitCode)

where ``Cwd`` is the working directory and ``Arg0, Arg1, ...`` form the argv
of the command to run.  The exit code is returned as a raw integer; a nonzero
exit is a valid, expected result and is returned, not raised.
"""

from __future__ import annotations

import subprocess
import sys
import traceback
from collections.abc import Iterable
from typing import Any

from constraint.constraint_foreign import register


@register("subprocess")
def _subprocess(arg: Any) -> int:
    """Run an argv-based command host-side and return its raw exit code.

    Invoked from Prolog via::

        foreign(subprocess, [Cwd, Arg0, Arg1, ...], ExitCode)

    The input is a single Prolog list of atoms, marshalled by janus to a Python
    ``list[str]``.  The list HEAD is the working directory; the remaining
    elements are the argv.  ``ExitCode`` is unified with the raw process exit
    status as an integer.

    Args:
        arg: A sequence of strings of the form ``[cwd, arg0, arg1, ...]``,
             marshalled by janus from a Prolog list of atoms.

    Returns:
        The raw integer exit code of the subprocess.

    Raises:
        ValueError: If *arg* is not an iterable, is empty, or contains only a
            cwd with no argv element.
        Exception: Re-raised after writing captured stdout, stderr, and a
            traceback to ``sys.stderr``.
    """
    # Validate that arg is iterable.
    if not isinstance(arg, Iterable):
        raise ValueError(
            f"subprocess: expected an iterable sequence, got {arg!r}"
        )

    # Convert to list for indexing and length checks.
    try:
        items = list(arg)
    except TypeError:
        raise ValueError(
            f"subprocess: expected an iterable sequence, got {arg!r}"
        )

    # Must have at least 2 elements: cwd + at least one argv element.
    if len(items) < 2:
        raise ValueError(
            f"subprocess: expected at least 2 elements [cwd, arg0, ...],"
            f" got {len(items)}"
        )

    cwd = items[0]
    argv = items[1:]

    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
        )
    except Exception:
        # Write captured output and traceback to stderr, then re-raise.
        print("subprocess callout failed", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        raise

    return result.returncode
