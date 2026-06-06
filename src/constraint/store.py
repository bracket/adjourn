"""Rule store and config helpers for content-addressed rulesets."""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from constraint.parser.ast import Atom, Clause, Compound, Float, Integer, List, Program, String, Variable
from constraint.parser.parser import parse_file


class Config:
    """Read and validate a project rule-store configuration file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._data = self._load()

    @property
    def store_configs(self) -> list[dict[str, Any]]:
        """Return validated store configuration entries."""
        return list(self._data["stores"])

    @property
    def aliases(self) -> dict[str, str]:
        """Return validated alias mappings."""
        return dict(self._data["aliases"])

    @property
    def base_dir(self) -> Path:
        """Return the base directory for relative ruleset file paths."""
        if self.path.parent.name == ".constraint":
            return self.path.parent.parent
        return self.path.parent

    def alias_hash(self, name: str) -> str:
        """Resolve a configured alias to its ruleset hash."""
        try:
            return self._data["aliases"][name]
        except KeyError as exc:
            raise ValueError(f"Unknown ruleset alias: {name}") from exc

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            raise FileNotFoundError(f"Config file not found: {self.path}")

        with self.path.open(encoding="utf-8") as handle:
            raw_data = yaml.safe_load(handle) or {}

        if not isinstance(raw_data, dict):
            raise ValueError(f"Invalid config file {self.path}: expected a mapping")
        if "stores" not in raw_data:
            raise ValueError(f"Invalid config file {self.path}: missing 'stores'")
        if "aliases" not in raw_data:
            raise ValueError(f"Invalid config file {self.path}: missing 'aliases'")

        stores = raw_data["stores"]
        aliases = raw_data["aliases"]

        if not isinstance(stores, list):
            raise ValueError(f"Invalid config file {self.path}: 'stores' must be a list")
        if not isinstance(aliases, dict):
            raise ValueError(f"Invalid config file {self.path}: 'aliases' must be a mapping")

        validated_stores: list[dict[str, Any]] = []
        for index, store in enumerate(stores):
            if not isinstance(store, dict):
                raise ValueError(
                    f"Invalid config file {self.path}: store #{index} must be a mapping"
                )
            if "type" not in store:
                raise ValueError(
                    f"Invalid config file {self.path}: store #{index} missing 'type'"
                )
            if "path" not in store:
                raise ValueError(
                    f"Invalid config file {self.path}: store #{index} missing 'path'"
                )
            validated_stores.append({"type": store["type"], "path": store["path"]})

        validated_aliases: dict[str, str] = {}
        for alias_name, ruleset_hash in aliases.items():
            if not isinstance(alias_name, str):
                raise ValueError(
                    f"Invalid config file {self.path}: alias names must be strings"
                )
            if not isinstance(ruleset_hash, str):
                raise ValueError(
                    f"Invalid config file {self.path}: alias '{alias_name}' must map to a string hash"
                )
            validated_aliases[alias_name] = ruleset_hash

        return {"stores": validated_stores, "aliases": validated_aliases}


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


class FileRuleSetStore(RuleSetStore):
    """Rule store backed by a single Prolog file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
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
        stores.append(FileRuleSetStore(store_path))
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
