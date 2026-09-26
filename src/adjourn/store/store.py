"""Rule store and config helpers for content-addressed rulesets."""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from adjourn.parser.ast import Atom, Clause, Compound, Float, Integer, List, Program, String, Variable
from adjourn.parser.parser import parse_file
from adjourn.config import Config


class RuleSetStore(ABC):
    """Abstract base class for ruleset stores."""

    @property
    @abstractmethod
    def ruleset_hash(self) -> str:
        """Return the primary ruleset hash for this store."""

    @abstractmethod
    def known_rulesets(self) -> list[str]:
        """Return the content hashes known to this store."""

    @abstractmethod
    def clauses_for(self, ruleset_hash: str) -> list[Clause]:
        """Return the clauses for *ruleset_hash*."""

    def owns(self, ruleset_hash: str) -> bool:
        """Return whether this store contains *ruleset_hash*."""
        return ruleset_hash in self.known_rulesets()


@dataclass(frozen=True)
class StoreInfo:
    """Metadata for a configured ruleset store."""

    type: str
    path: str
    hash: str
    name: str | None = None


class FileRuleSetStore(RuleSetStore):
    """Rule store backed by a single Prolog file."""

    def __init__(
        self,
        path: str | Path,
        name: str | None = None,
        prolog: str = "wrapped",
    ) -> None:
        self.path = Path(path)
        self.name = name
        self.prolog = prolog
        self._ruleset_hash: str | None = None
        self._clauses: list[Clause] | None = None

    @property
    def ruleset_hash(self) -> str:
        """Return the file store's content hash."""
        self._load()
        assert self._ruleset_hash is not None
        return self._ruleset_hash

    def known_rulesets(self) -> list[str]:
        """Return the single content hash owned by this file store."""
        return [self.ruleset_hash]

    def clauses_for(self, ruleset_hash: str) -> list[Clause]:
        """Return the file's clauses when *ruleset_hash* matches."""
        self._load()
        assert self._clauses is not None
        if ruleset_hash != self.ruleset_hash:
            raise KeyError(f"Unknown ruleset hash: {ruleset_hash}")
        return list(self._clauses)

    def _load(self) -> None:
        if self._ruleset_hash is not None and self._clauses is not None:
            return
        program = parse_file(str(self.path))
        clauses = _program_clauses(program)
        if self.prolog == "wrapped":
            clauses = [_wrap_clause(clause) for clause in clauses]
        if not clauses:
            raise ValueError(
                f"Ruleset file {self.path} parsed to an empty program: "
                "the interpreted program has no clauses. An empty program "
                "cannot resolve any goal and is not a meaningful input."
            )
        self._clauses = clauses
        self._ruleset_hash = hash_clauses(clauses)

    def store_info(self) -> StoreInfo:
        """Return display metadata for this file store."""
        return StoreInfo(
            type="file",
            name=self.name,
            path=str(self.path),
            hash=self.ruleset_hash,
        )


class AggregateRuleSetStore(RuleSetStore):
    """Aggregate multiple child stores as an ordered `chain`."""

    def __init__(self, stores: list[RuleSetStore]) -> None:
        self._stores = list(stores)
        self._member_stores = _dedupe_stores_by_ruleset_hash(self._stores)
        self._member_hashes = [store.ruleset_hash for store in self._member_stores]
        self._ruleset_hash: str | None = None

    @property
    def ruleset_hash(self) -> str:
        """Return the aggregate chain hash."""
        ruleset_hash = self._composite_ruleset_hash()
        if ruleset_hash is None:
            raise ValueError(
                "Aggregate ruleset resolved to an empty program: "
                "the interpreted program has no clauses. An empty program "
                "cannot resolve any goal and is not a meaningful input."
            )
        return ruleset_hash

    def known_rulesets(self) -> list[str]:
        """Return the aggregate hash plus all owned child hashes."""
        known_rulesets: list[str] = []
        seen_hashes: set[str] = set()
        composite_hash = self._composite_ruleset_hash()
        if composite_hash is not None:
            known_rulesets.append(composite_hash)
            seen_hashes.add(composite_hash)
        for store in self._member_stores:
            for ruleset_hash in store.known_rulesets():
                if ruleset_hash in seen_hashes:
                    continue
                seen_hashes.add(ruleset_hash)
                known_rulesets.append(ruleset_hash)
        return known_rulesets

    def clauses_for(self, ruleset_hash: str) -> list[Clause]:
        """Return chained clauses for the aggregate hash or dispatch to a child."""
        composite_hash = self._composite_ruleset_hash()
        if composite_hash is not None and ruleset_hash == composite_hash:
            clauses = [
                clause
                for store, member_hash in zip(
                    self._member_stores, self._member_hashes, strict=True
                )
                for clause in store.clauses_for(member_hash)
            ]
            if not clauses:
                raise ValueError(
                    "Aggregate ruleset resolved to an empty program: "
                    "the interpreted program has no clauses. An empty program "
                    "cannot resolve any goal and is not a meaningful input."
                )
            return clauses
        for store in self._member_stores:
            if store.owns(ruleset_hash):
                return store.clauses_for(ruleset_hash)
        raise KeyError(f"Unknown ruleset hash: {ruleset_hash}")

    def owns(self, ruleset_hash: str) -> bool:
        """Return whether the aggregate or any child store owns *ruleset_hash*."""
        composite_hash = self._composite_ruleset_hash()
        if composite_hash is not None and ruleset_hash == composite_hash:
            return True
        return any(store.owns(ruleset_hash) for store in self._member_stores)

    def store_info_list(self) -> list[StoreInfo]:
        """Return the aggregate summary row plus child-store metadata."""
        child_store_info = [
            store.store_info() for store in self._stores if isinstance(store, FileRuleSetStore)
        ]
        if not child_store_info:
            return []
        return [
            StoreInfo(type="system", name="@top", path="", hash=self.ruleset_hash),
            *child_store_info,
        ]

    def _composite_ruleset_hash(self) -> str | None:
        if self._ruleset_hash is not None:
            return self._ruleset_hash
        if not self._member_hashes:
            return None
        if len(self._member_hashes) == 1:
            self._ruleset_hash = self._member_hashes[0]
            return self._ruleset_hash
        self._ruleset_hash = _hash_chain(self._member_hashes)
        return self._ruleset_hash


