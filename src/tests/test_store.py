"""Tests for config-backed ruleset stores."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from constraint.config import Config
from constraint.parser.ast import Atom, Clause, Compound
from constraint.store import (
    AggregateRuleSetStore,
    FileRuleSetStore,
    RuleSetStore,
    build_store_from_config,
)


def _write_rules(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content)
    return path


class _EmptyRuleSetStore(RuleSetStore):
    @property
    def ruleset_hash(self) -> str:
        return "f" * 64

    def known_rulesets(self) -> list[str]:
        return [self.ruleset_hash]

    def clauses_for(self, ruleset_hash: str) -> list[Clause]:
        if ruleset_hash != self.ruleset_hash:
            raise KeyError(f"Unknown ruleset hash: {ruleset_hash}")
        return []


class TestHashing:
    """Hash canonicalization properties."""

    def test_variable_renaming_hashes_equal(self, tmp_path: Path) -> None:
        left = FileRuleSetStore(_write_rules(tmp_path, "left.pl", "p(X) :- q(X).\n"))
        right = FileRuleSetStore(_write_rules(tmp_path, "right.pl", "p(Y) :- q(Y).\n"))
        assert left.known_rulesets() == right.known_rulesets()

    def test_shared_and_distinct_variables_hash_differ(self, tmp_path: Path) -> None:
        left = FileRuleSetStore(_write_rules(tmp_path, "left.pl", "p(X, X).\n"))
        right = FileRuleSetStore(_write_rules(tmp_path, "right.pl", "p(Y, Z).\n"))
        assert left.known_rulesets() != right.known_rulesets()

    def test_whitespace_and_comments_do_not_change_hash(self, tmp_path: Path) -> None:
        left = FileRuleSetStore(_write_rules(tmp_path, "left.pl", "p(X) :- q(X).\n"))
        right = FileRuleSetStore(
            _write_rules(
                tmp_path,
                "right.pl",
                "% comment only\n\np( Y ) :-\n    q(Y).\n",
            )
        )
        assert left.known_rulesets() == right.known_rulesets()

    def test_clause_order_changes_hash(self, tmp_path: Path) -> None:
        left = FileRuleSetStore(_write_rules(tmp_path, "left.pl", "p(a).\np(b).\n"))
        right = FileRuleSetStore(_write_rules(tmp_path, "right.pl", "p(b).\np(a).\n"))
        assert left.known_rulesets() != right.known_rulesets()


class TestConfig:
    """Config loading tests."""

    def test_loads_valid_yaml(self, tmp_path: Path) -> None:
        config_path = tmp_path / ".constraint" / "config.yaml"
        config_path.parent.mkdir()
        config_path.write_text(
            yaml.safe_dump(
                {
                    "stores": [{"type": "file", "path": "rules/test.pl"}],
                    "aliases": {"test_rules": "abc123"},
                }
            )
        )

        config = Config(config_path)

        assert config.store_configs == [
            {"type": "file", "path": "rules/test.pl", "prolog": "constraint"}
        ]
        assert config.aliases == {"test_rules": "abc123"}

    def test_loads_store_name(self, tmp_path: Path) -> None:
        config_path = tmp_path / ".constraint" / "config.yaml"
        config_path.parent.mkdir()
        config_path.write_text(
            yaml.safe_dump(
                {
                    "stores": [{"type": "file", "path": "rules/test.pl", "name": "test"}],
                    "aliases": {"test_rules": "abc123"},
                }
            )
        )

        config = Config(config_path)

        assert config.store_configs == [
            {
                "type": "file",
                "path": "rules/test.pl",
                "name": "test",
                "prolog": "constraint",
            }
        ]

    def test_loads_strict_store_prolog_mode(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.safe_dump(
                {
                    "stores": [
                        {"type": "file", "path": "rules/test.pl", "prolog": "strict"}
                    ],
                    "aliases": {},
                }
            )
        )

        config = Config(config_path)

        assert config.store_configs == [
            {"type": "file", "path": "rules/test.pl", "prolog": "strict"}
        ]

    def test_rejects_invalid_store_prolog_mode(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.safe_dump(
                {
                    "stores": [
                        {"type": "file", "path": "rules/test.pl", "prolog": "invalid"}
                    ],
                    "aliases": {},
                }
            )
        )

        with pytest.raises(
            ValueError,
            match="'prolog' must be 'constraint' or 'strict'",
        ):
            Config(config_path)

    def test_rejects_system_alias_prefix_in_store_name(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.safe_dump(
                {
                    "stores": [{"type": "file", "path": "rules/test.pl", "name": "@first"}],
                    "aliases": {},
                }
            )
        )

        with pytest.raises(ValueError, match="cannot start with '@'"):
            Config(config_path)

    def test_rejects_system_alias_prefix_in_alias_name(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.safe_dump(
                {
                    "stores": [{"type": "file", "path": "rules/test.pl"}],
                    "aliases": {"@first": "abc123"},
                }
            )
        )

        with pytest.raises(ValueError, match="cannot start with '@'"):
            Config(config_path)

    def test_rejects_duplicate_store_names(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.safe_dump(
                {
                    "stores": [
                        {"type": "file", "path": "rules/left.pl", "name": "shared"},
                        {"type": "file", "path": "rules/right.pl", "name": "shared"},
                    ],
                    "aliases": {},
                }
            )
        )

        with pytest.raises(ValueError, match="duplicate store name 'shared'"):
            Config(config_path)

    def test_rejects_store_name_alias_collision(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.safe_dump(
                {
                    "stores": [{"type": "file", "path": "rules/test.pl", "name": "shared"}],
                    "aliases": {"shared": "abc123"},
                }
            )
        )

        with pytest.raises(ValueError, match="collides with alias"):
            Config(config_path)


class TestStores:
    """Store dispatch tests."""

    def test_file_store_returns_clauses_for_known_hash(self, tmp_path: Path) -> None:
        rules_path = _write_rules(tmp_path, "rules.pl", "p(a).\n")
        store = FileRuleSetStore(rules_path)
        ruleset_hash = store.known_rulesets()[0]

        clauses = store.clauses_for(ruleset_hash)

        assert [str(clause) for clause in clauses] == ["rule(p(a), true)."]

    def test_file_store_exposes_name(self, tmp_path: Path) -> None:
        rules_path = _write_rules(tmp_path, "rules.pl", "p(a).\n")
        store = FileRuleSetStore(rules_path, name="rules")

        assert store.name == "rules"

    def test_file_store_ruleset_hash_matches_known_ruleset(self, tmp_path: Path) -> None:
        rules_path = _write_rules(tmp_path, "rules.pl", "p(a).\n")
        store = FileRuleSetStore(rules_path)

        assert store.ruleset_hash == store.known_rulesets()[0]

    def test_file_store_rejects_empty_ruleset(self, tmp_path: Path) -> None:
        rules_path = _write_rules(tmp_path, "rules.pl", "% empty\n")
        store = FileRuleSetStore(rules_path)

        with pytest.raises(ValueError, match="empty program"):
            store.known_rulesets()

    def test_constraint_mode_wraps_bare_clauses(self, tmp_path: Path) -> None:
        rules_path = _write_rules(tmp_path, "rules.pl", "foo.\nbar :- baz.\n")
        store = FileRuleSetStore(rules_path)
        ruleset_hash = store.known_rulesets()[0]

        clauses = store.clauses_for(ruleset_hash)

        assert all(clause.body is None for clause in clauses)
        assert clauses == [
            Clause(
                head=Compound("rule", [Atom("foo"), Atom("true")]),
                body=None,
            ),
            Clause(
                head=Compound(
                    "rule",
                    [
                        Atom("bar"),
                        Atom("baz"),
                    ],
                ),
                body=None,
            ),
        ]

    def test_constraint_and_strict_modes_produce_equal_hash_for_equivalent_rules(
        self, tmp_path: Path
    ) -> None:
        constraint_store = FileRuleSetStore(
            _write_rules(tmp_path, "constraint.pl", "foo.\nbar :- baz.\n"),
        )
        strict_store = FileRuleSetStore(
            _write_rules(
                tmp_path,
                "strict.pl",
                "rule(foo, true).\nrule(bar, baz).\n",
            ),
            prolog="strict",
        )

        assert constraint_store.ruleset_hash == strict_store.ruleset_hash

    def test_strict_mode_keeps_rule_clauses_unmodified(self, tmp_path: Path) -> None:
        rules_path = _write_rules(tmp_path, "rules.pl", "rule(foo, true).\n")
        store = FileRuleSetStore(rules_path, prolog="strict")
        ruleset_hash = store.ruleset_hash

        clauses = store.clauses_for(ruleset_hash)

        assert clauses == [Clause(head=Compound("rule", [Atom("foo"), Atom("true")]))]

    def test_constraint_mode_keeps_directives_rejected(self, tmp_path: Path) -> None:
        rules_path = _write_rules(tmp_path, "rules.pl", ":- dynamic foo/0.\nfoo.\n")
        store = FileRuleSetStore(rules_path)

        with pytest.raises(ValueError, match="unsupported item"):
            store.known_rulesets()

    def test_aggregate_dispatches_to_child_store(self, tmp_path: Path) -> None:
        left = FileRuleSetStore(_write_rules(tmp_path, "left.pl", "p(a).\n"))
        right = FileRuleSetStore(_write_rules(tmp_path, "right.pl", "q(b).\n"))
        aggregate = AggregateRuleSetStore([left, right])
        right_hash = right.ruleset_hash

        clauses = aggregate.clauses_for(right_hash)

        assert [str(clause) for clause in clauses] == ["rule(q(b), true)."]

    def test_aggregate_ruleset_hash_passthrough_single_member(
        self, tmp_path: Path
    ) -> None:
        store = FileRuleSetStore(_write_rules(tmp_path, "rules.pl", "p(a).\n"))

        aggregate = AggregateRuleSetStore([store])

        assert aggregate.ruleset_hash == store.ruleset_hash

    def test_aggregate_ruleset_hash_hashes_multiple_members(self, tmp_path: Path) -> None:
        left = FileRuleSetStore(_write_rules(tmp_path, "left.pl", "p(a).\n"))
        right = FileRuleSetStore(_write_rules(tmp_path, "right.pl", "q(b).\n"))

        aggregate = AggregateRuleSetStore([left, right])

        expected_hash = hashlib.sha256(
            b"chain\x00"
            + b"\x00".join(
                ruleset_hash.encode("utf-8")
                for ruleset_hash in [left.ruleset_hash, right.ruleset_hash]
            )
        ).hexdigest()

        assert aggregate.ruleset_hash == expected_hash

    def test_aggregate_dedupes_duplicate_member_stores(self, tmp_path: Path) -> None:
        left = FileRuleSetStore(_write_rules(tmp_path, "left.pl", "p(a).\n"))
        duplicate = FileRuleSetStore(_write_rules(tmp_path, "duplicate.pl", "p(a).\n"))

        aggregate = AggregateRuleSetStore([left, duplicate])

        assert aggregate.ruleset_hash == left.ruleset_hash
        assert [str(clause) for clause in aggregate.clauses_for(aggregate.ruleset_hash)] == [
            "rule(p(a), true)."
        ]

    def test_aggregate_clauses_for_composite_hash_concatenates_in_config_order(
        self, tmp_path: Path
    ) -> None:
        left = FileRuleSetStore(_write_rules(tmp_path, "left.pl", "p(a).\np(b).\n"))
        right = FileRuleSetStore(_write_rules(tmp_path, "right.pl", "q(c).\n"))

        aggregate = AggregateRuleSetStore([left, right])

        clauses = aggregate.clauses_for(aggregate.ruleset_hash)

        assert [str(clause) for clause in clauses] == [
            "rule(p(a), true).",
            "rule(p(b), true).",
            "rule(q(c), true).",
        ]

    def test_aggregate_owns_composite_hash(self, tmp_path: Path) -> None:
        store = FileRuleSetStore(_write_rules(tmp_path, "rules.pl", "p(a).\n"))

        aggregate = AggregateRuleSetStore([store])

        assert aggregate.owns(aggregate.ruleset_hash)

    def test_aggregate_raises_for_unknown_hash(self, tmp_path: Path) -> None:
        store = AggregateRuleSetStore(
            [FileRuleSetStore(_write_rules(tmp_path, "rules.pl", "p(a).\n"))]
        )

        with pytest.raises(KeyError, match="Unknown ruleset hash"):
            store.clauses_for("missing")

    def test_build_store_from_config_uses_project_root_paths(self, tmp_path: Path) -> None:
        config_dir = tmp_path / ".constraint"
        rules_dir = tmp_path / "rules"
        config_dir.mkdir()
        rules_dir.mkdir()
        rules_path = _write_rules(rules_dir, "rules.pl", "p(a).\n")
        file_store = FileRuleSetStore(rules_path)
        ruleset_hash = file_store.known_rulesets()[0]

        config_path = config_dir / "config.yaml"
        config_path.write_text(
            yaml.safe_dump(
                {
                    "stores": [{"type": "file", "path": "rules/rules.pl"}],
                    "aliases": {"test_rules": ruleset_hash},
                }
            )
        )

        aggregate = build_store_from_config(Config(config_path))

        assert aggregate.clauses_for(ruleset_hash)

    def test_build_store_from_config_passes_store_name(self, tmp_path: Path) -> None:
        config_dir = tmp_path / ".constraint"
        rules_dir = tmp_path / "rules"
        config_dir.mkdir()
        rules_dir.mkdir()
        _write_rules(rules_dir, "rules.pl", "p(a).\n")
        config_path = config_dir / "config.yaml"
        config_path.write_text(
            yaml.safe_dump(
                {
                    "stores": [
                        {"type": "file", "path": "rules/rules.pl", "name": "named-rules"}
                    ],
                    "aliases": {},
                }
            )
        )

        aggregate = build_store_from_config(Config(config_path))

        assert aggregate.store_info_list()[1].name == "named-rules"

    def test_aggregate_store_info_list_preserves_config_order(self, tmp_path: Path) -> None:
        left_path = _write_rules(tmp_path, "left.pl", "p(a).\n")
        right_path = _write_rules(tmp_path, "right.pl", "q(b).\n")
        left = FileRuleSetStore(left_path, name="left")
        right = FileRuleSetStore(right_path)

        aggregate = AggregateRuleSetStore([left, right])
        store_info = aggregate.store_info_list()

        assert [info.type for info in store_info] == ["system", "file", "file"]
        assert [info.name for info in store_info] == ["@top", "left", None]
        assert [info.path for info in store_info] == ["", str(left_path), str(right_path)]
        assert [info.hash for info in store_info] == [
            aggregate.ruleset_hash,
            left.ruleset_hash,
            right.ruleset_hash,
        ]

    def test_aggregate_rejects_empty_composite_hash(self) -> None:
        aggregate = AggregateRuleSetStore([_EmptyRuleSetStore()])

        with pytest.raises(ValueError, match="empty program"):
            aggregate.clauses_for(aggregate.ruleset_hash)
