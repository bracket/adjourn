"""Workspace for disk-backed adjourn resolution sessions.

The :class:`Workspace` encapsulates the session machinery behind the MCP
server tools: it allocates session ids, shells out to the adjourn CLI per
call against disk-backed state files, and manages numbered ruleset files in
the server directory.  It is a plain Python class with no fastmcp
dependency, so it can be used (and tested) without the optional MCP extra
installed.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path


class Workspace:
    """Drive adjourn resolution sessions against a project config.

    A workspace is bound to one project config file.  Sessions are stored as
    JSON state files under a sessions directory, and every CLI interaction is
    performed by shelling out to ``python -m adjourn.cli`` so that Prolog
    (via janus) never loads in this process.  Every CLI call passes the
    workspace's ``--config`` and runs from :attr:`server_dir`, so behaviour
    does not depend on the calling process's cwd or ``ADJOURN_CONFIG``.

    Attributes:
        config_path: Resolved path to the project config file.
        sessions_dir: Directory holding per-session state files.  Created
            lazily on first use; may be reassigned after construction.
        timeout: Subprocess timeout in seconds for each CLI call.
        create_config: Whether ``init`` should create a missing config file
            (with an empty ``stores`` list) instead of failing.
    """

    def __init__(
        self,
        config_path: str | os.PathLike[str],
        sessions_dir: str | os.PathLike[str] | None = None,
        timeout: int = 60,
        create_config: bool = False,
    ) -> None:
        """Initialise a workspace for the given project config.

        The constructor does not touch the filesystem: the sessions
        directory is only created on first use, and a missing config file
        is only created (when *create_config* is true) by a later
        :meth:`init` call.

        Args:
            config_path: Path to the project config file.  Stored resolved.
            sessions_dir: Directory for session state files.  When omitted,
                defaults to ``config_path.parent / "mcp-sessions"``.  The
                value is stored as given (not resolved).
            timeout: Subprocess timeout in seconds for each CLI call.
            create_config: When true, :meth:`init` creates a missing config
                before invoking the CLI. On an empty program the initial state
                records the reserved ``@empty`` ruleset hash for both
                ``ruleset_hash`` and ``resume_hash``; call :meth:`add_rules`
                before :meth:`resume` to recover.
        """
        self.config_path = Path(config_path).resolve()
        if sessions_dir is None:
            self.sessions_dir = self.config_path.parent / "mcp-sessions"
        else:
            self.sessions_dir = Path(sessions_dir)
        self.timeout = timeout
        self.create_config = create_config

    @property
    def server_dir(self) -> Path:
        """Return the server directory that contains ``.adjourn/``."""
        return self.config_path.parent.parent

    @classmethod
    def from_env(cls, create_config: bool = False) -> Workspace:
        """Build a workspace from environment variables.

        Reads ``ADJOURN_CONFIG`` (default ``.adjourn/config.yaml``),
        ``ADJOURN_MCP_TIMEOUT`` (default ``60``), and
        ``ADJOURN_MCP_SESSIONS_DIR`` (when set; otherwise the
        config-relative default applies).  *create_config* is not read from
        any environment variable; it must be passed explicitly.

        Args:
            create_config: Forwarded to :meth:`__init__`; when true,
                :meth:`init` creates a missing config file (with an empty
                ``stores`` list) instead of failing.

        Returns:
            A new :class:`Workspace` configured from the environment.
        """
        config_path = os.environ.get("ADJOURN_CONFIG", ".adjourn/config.yaml")
        timeout = int(os.environ.get("ADJOURN_MCP_TIMEOUT", "60"))
        sessions_dir = os.environ.get("ADJOURN_MCP_SESSIONS_DIR")
        return cls(
            config_path,
            sessions_dir=sessions_dir,
            timeout=timeout,
            create_config=create_config,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _sessions_dir(self) -> Path:
        """Return the sessions directory, creating it if missing."""
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        return self.sessions_dir

    def _session_path(self, session_id: str) -> Path:
        """Map a session id to its state-file path."""
        return self._sessions_dir() / f"{session_id}.json"

    def context_path(self, session: str) -> Path:
        """Return the default sidecar path for a session's context stack.

        The path is ``sessions_dir / "<session>.context.json"``.  This
        method does not touch the filesystem: it neither creates the
        sessions directory nor the sidecar file.

        Args:
            session: The session id returned by :meth:`init`.

        Returns:
            The sidecar path for the session's context stack.
        """
        return self.sessions_dir / f"{session}.context.json"

    def state_path(self, session: str) -> Path:
        """Return the state-file path for a session.

        The path is ``sessions_dir / "<session>.json"``, the same path as
        :meth:`_session_path`.  This method does not touch the filesystem: it
        neither creates the sessions directory nor the state file.

        Args:
            session: The session id returned by :meth:`init`.

        Returns:
            The state-file path for the session.
        """
        return self._session_path(session)

    def _allocate_session_id(self) -> str:
        """Allocate a fresh session id (UUID hex)."""
        return uuid.uuid4().hex

    def _allocate_rules_filename(self, server_dir: Path) -> str:
        """Allocate the next ``rules_NNN.pl`` filename in *server_dir*."""
        next_index = 1
        pattern = re.compile(r"^rules_(\d+)\.pl$")
        for candidate in server_dir.iterdir():
            match = pattern.match(candidate.name)
            if match is None:
                continue
            next_index = max(next_index, int(match.group(1)) + 1)
        return f"rules_{next_index:03d}.pl"

    def _write_rules_file(self, server_dir: Path, rules: str) -> str:
        """Write *rules* to a uniquely created ``rules_NNN.pl`` file."""
        rules_filename = self._allocate_rules_filename(server_dir)
        next_index = int(rules_filename.removeprefix("rules_").removesuffix(".pl"))
        while True:
            rules_filename = f"rules_{next_index:03d}.pl"
            rules_path = server_dir / rules_filename
            try:
                with rules_path.open("x", encoding="utf-8") as handle:
                    handle.write(rules)
            except FileExistsError:
                next_index += 1
                continue
            return rules_filename

    def _run_cli(self, args: list[str], cwd: Path | None = None) -> dict:
        """Run the adjourn CLI as a subprocess and return the parsed JSON projection.

        Args:
            args: CLI arguments (excluding the program name).
            cwd: Optional working directory for the subprocess.

        Returns:
            The parsed JSON projection dict.

        Raises:
            RuntimeError: If the CLI exits with a non-zero status.
        """
        return json.loads(self._run_cli_command(args, cwd=cwd))

    def _run_cli_command(self, args: list[str], cwd: Path | None = None) -> str:
        """Run the CLI and return stdout without assuming it is JSON."""
        cmd = [sys.executable, "-m", "adjourn.cli"] + args
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                check=False,
                text=True,
                timeout=self.timeout,
                cwd=cwd,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"CLI subprocess timed out after {self.timeout}s: {' '.join(cmd)}"
            ) from exc

        if result.returncode != 0:
            stderr = result.stderr.strip()
            raise RuntimeError(
                f"CLI command failed (exit {result.returncode}): {' '.join(cmd)}\n"
                f"stderr: {stderr}"
            )

        return result.stdout

    def _require_session_state(self, session: str) -> Path:
        """Return the session state file path or raise if it does not exist."""
        state_path = self._session_path(session)
        if not state_path.exists():
            raise RuntimeError(
                f"Session '{session}' not found (state file {state_path} does not exist). "
                "Was the session initialised first?"
            )
        return state_path

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    def init(self, goal: str) -> dict:
        """Initialise a new resolution session.

        Allocates a new disk-backed session, runs ``adjourn init`` to produce
        the initial state, and returns the session id together with the
        initial projection.

        The returned dict includes ``session``, ``status``, ``label``,
        ``original_goal``, ``bindings``, ``ruleset_hash``, and ``resume_hash``.

        When :attr:`create_config` is true, a missing config file is created
        before invoking ``adjourn init``. On an empty program the initial state
        records the reserved ``@empty`` ruleset hash for both
        ``ruleset_hash`` and ``resume_hash``; call :meth:`add_rules` before
        :meth:`resume` to recover.

        Status lifecycle:
            The state file is written only at init and when resolution stops
            (at a suspension, a solution, or done), so resolution in progress
            is never observable.  ``running`` appears only on the freshly
            initialised state.  Each :meth:`resume` then stops at
            ``suspended``, ``solution`` or ``done``.  ``solution`` is a
            resumable checkpoint (resuming backtracks for further
            solutions); only ``done`` is terminal.

        Args:
            goal: The Prolog goal string to resolve.

        Returns:
            The initial projection with the session id.
        """
        session_id = self._allocate_session_id()
        state_path = self._session_path(session_id).resolve()
        init_args = [
            "init",
            goal,
            str(state_path),
            "--config",
            str(self.config_path),
            "--format",
            "json",
        ]
        if self.create_config and not self.config_path.exists():
            try:
                self._run_cli_command(
                    ["config", "init", "--config", str(self.config_path)],
                    cwd=self.server_dir,
                )
            except RuntimeError:
                # A concurrent init may have created the config between the
                # existence check and the CLI call; only fail if it is still
                # missing.
                if not self.config_path.exists():
                    raise
        projection = self._run_cli(init_args, cwd=self.server_dir)
        return {"session": session_id, **projection}

    def resume(self, session: str) -> dict:
        """Advance a resolution session until the next yield, solution, or done.

        Reads the state file for the given *session* id, runs ``adjourn
        resume`` in place, and returns the updated projection.  The CLI
        continues through checkpoints, so a single call runs until the next
        yield, solution, or done rather than stopping after one step.

        The returned dict includes ``session``, ``status``, ``label``,
        ``original_goal``, ``bindings``, ``ruleset_hash``, and ``resume_hash``.

        Args:
            session: The session id returned by :meth:`init`.

        Returns:
            The updated projection with the session id.

        Raises:
            RuntimeError: If the session state file does not exist.
        """
        state_path = self._require_session_state(session).resolve()
        projection = self._run_cli(
            [
                "resume",
                str(state_path),
                str(state_path),
                "--config",
                str(self.config_path),
                "--format",
                "json",
            ],
            cwd=self.server_dir,
        )
        return {"session": session, **projection}

    def add_rules(self, session: str, rules: str) -> dict:
        """Add a ruleset file and repoint resume, without resuming.

        Writes *rules* verbatim to a newly allocated ``rules_NNN.pl`` file in
        the server directory, registers that relative filename in the
        configured project config, repoints the session's ``resume_hash`` to
        ``@top``, and returns the resulting projection.  The session is not
        resumed: callers resume separately.  This sequence is not atomic: if a
        later CLI step fails, the numbered rules file remains on disk, and any
        earlier config registration also remains in place while the error is
        propagated.

        Args:
            session: The session id returned by :meth:`init`.
            rules: Opaque Prolog rule text to write verbatim.

        Returns:
            The updated projection with the session id.

        Raises:
            RuntimeError: If the session state file does not exist.
        """
        state_path = self._require_session_state(session).resolve()
        config_path = self.config_path
        server_dir = self.server_dir
        rules_filename = self._write_rules_file(server_dir, rules)

        self._run_cli(
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
        projection = self._run_cli(
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
        return {"session": session, **projection}