def build_store_from_config(config: Config) -> AggregateRuleSetStore:
    """Build an aggregate rule store from *config*."""
    stores: list[RuleSetStore] = []
    for store_config in config.store_configs:
        store_type = store_config["type"]
        store_path = Path(store_config["path"])
        if not store_path.is_absolute():
            store_path = config.base_dir / store_path
        if store_type == "file":
            stores.append(
                FileRuleSetStore(
                    store_path,
                    name=store_config.get("name"),
                    prolog=store_config["prolog"],
                )
            )
        elif store_type == "mnestic":
            from adjourn.store.mnestic_store import MnesticRuleSetStore
            support_val = store_config.get("support")
            support_path: Path | None = None
            if support_val is not None:
                support_path = Path(support_val)
                if not support_path.is_absolute():
                    support_path = config.base_dir / support_path
            stores.append(
                MnesticRuleSetStore(
                    store_path,
                    name=store_config.get("name"),
                    support=support_path,
                )
            )
        else:
            raise ValueError(f"Unsupported store type: {store_type}")
    return AggregateRuleSetStore(stores)


def _dedupe_stores_by_ruleset_hash(stores: list[RuleSetStore]) -> list[RuleSetStore]:
    deduped_stores: list[RuleSetStore] = []
    seen_hashes: set[str] = set()
    for store in stores:
        ruleset_hash = store.ruleset_hash
        if ruleset_hash in seen_hashes:
            continue
        seen_hashes.add(ruleset_hash)
        deduped_stores.append(store)
    return deduped_stores


def _hash_chain(ruleset_hashes: list[str]) -> str:
    payload = b"chain\x00" + b"\x00".join(
        ruleset_hash.encode("utf-8") for ruleset_hash in ruleset_hashes
    )
    return hashlib.sha256(payload).hexdigest()


def hash_clauses(clauses: list[Clause]) -> str:
    """Return the content hash for *clauses*."""
    canonical = "\n".join(canonical_clause(clause) for clause in clauses)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def canonical_clause(clause: Clause) -> str:
    """Return a canonical serialization for *clause*."""
    variable_ids: dict[str, str] = {}
    next_id = [0]
    head = _canonical_term(clause.head, variable_ids, next_id)
    body = "a:true" if clause.body is None else _canonical_term(clause.body, variable_ids, next_id)
    return f"cl:({head}:-{body})"


def _program_clauses(program: Program) -> list[Clause]:
    clauses: list[Clause] = []
    for item in program.items:
        if not isinstance(item, Clause):
            raise ValueError(f"Ruleset file contains unsupported item: {item}")
        clauses.append(item)
    return clauses


def _wrap_clause(clause: Clause) -> Clause:
    """Wrap clause as a `rule/2` fact for wrapped-mode hashing/loading.

    Facts become ``rule(Head, true)`` and rules become ``rule(Head, Body)``.
    The returned wrapper clause is always a fact (``body=None``).
    This helper assumes `_program_clauses` has already filtered non-clause items.
    """
    body = clause.body if clause.body is not None else Atom("true")
    return Clause(head=Compound("rule", [clause.head, body]), body=None)


def _canonical_term(
    term: Any,
    variable_ids: dict[str, str],
    next_id: list[int],
) -> str:
    if isinstance(term, Atom):
        return f"a:{_quoted(term.value)}"
    if isinstance(term, Integer):
        return f"i:{term.value}"
    if isinstance(term, Float):
        return f"f:{term.value!r}"
    if isinstance(term, String):
        return f"s:{_quoted(term.value)}"
    if isinstance(term, Variable):
        return f"v:{_quoted(_canonical_variable_id(term, variable_ids, next_id))}"
    if isinstance(term, Compound):
        args = ",".join(
            _canonical_term(arg, variable_ids, next_id) for arg in term.args
        )
        return f"c:{_quoted(term.functor)}/{len(term.args)}({args})"
    if isinstance(term, List):
        elements = ",".join(
            _canonical_term(element, variable_ids, next_id) for element in term.elements
        )
        tail = "a:nil"
        if term.tail is not None:
            tail = _canonical_term(term.tail, variable_ids, next_id)
        return f"l:[{elements}|{tail}]"
    raise TypeError(f"Unsupported AST node: {term!r}")


def _canonical_variable_id(
    variable: Variable,
    variable_ids: dict[str, str],
    next_id: list[int],
) -> str:
    if variable.name.startswith("_"):
        return _next_variable_id(next_id)
    try:
        return variable_ids[variable.name]
    except KeyError:
        canonical_id = _next_variable_id(next_id)
        variable_ids[variable.name] = canonical_id
        return canonical_id


def _next_variable_id(next_id: list[int]) -> str:
    canonical_id = f"_V{next_id[0]}"
    next_id[0] += 1
    return canonical_id


def _quoted(value: str) -> str:
    return json.dumps(value, separators=(",", ":"))
