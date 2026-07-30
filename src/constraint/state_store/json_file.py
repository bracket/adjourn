"""JSON-file-backed implementation of the state storage seam."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from constraint.state_store.base import StateStore


class JsonFileStateStore(StateStore):
    """Concrete state store that persists state as JSON files.

    States are written to ``<root>/states/state_<name>.json``.
    The root directory defaults to ``.constraint`` but can be overridden
    (e.g. with a ``tmp_path`` in tests).
    """

    def __init__(self, root: str | Path = ".constraint") -> None:
        self._root = Path(root)

    def store_state(self, name: str, state: dict) -> None:
        """Write *state* as JSON to ``<root>/states/state_<name>.json``.

        Creates the ``<root>/states/`` directory if it does not exist.
        Overwrites any existing file with the same name (last-write-wins).
        """
        states_dir = self._root / "states"
        states_dir.mkdir(parents=True, exist_ok=True)
        path = states_dir / f"state_{name}.json"
        path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")

    def load_state(self, name: str) -> dict:
        """Read and return the JSON dict from ``<root>/states/state_<name>.json``.

        Raises ``FileNotFoundError`` if no state with that name exists.
        """
        path = self._root / "states" / f"state_{name}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def store_init_state(self, state: dict) -> None:
        """Write *state* as JSON to ``<root>/state_init.json``.

        Creates the ``<root>/`` directory if it does not exist.
        Overwrites any existing file (last-write-wins).
        """
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._root / "state_init.json"
        path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
