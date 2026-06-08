"""Rule store and config helpers for content-addressed rulesets."""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from constraint.parser.ast import Atom, Clause, Compound, Float, Integer, List, Program, String, Variable
from constraint.parser.parser import parse_file
from constraint.config import Config


class RuleSetStore(ABC):
    """Abstract base class for ruleset stores."""

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

    def __init__(self, path: str | Path, name: str | None = None) -> None:
        self.path = Path(path)
        self.name = name
        self._ruleset_hash: str | None = None
        self._clauses: list[Clause] | None = None

    def known_rulesets(self) -> list[str]:
        """Return the single content hash owned by this file store."""
        self._load()
        assert self._ruleset_hash is not None
        return [self._ruleset_hash]

    def clauses_for(self, ruleset_hash: str) -> list[Clause]:
        """Return the file's clauses when *ruleset_hash* matches."""
        self._load()
        assert self._ruleset_hash is not None
        assert self._clauses is not None
        if ruleset_hash != self._ruleset_hash:
            raise KeyError(f"Unknown ruleset hash: {ruleset_hash}")
        return list(self._clauses)

    def _load(self) -> None:
        if self._ruleset_hash is not None and self._clauses is not None:
            return
        program = parse_file(str(self.path))
        clauses = _program_clauses(program)
        self._clauses = clauses
        self._ruleset_hash = hash_clauses(clauses)

    def store_info(self) -> StoreInfo:
        """Return display metadata for this file store."""
        self._load()
        assert self._ruleset_hash is not None
        return StoreInfo(
            type="file",
            name=self.name,
            path=str(self.path),
            hash=self._ruleset_hash,
        )


class AggregateRuleSetStore(RuleSetStore):
    """Aggregate multiple child stores behind a hash index."""

    def __init__(self, stores: list[RuleSetStore]) -> None:
        self._stores = list(stores)
        self._stores_by_hash: dict[str, RuleSetStore] = {}
        for store in self._stores:
            for ruleset_hash in store.known_rulesets():
                self._stores_by_hash.setdefault(ruleset_hash, store)

    def known_rulesets(self) -> list[str]:
        """Return the union of known child-store hashes."""
        return list(self._stores_by_hash)

    def clauses_for(self, ruleset_hash: str) -> list[Clause]:
        """Dispatch clause lookup to the indexed owning store."""
        try:
            store = self._stores_by_hash[ruleset_hash]
        except KeyError as exc:
            raise KeyError(f"Unknown ruleset hash: {ruleset_hash}") from exc
        return store.clauses_for(ruleset_hash)

    def owns(self, ruleset_hash: str) -> bool:
        """Return whether any child store owns *ruleset_hash*."""
        return ruleset_hash in self._stores_by_hash

    def store_info_list(self) -> list[StoreInfo]:
        """Return child-store metadata in configured order."""
        return [store.store_info() for store in self._stores if isinstance(store, FileRuleSetStore)]


def build_store_from_config(config: Config) -> AggregateRuleSetStore:
    """Build an aggregate rule store from *config*."""
    stores: list[RuleSetStore] = []
    for store_config in config.store_configs:
        store_type = store_config["type"]
        if store_type != "file":
            raise ValueError(f"Unsupported store type: {store_type}")
        store_path = Path(store_config["path"])
        if not store_path.is_absolute():
            store_path = config.base_dir / store_path
        stores.append(FileRuleSetStore(store_path, name=store_config.get("name")))
    return AggregateRuleSetStore(stores)


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
