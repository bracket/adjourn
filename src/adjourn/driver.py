"""LLM driver for adjourn resolution sessions.

The :class:`Driver` runs one adjourn resolution session to completion by
calling an LLM whenever the session suspends.  It owns the session id and
the context stack, and it alone resumes the session: the LLM is offered
local tools to add rules and to manage its own context, but it never sees
session ids or hashes and it cannot resume the session itself.

All resolution still runs through :class:`~adjourn.tools.Workspace`, which
shells out to the adjourn CLI, so Prolog (via janus) never loads in the
driver's process.  The optional ``haft-mcp-host`` dependency is imported
lazily, so importing this module does not require the ``mcp`` extra.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from adjourn.context import ContextStack
from adjourn.prompts import read_prompt, render_usage
from adjourn.state import state_projection
from adjourn.tools import Workspace

_HAFT_IMPORT_ERROR = (
    "The adjourn LLM driver requires the optional 'haft-mcp-host' package. "
    "Install it with `pip install 'adjourn[mcp]'`."
)


def _load_haft() -> tuple[type[Any], type[BaseException]]:
    """Import and return haft's chat session and iteration-limit error.

    The import is performed here rather than at module scope so that
    importing :mod:`adjourn.driver` works without the optional
    ``haft-mcp-host`` dependency installed.

    Returns:
        A ``(ChatSession, MaxIterationsExceededError)`` pair.

    Raises:
        ImportError: If ``haft-mcp-host`` is not installed, chained from the
            original import failure.
    """
    try:
        from haft.mcp_host import ChatSession, MaxIterationsExceededError
    except ImportError as exc:
        raise ImportError(_HAFT_IMPORT_ERROR) from exc
    return ChatSession, MaxIterationsExceededError


class DriverError(Exception):
    """Base class for driver failures.

    A driver error carries the session id and the full state dict read from
    the state file at the time the error was raised.  It never carries a
    transcript.

    Attributes:
        session: The id of the session being driven.
        state: The full session state dict at the time of the error.
    """

    def __init__(self, session: str, state: dict[str, Any], message: str = "") -> None:
        """Initialise the error with the session id and state.

        Args:
            session: The id of the session being driven.
            state: The full session state dict at the time of the error.
            message: Optional human-readable message.
        """
        self.session = session
        self.state = state
        super().__init__(message or f"driver error in session {session}")


class DriverRoundLimitError(DriverError):
    """Raised when a drive exceeds its configured number of LLM rounds."""

    def __init__(self, session: str, state: dict[str, Any]) -> None:
        """Initialise the error with the session id and state."""
        super().__init__(
            session,
            state,
            "the maximum number of LLM rounds was reached",
        )


class DriverIterationLimitError(DriverError):
    """Raised when an LLM round exceeds haft's tool-call iteration limit."""

    def __init__(self, session: str, state: dict[str, Any]) -> None:
        """Initialise the error with the session id and state."""
        super().__init__(
            session,
            state,
            "the LLM exceeded the maximum tool-call iterations",
        )


@dataclass
class DriveResult:
    """The outcome of a completed :meth:`Driver.drive` run.

    Attributes:
        status: The final session status (``solution`` or ``done``).
        solutions: The ``bindings`` dict of each solution state, in order.
        state: The final full session state dict read from the state file.
    """

    status: str
    solutions: list[dict[str, Any]]
    state: dict[str, Any]


