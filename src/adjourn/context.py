"""Context stack for adjourn resolution sessions.

The :class:`ContextStack` holds the background (pinned) frames and the
pushed context frames that make up the round prompt for an LLM-driven
resolution session.  It is a plain Python class with no fastmcp or Prolog
dependency, so it can be used (and tested) standalone.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path


class ContextStackEmptyError(Exception):
    """Raised when popping from a context stack with no pushed frames."""


class ContextStack:
    """A stack of plain-string context frames for a resolution session.

    Pinned frames are set at construction and are never removed; pushed
    frames are appended by :meth:`push` and removed last-in-first-out by
    :meth:`pop`.  The stack can be persisted to and restored from a JSON
    file with :meth:`save` and :meth:`load`.

    Attributes:
        pinned: Background frames, oldest first, never removed.
        pushed: Pushed frames, oldest first; ``pop`` removes the last one.
    """

    def __init__(
        self,
        pinned: Sequence[str] = (),
        pushed: Sequence[str] = (),
    ) -> None:
        """Initialise a context stack with the given frames.

        Args:
            pinned: Background frames to keep for the whole session.
            pushed: Pushed frames to start with, oldest first.
        """
        self._pinned = list(pinned)
        self._pushed = list(pushed)

    @property
    def pinned(self) -> list[str]:
        """Return the pinned (background) frames, oldest first."""
        return self._pinned

    @property
    def pushed(self) -> list[str]:
        """Return the pushed frames, oldest first."""
        return self._pushed

    def push(self, text: str) -> None:
        """Append a pushed frame to the top of the stack.

        Args:
            text: The frame text to push.
        """
        self._pushed.append(text)

    def pop(self) -> str:
        """Remove and return the most recently pushed frame.

        Returns:
            The most recently pushed frame.

        Raises:
            ContextStackEmptyError: If there are no pushed frames.  Pinned
                frames are never removed and do not satisfy a pop.
        """
        if not self._pushed:
            raise ContextStackEmptyError
        return self._pushed.pop()

    def save(self, path: str | os.PathLike[str]) -> None:
        """Write the stack to *path* as UTF-8 JSON.

        Creates the parent directory if it does not exist.  The file is
        written in the versioned format ``{"version": 1, "pinned": [...],
        "pushed": [...]}``.

        Args:
            path: Destination file path.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "pinned": self._pinned,
                    "pushed": self._pushed,
                }
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | os.PathLike[str]) -> ContextStack:
        """Restore a context stack from a JSON file written by :meth:`save`.

        Args:
            path: Source file path.

        Returns:
            A new :class:`ContextStack` with the saved pinned and pushed
            frames in their saved order.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the saved ``version`` is not ``1``.
        """
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("version") != 1:
            raise ValueError(f"unsupported context stack version: {data.get('version')!r}")
        return cls(
            pinned=data.get("pinned", []),
            pushed=data.get("pushed", []),
        )

    def render(self, state: dict) -> str:
        """Render the whole round prompt for the given session *state*.

        Sections appear in this order: ``## Background`` with the pinned
        frames, ``## Your context stack`` with the pushed frames oldest
        first, and ``## Session state`` with the JSON-serialised *state*.
        A section is omitted entirely when it has no content, except the
        session state section which is always present.  A blank line
        separates each heading from its content, each frame from the next,
        and each section from the next.

        Args:
            state: Session state dict to serialise into the prompt.

        Returns:
            The rendered round prompt.
        """
        lines: list[str] = []
        if self._pinned:
            lines.append("## Background")
            lines.append("")
            for frame in self._pinned:
                lines.append(frame)
                lines.append("")
        if self._pushed:
            lines.append("## Your context stack (oldest first; pop_context removes the last entry)")
            lines.append("")
            for frame in self._pushed:
                lines.append(frame)
                lines.append("")
        lines.append("## Session state")
        lines.append("")
        lines.append(json.dumps(state, indent=2))
        return "\n".join(lines)
