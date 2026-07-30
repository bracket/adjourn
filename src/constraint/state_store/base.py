"""Abstract base class for state storage seams."""

from __future__ import annotations

from abc import ABC, abstractmethod


class StateStore(ABC):
    """Abstract base class for storing and loading meta-interpreter state."""

    @abstractmethod
    def store_state(self, name: str, state: dict) -> None:
        """Persist *state* under the given *name*.

        Args:
            name: Logical name for the state (not a filesystem path).
            state: JSON-serializable dict representing the meta-interpreter state.
        """

    @abstractmethod
    def load_state(self, name: str) -> dict:
        """Load and return the state previously stored under *name*.

        Args:
            name: Logical name for the state (not a filesystem path).

        Returns:
            The deserialized state dict.
        """