class Driver:
    """Drive one adjourn resolution session with an LLM in the loop.

    The driver allocates a session, resumes it once without the LLM, and
    then runs one LLM round per suspension.  Each round is a fresh
    :class:`haft.mcp_host.ChatSession` prompted with the rendered context
    stack and state; the context stack is the only memory carried between
    rounds.  The driver alone resumes the session.

    Attributes:
        workspace: The :class:`~adjourn.tools.Workspace` used for all
            resolution operations.
        model: The model name passed to haft.
        base_url: The Responses-compatible base URL passed to haft.
        system_prompt: The driver's system prompt.
        max_rounds: Maximum number of LLM rounds per drive.
        max_iterations: Maximum tool-call iterations per LLM round.
        request_headers: Optional HTTP headers for the model endpoint.
    """

    def __init__(
        self,
        workspace: Workspace,
        model: str,
        base_url: str,
        *,
        system_prompt: str | None = None,
        max_rounds: int = 30,
        max_iterations: int = 10,
        request_headers: Mapping[str, str] | None = None,
        _responses_client: Callable[..., dict[str, Any]] | None = None,
    ) -> None:
        """Initialise the driver.

        Args:
            workspace: The workspace used for all resolution operations.
            model: The model name passed to haft.
            base_url: The Responses-compatible base URL passed to haft.
            system_prompt: Optional caller text appended to the driver's
                default system prompt after a blank line.
            max_rounds: Maximum number of LLM rounds per drive.
            max_iterations: Maximum tool-call iterations per LLM round.
            request_headers: Optional HTTP headers for the model endpoint.
            _responses_client: Test hook replacing haft's HTTP model call.

        Raises:
            ImportError: If ``haft-mcp-host`` is not installed.
        """
        _load_haft()
        self.workspace = workspace
        self.model = model
        self.base_url = base_url
        default_prompt = render_usage(read_prompt("driver_preamble.md"))
        if system_prompt is not None:
            self.system_prompt = f"{default_prompt}\n\n{system_prompt}"
        else:
            self.system_prompt = default_prompt
        self.max_rounds = max_rounds
        self.max_iterations = max_iterations
        self.request_headers = request_headers
        self._responses_client = _responses_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def drive(
        self,
        goal: str,
        initial_context: Sequence[str] = (),
        all_solutions: bool = False,
    ) -> DriveResult:
        """Drive a fresh session for *goal* to a solution or completion.

        The session is initialised and resumed once without the LLM, then
        each suspension runs one LLM round.  With *all_solutions* false the
        first solution finishes the drive; with it true the driver resumes
        past each solution (without the LLM) and collects bindings until the
        session is done.

        Args:
            goal: The Prolog goal string to resolve.
            initial_context: Pinned background frames for the context stack.
            all_solutions: Whether to collect every solution instead of
                stopping at the first.

        Returns:
            The final :class:`DriveResult`.

        Raises:
            ImportError: If ``haft-mcp-host`` is not installed.
            DriverRoundLimitError: If the drive exceeds ``max_rounds``.
            DriverIterationLimitError: If a round exceeds ``max_iterations``.
        """
        _load_haft()
        session = self.workspace.init(goal)["session"]
        self.workspace.resume(session)
        stack = ContextStack(pinned=initial_context)
        context_path = self.workspace.context_path(session)
        solutions: list[dict[str, Any]] = []
        rounds = 0
        while True:
            state = self._read_state(session)
            status = state["status"]
            if status == "solution":
                solutions.append(state["bindings"])
                if not all_solutions:
                    return DriveResult(status, solutions, state)
                self.workspace.resume(session)
                continue
            if status == "done":
                return DriveResult(status, solutions, state)
            if rounds >= self.max_rounds:
                stack.save(context_path)
                raise DriverRoundLimitError(session, self._read_state(session))
            rounds += 1
            self._run_round(session, stack, context_path, state)
            self.workspace.resume(session)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _read_state(self, session: str) -> dict[str, Any]:
        """Read and return the full state dict for *session*."""
        path = self.workspace.state_path(session)
        return json.loads(path.read_text(encoding="utf-8"))

    def _tool_state(self, session: str) -> dict[str, Any]:
        """Build the LLM-facing result dict from the session state file.

        The result always carries ``status``, ``label``, and ``bindings``.
        Unavailable fields are ``None``.  It never carries the session id or
        any hash keys.
        """
        state = self._read_state(session)
        return state_projection(state, ("status", "label", "bindings"))

    def _create_chat_session(self, chat_session_cls: type[Any]) -> Any:
        """Create a fresh haft chat session for one round."""
        kwargs: dict[str, Any] = {}
        if self._responses_client is not None:
            kwargs["_responses_client"] = self._responses_client
        return chat_session_cls(
            self.model,
            self.base_url,
            system_prompt=self.system_prompt,
            max_iterations=self.max_iterations,
            request_headers=self.request_headers,
            **kwargs,
        )

    def _run_round(
        self,
        session: str,
        stack: ContextStack,
        context_path: Path,
        state: dict[str, Any],
    ) -> None:
        """Run one LLM round against the current suspension.

        The round is a fresh chat session prompted with the rendered context
        stack and state.  The LLM may add rules and edit the context stack;
        it cannot resume the session.  The stack is saved after the round and
        before raising any driver error.

        Args:
            session: The session id being driven.
            stack: The context stack for the session.
            context_path: Sidecar path the stack is saved to.
            state: The full state dict to render into the round prompt.

        Raises:
            DriverIterationLimitError: If haft's iteration limit is hit.
        """
        chat_session_cls, max_iterations_error = _load_haft()

        def add_rules(args: dict[str, Any]) -> Any:
            """Add Prolog clauses to the program.

            Use this when the program suspended because no rule covers a
            goal.  The clauses are added to the program and the current goal
            restarts from the top when the driver resumes.  This does not
            resume the session itself.

            Args:
                args: Tool arguments; ``rules`` holds the Prolog clause text.
            """
            try:
                self.workspace.add_rules(session, args["rules"])
                return self._tool_state(session)
            except Exception as exc:  # noqa: BLE001 - returned to the LLM as an error result
                return {"error": str(exc)}

        def push_context(args: dict[str, Any]) -> Any:
            """Save a note for yourself to read in later rounds.

            Rounds have no shared memory, so push anything you will need
            again.  The note appears in the context stack of later prompts.

            Args:
                args: Tool arguments; ``text`` holds the note to save.
            """
            try:
                stack.push(args["text"])
                return "Context pushed."
            except Exception as exc:  # noqa: BLE001 - returned to the LLM as an error result
                return {"error": str(exc)}

        def pop_context(args: dict[str, Any]) -> Any:
            """Remove and return the most recent note you pushed.

            Background frames cannot be removed; popping when only
            background frames remain returns an error result.
            """
            try:
                return stack.pop()
            except Exception as exc:  # noqa: BLE001 - returned to the LLM as an error result
                return {"error": str(exc)}

        chat = self._create_chat_session(chat_session_cls)
        try:
            with chat:
                chat.add_local_tool(
                    "add_rules",
                    add_rules,
                    {
                        "type": "object",
                        "properties": {"rules": {"type": "string"}},
                        "required": ["rules"],
                    },
                )
                chat.add_local_tool(
                    "push_context",
                    push_context,
                    {
                        "type": "object",
                        "properties": {"text": {"type": "string"}},
                        "required": ["text"],
                    },
                )
                chat.add_local_tool(
                    "pop_context",
                    pop_context,
                    {"type": "object", "properties": {}},
                )
                chat.send(stack.render(state))
        except max_iterations_error as exc:
            stack.save(context_path)
            raise DriverIterationLimitError(session, self._read_state(session)) from exc
        stack.save(context_path)
