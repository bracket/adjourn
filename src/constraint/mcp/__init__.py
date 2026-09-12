"""MCP server for the constraint resolution system.

Exposes three tools — ``constraint_init``, ``constraint_resume``, and
``constraint_add_rules`` — that let an external client drive a resolution as a
coroutine by shelling out to the CLI per call against disk-backed sessions.
"""

from __future__ import annotations

import json
import os
import re
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
_CONFIG_PATH = Path(os.environ.get("CONSTRAINT_CONFIG", ".constraint/config.yaml"))
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


def _config_path() -> Path:
    """Return the configured project config path."""
    return _CONFIG_PATH


def _server_dir() -> Path:
    """Return the server directory that contains ``.constraint/``."""
    return _config_path().parent.parent


def _allocate_rules_filename(server_dir: Path) -> str:
    """Allocate the next ``rules_NNN.pl`` filename in *server_dir*."""
    next_index = 1
    pattern = re.compile(r"^rules_(\d+)\.pl$")
    for candidate in server_dir.iterdir():
        match = pattern.match(candidate.name)
        if match is None:
            continue
        next_index = max(next_index, int(match.group(1)) + 1)
    return f"rules_{next_index:03d}.pl"


def _allocate_session_id() -> str:
    """Allocate a fresh session id (UUID hex)."""
    return uuid.uuid4().hex


def _run_cli(args: list[str], cwd: Path | None = None) -> dict:
    """Run the constraint CLI as a subprocess and return the parsed JSON projection.

    Args:
        args: CLI arguments (excluding the program name).
        cwd: Optional working directory for the subprocess.

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
            cwd=cwd,
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


def _require_session_state(session: str) -> Path:
    """Return the session state file path or raise if it does not exist."""
    state_path = _session_path(session)
    if not state_path.exists():
        raise RuntimeError(
            f"Session '{session}' not found (state file {state_path} does not exist). "
            "Did you call constraint_init first?"
        )
    return state_path


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
    state_path = _require_session_state(session)
    projection = _run_cli(
        ["resume", str(state_path), str(state_path), "--format", "json"]
    )
    return {"session": session, **projection}


@mcp.tool()
def constraint_add_rules(session: str, rules: str) -> dict:
    """Add a ruleset file, repoint resume, and advance the session once.

    Writes *rules* verbatim to a newly allocated ``rules_NNN.pl`` file in the
    server directory, registers that relative filename in the configured
    project config, repoints the session's ``resume_hash`` to ``@top``, resumes
    the session in place, and returns the resulting projection.

    Args:
        session: The session id returned by ``constraint_init``.
        rules: Opaque Prolog rule text to write verbatim.

    Returns:
        The updated projection with the session id.

    Raises:
        RuntimeError: If the session state file does not exist.
    """
    state_path = _require_session_state(session).resolve()
    config_path = _config_path()
    server_dir = _server_dir()
    rules_filename = _allocate_rules_filename(server_dir)
    rules_path = server_dir / rules_filename
    rules_path.write_text(rules, encoding="utf-8")

    _run_cli(
        [
            "rules",
            "add",
            rules_filename,
            "--config",
            str(config_path),
            "--format",
            "json",
        ],
        cwd=server_dir,
    )
    _run_cli(
        [
            "set-resume",
            "@top",
            str(state_path),
            "--config",
            str(config_path),
            "--format",
            "json",
        ],
        cwd=server_dir,
    )
    projection = _run_cli(
        ["resume", str(state_path), str(state_path), "--format", "json"],
        cwd=server_dir,
    )
    return {"session": session, **projection}
