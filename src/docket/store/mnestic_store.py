"""MnesticRuleSetStore — in-memory base-predicate generation from a discovered schema."""

from __future__ import annotations

from pathlib import Path

from constraint.parser.ast import Atom, Clause, Compound, Variable
from constraint.parser.parser import parse_file
from constraint.store.mnestic_adapter import MnesticAdapter, RelationDescriptor, register
from constraint.store.store import (
    RuleSetStore,
    StoreInfo,
    _program_clauses,
    hash_clauses,
)


def _to_camel_case(snake_str: str) -> str:
    """Convert a snake_case string to CamelCase.

    >>> _to_camel_case("parent_id")
    'ParentId'
    >>> _to_camel_case("id")
    'Id'
    >>> _to_camel_case("is_named")
    'IsNamed'
    >>> _to_camel_case("start_byte")
    'StartByte'
    """
    return "".join(word.capitalize() for word in snake_str.split("_"))


def _generate_clause_for_relation(descriptor: RelationDescriptor) -> Clause:
    """Generate a single base-predicate fact clause from a relation descriptor.

    The clause has the form::

        relation_name(Var1, Var2, ...).

    where each variable is named after the column in CamelCase, preserving
    column order (key columns first, then value columns).  Each variable is
    *fresh* — if two columns happen to share the same name the repeated
    variable name is disambiguated with a numeric suffix.
    """
    used_names: set[str] = set()
    variables: list[Variable] = []
    for col in descriptor.columns:
        base = _to_camel_case(col.name)
        name = base
        i = 1
        while name in used_names:
            name = f"{base}{i}"
            i += 1
        used_names.add(name)
        variables.append(Variable(name=name))
    return Clause(
        head=Compound(
            functor=descriptor.name,
            args=variables,
        ),
        body=None,
    )


def _wrap_query_rule_clause(clause: Clause) -> Clause:
    """Wrap *clause* as a ``query_rule/2`` fact.

    Facts become ``query_rule(Head, true)`` and rules become
    ``query_rule(Head, Body)``.  The returned wrapper clause is always a
    fact (``body=None``).
    """
    body = clause.body if clause.body is not None else Atom("true")
    return Clause(head=Compound("query_rule", [clause.head, body]), body=None)


def _generate_clauses(descriptors: list[RelationDescriptor]) -> list[Clause]:
    """Generate base-predicate clauses for all discovered relations."""
    return [_generate_clause_for_relation(d) for d in descriptors]


class MnesticRuleSetStore(RuleSetStore):
    """Rule store backed by a mnestic (CozoDB) database.

    Discovers the database schema on first access and generates one
    positional base-predicate fact per stored relation, using the
    column order from the descriptor (key columns first, then value
    columns).  Results are memoized for the store's lifetime.
    """

    def __init__(
        self,
        path: str | Path,
        name: str | None = None,
        support: str | Path | None = None,
    ) -> None:
        self.path = Path(path)
        self.name = name
        self.support = Path(support) if support is not None else None
        self._adapter = MnesticAdapter(str(self.path))
        self._ruleset_hash: str | None = None
        self._clauses: list[Clause] | None = None
        self._descriptor: list[RelationDescriptor] | None = None

    # ------------------------------------------------------------------
    # Internal — lazy load / memoize
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Discover schema and generate clauses on first access."""
        if self._ruleset_hash is not None and self._clauses is not None:
            return
        # Register the adapter under the store's configured name once.
        if self.name is not None:
            register(self.name, self._adapter)
        descriptors = self._adapter.discover_schema()
        base_clauses = _generate_clauses(descriptors)
        query_rule_clauses: list[Clause] = []
        if self.support is not None:
            program = parse_file(str(self.support))
            support_clauses = _program_clauses(program)
            if not support_clauses:
                raise ValueError(
                    f"Support file {self.support} contains no clauses: "
                    "the interpreted program has no clauses. An empty program "
                    "cannot resolve any goal and is not a meaningful input."
                )
            query_rule_clauses = [_wrap_query_rule_clause(c) for c in support_clauses]
        clauses = base_clauses + query_rule_clauses
        self._clauses = clauses
        self._descriptor = descriptors
        self._ruleset_hash = hash_clauses(clauses)

    # ------------------------------------------------------------------
    # RuleSetStore ABC implementation
    # ------------------------------------------------------------------

    @property
    def ruleset_hash(self) -> str:
        """Return the content hash of the generated base predicates."""
        self._load()
        assert self._ruleset_hash is not None
        return self._ruleset_hash

    def known_rulesets(self) -> list[str]:
        """Return the single content hash owned by this mnestic store."""
        return [self.ruleset_hash]

    def clauses_for(self, ruleset_hash: str) -> list[Clause]:
        """Return the generated clauses when *ruleset_hash* matches.

        Raises:
            KeyError: If *ruleset_hash* does not match this store's hash.
        """
        self._load()
        assert self._clauses is not None
        if ruleset_hash != self.ruleset_hash:
            raise KeyError(f"Unknown ruleset hash: {ruleset_hash}")
        return list(self._clauses)

    # ------------------------------------------------------------------
    # Display / metadata parity with FileRuleSetStore
    # ------------------------------------------------------------------

    def store_info(self) -> StoreInfo:
        """Return display metadata for this mnestic store."""
        return StoreInfo(
            type="mnestic",
            name=self.name,
            path=str(self.path),
            hash=self.ruleset_hash,
        )
