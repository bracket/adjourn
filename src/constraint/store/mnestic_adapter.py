"""Mnestic adapter stub for the constraint ruleset store.

This module provides the schema descriptor dataclasses and MnesticAdapter
class that MnesticRuleSetStore builds against. The real implementation
(backed by mnestic.CozoDbPy) is filled in by a later obligation; this stub
is sufficient for the store's tests to run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ColumnDescriptor:
    """Descriptor for a single column in a discovered relation."""

    name: str
    type: str
    is_key: bool


@dataclass(frozen=True)
class RelationDescriptor:
    """Descriptor for a discovered relation (table).

    ``columns`` is an ordered list: key column(s) first, then value columns
    in declaration order. ``arity`` always equals ``len(columns)``.
    """

    name: str
    columns: list[ColumnDescriptor]
    arity: int = field(default=0)

    def __post_init__(self) -> None:
        # A frozen dataclass requires object.__setattr__ for computed fields.
        # Always derive arity from the actual column list so the invariant
        # ``arity == len(columns)`` holds regardless of what was passed in.
        object.__setattr__(self, "arity", len(self.columns))


class MnesticAdapter:
    """Adapter to a mnestic (CozoDB) database.

    The real implementation opens the database at *path* and provides
    schema discovery and script execution. This stub provides enough
    structure for MnesticRuleSetStore to import and test against: pass a
    canned ``schema`` (a list of :class:`RelationDescriptor`) at
    construction, or assign ``adapter.schema`` afterwards, and
    :meth:`discover_schema` will return it.
    """

    def __init__(self, path: str, schema: list[RelationDescriptor] | None = None) -> None:
        self.path = path
        self.schema = schema

    def run_script(
        self, script: str, params: dict[str, Any] | None = None, immutable: bool = True
    ) -> list[dict[str, Any]]:
        """Execute a CozoScript against the database.

        Args:
            script: The CozoScript to execute.
            params: Optional parameters for the script.
            immutable: Whether the script is read-only.

        Returns:
            A list of result rows as dictionaries.
        """
        raise NotImplementedError(
            "MnesticAdapter.run_script is not yet implemented"
        )

    def discover_schema(self) -> list[RelationDescriptor]:
        """Discover the schema of the database.

        Returns:
            A list of RelationDescriptor objects, one per stored relation.

        Raises:
            NotImplementedError: When no canned schema has been supplied.
        """
        if self.schema is None:
            raise NotImplementedError(
                "MnesticAdapter.discover_schema is not yet implemented"
            )
        return list(self.schema)
