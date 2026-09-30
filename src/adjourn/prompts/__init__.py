"""Shared LLM-facing usage text for adjourn.

The conceptual "how to drive adjourn" text lives in ``usage.md`` and names no
tools.  Each caller (the MCP server, the LLM driver) supplies its own preamble
describing its tool surface, and both go through :func:`render_usage`.
"""

from __future__ import annotations

from functools import cache
from importlib.resources import files


@cache
def read_prompt(name: str) -> str:
    """Return the text of the prompt file *name* shipped in this package."""
    return files(__package__).joinpath(name).read_text(encoding="utf-8")


def render_usage(preamble: str = "") -> str:
    """Return the shared usage text, optionally prefixed by *preamble*.

    With an empty preamble, returns the core text alone.  Otherwise returns
    the preamble, a blank line, then the core.
    """
    core = read_prompt("usage.md")
    preamble = preamble.strip()
    if not preamble:
        return core
    return f"{preamble}\n\n{core}"
