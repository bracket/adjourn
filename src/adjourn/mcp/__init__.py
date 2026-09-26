"""MCP server for the adjourn resolution system.

Exposes three tools — ``adjourn_init``, ``adjourn_resume``, and
``adjourn_add_rules`` — that let an external client drive a resolution as a
coroutine by shelling out to the CLI per call against disk-backed sessions.
The tools are thin wrappers that delegate to a module-level
:class:`~adjourn.tools.Workspace` instance.
"""

from __future__ import annotations

import os

from fastmcp import FastMCP

from adjourn.tools import Workspace

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------

MCP_HOST = os.environ.get("ADJOURN_MCP_HOST", "localhost")
MCP_PORT = int(os.environ.get("ADJOURN_MCP_PORT", "8080"))
_LOG_LEVEL = os.environ.get("ADJOURN_MCP_LOG_LEVEL", "WARNING")

# ---------------------------------------------------------------------------
# FastMCP instance
# ---------------------------------------------------------------------------

mcp = FastMCP("adjourn-mcp")

# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------

workspace: Workspace = Workspace.from_env()


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def adjourn_init(goal: str) -> dict:
    """Initialise a new resolution session.

    Delegates to :meth:`adjourn.tools.Workspace.init`, which allocates a new
    disk-backed session, runs ``adjourn init`` to produce the initial state,
    and returns the session id together with the initial projection.

    The returned dict has keys ``session``, ``status``, ``label``,
    ``ruleset_hash``, and ``resume_hash``.

    Coroutine loop:
        1. Call ``adjourn_init`` once to create a session.
        2. Call ``adjourn_resume`` repeatedly with the returned session id.
        3. ``status`` progresses through ``running`` → ``suspended`` /
           ``solution`` and terminates at ``done``.
        4. ``solution`` is a resumable checkpoint (resuming backtracks for
           further solutions); only ``done`` is terminal.

    Args:
        goal: The Prolog goal string to resolve.

    Returns:
        The initial projection with the session id.
    """
    return workspace.init(goal)


@mcp.tool()
def adjourn_resume(session: str) -> dict:
    """Resume a resolution session until the next yield, solution, or done.

    Delegates to :meth:`adjourn.tools.Workspace.resume`, which reads the
    state file for the given *session* id, runs ``adjourn resume`` in place,
    and returns the updated projection.  The CLI continues through
    checkpoints, so a single call runs until the next yield, solution, or
    done rather than stopping after one step.

    The returned dict has keys ``session``, ``status``, ``label``,
    ``ruleset_hash``, and ``resume_hash``.

    Args:
        session: The session id returned by ``adjourn_init``.

    Returns:
        The updated projection with the session id.

    Raises:
        RuntimeError: If the session state file does not exist.
    """
    return workspace.resume(session)


@mcp.tool()
def adjourn_add_rules(session: str, rules: str) -> dict:
    """Add a ruleset file, repoint resume, and resume the session.

    Delegates to :meth:`adjourn.tools.Workspace.add_rules`, which writes
    *rules* verbatim to a newly allocated ``rules_NNN.pl`` file in the server
    directory, registers that relative filename in the configured project
    config, repoints the session's ``resume_hash`` to ``@top``, resumes the
    session in place, and returns the resulting projection.  This sequence is
    not atomic: if a later CLI step fails, the numbered rules file remains on
    disk, and any earlier config registration also remains in place while the
    error is propagated.

    Args:
        session: The session id returned by ``adjourn_init``.
        rules: Opaque Prolog rule text to write verbatim.

    Returns:
        The updated projection with the session id.

    Raises:
        RuntimeError: If the session state file does not exist.
    """
    return workspace.add_rules(session, rules)
