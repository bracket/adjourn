"""Mnestic (CozoDB) adapter for the constraint ruleset store.

This module provides the schema descriptor dataclasses and MnesticAdapter
that MnesticRuleSetStore builds against. The adapter opens a read-only
rocksdb-backed mnestic database, discovers its schema generically from
CozoDB's ``::relations`` and ``::columns`` system ops, and executes
read-only CozoScript.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mnestic import CozoDbPy


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

    Opens the rocksdb-backed database at *path* and provides read-only
    script execution and generic schema discovery.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self._db = CozoDbPy("rocksdb", path, "")

    def run_script(
        self,
        script: str,
        params: dict[str, Any] | None = None,
        immutable: bool = True,
    ) -> dict[str, Any]:
        """Execute a CozoScript against the database.

        Args:
            script: The CozoScript to execute.
            params: Optional parameters for the script.
            immutable: Whether the script is read-only (default True).

        Returns:
            The raw CozoDB result dict with ``headers``, ``rows``, and
            ``next`` keys.
        """
        if params is None:
            params = {}
        return self._db.run_script(script, params, immutable)

    def discover_schema(self) -> list[RelationDescriptor]:
        """Discover the schema of the database.

        Runs ``::relations`` to list stored relations, then
        ``::columns <relation>`` for each to obtain column metadata.
        Columns are ordered key-first-then-value by their positional index
        so that base-predicate generation is deterministic.

        Returns:
            A list of RelationDescriptor objects, one per stored relation.
        """
        relations_result = self.run_script("::relations")
        relations_headers = relations_result["headers"]
        relations_rows = relations_result["rows"]

        descriptors: list[RelationDescriptor] = []
        for row in relations_rows:
            rel = dict(zip(relations_headers, row, strict=False))
            rel_name: str = rel["name"]

            columns_result = self.run_script(f"::columns {rel_name}")
            col_headers = columns_result["headers"]
            col_rows = columns_result["rows"]

            # Build column descriptors, sorting by (not is_key, index)
            # so key columns come first, then value columns in declaration order.
            raw_columns: list[dict[str, Any]] = [
                dict(zip(col_headers, cr, strict=False)) for cr in col_rows
            ]
            raw_columns.sort(key=lambda c: (not c["is_key"], c["index"]))

            columns = [
                ColumnDescriptor(
                    name=col["column"],
                    type=col["type"],
                    is_key=bool(col["is_key"]),
                )
                for col in raw_columns
            ]

            descriptors.append(RelationDescriptor(name=rel_name, columns=columns))

        return descriptors
