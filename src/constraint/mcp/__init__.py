"""MCP server for the constraint resolution system.

Exposes two tools — ``constraint_init`` and ``constraint_resume`` — that let
an external client drive a resolution as a coroutine by shelling out to the
CLI per call against disk-backed sessions.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

from fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------

MCP_HOST = os.environ.get("CONSTRAINT_MCP_HOST", "localhost")
MCP_PORT = int(os.environ.get("CONSTRAINT_MCP_PORT", "8080"))
_SESSIONS_DIR = Path(
    os.environ.get("CONSTRAINT_MCP_SESSIONS_DIR", "./.constraint/mcp-sessions")
)
_TIMEOUT = int(os.environ.get("CONSTRAINT_MCP_TIMEOUT", "60"))
_LOG_LEVEL = os.environ.get("CONSTRAINT_MCP_LOG_LEVEL", "WARNING")

# ---------------------------------------------------------------------------
# FastMCP instance
# ---------------------------------------------------------------------------

mcp = FastMCP("constraint-mcp")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sessions_dir() -> Path:
    """Return the sessions directory, creating it if missing."""
    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    return _SESSIONS_DIR


def _session_path(session_id: str) -> Path:
    """Map a session id to its state-file path."""
    return _sessions_dir() / f"{session_id}.json"


def _allocate_session_id() -> str:
    """Allocate a fresh session id (UUID hex)."""
    return uuid.uuid4().hex


def _run_cli(args: list[str]) -> dict:
    """Run the constraint CLI as a subprocess and return the parsed JSON projection.

    Args:
        args: CLI arguments (excluding the program name).

    Returns:
        The parsed JSON projection dict.

    Raises:
        RuntimeError: If the CLI exits with a non-zero status.
    """
    cmd = [sys.executable, "-m", "constraint.cli"] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"CLI subprocess timed out after {_TIMEOUT}s: {' '.join(cmd)}"
        ) from exc

    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(
            f"CLI command failed (exit {result.returncode}): {' '.join(cmd)}\n"
            f"stderr: {stderr}"
        )

    return json.loads(result.stdout)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def constraint_init(goal: str) -> dict:
    """Initialise a new resolution session.

    Allocates a new disk-backed session, runs ``constraint init`` to produce
    the initial state, and returns the session id together with the initial
    projection.

    The returned dict has keys ``session``, ``status``, ``label``,
    ``ruleset_hash``, and ``resume_hash``.

    Coroutine loop:
        1. Call ``constraint_init`` once to create a session.
        2. Call ``constraint_resume`` repeatedly with the returned session id.
        3. ``status`` progresses through ``running`` → ``suspended`` /
           ``solution`` and terminates at ``done``.
        4. ``solution`` is a resumable checkpoint (resuming backtracks for
           further solutions); only ``done`` is terminal.
    """
    session_id = _allocate_session_id()
    state_path = _session_path(session_id)
    projection = _run_cli(
        ["init", goal, str(state_path), "--format", "json"]
    )
    return {"session": session_id, **projection}


@mcp.tool()
def constraint_resume(session: str) -> dict:
    """Advance a resolution session by one step.

    Reads the state file for the given *session* id, runs ``constraint resume``
    in place, and returns the updated projection.

    The returned dict has keys ``session``, ``status``, ``label``,
    ``ruleset_hash``, and ``resume_hash``.

    Args:
        session: The session id returned by ``constraint_init``.

    Returns:
        The updated projection with the session id.

    Raises:
        RuntimeError: If the session state file does not exist.
    """
    state_path = _session_path(session)
    if not state_path.exists():
        raise RuntimeError(
            f"Session '{session}' not found (state file {state_path} does not exist). "
            "Did you call constraint_init first?"
        )
    projection = _run_cli(
        ["resume", str(state_path), str(state_path), "--format", "json"]
    )
    return {"session": session, **projection}
