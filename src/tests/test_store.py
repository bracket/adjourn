"""Tests for config-backed ruleset stores."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from constraint.store import AggregateRuleSetStore, Config, FileRuleSetStore, build_store_from_config


def _write_rules(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content)
    return path


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

        assert config.store_configs == [{"type": "file", "path": "rules/test.pl"}]
        assert config.aliases == {"test_rules": "abc123"}


class TestStores:
    """Store dispatch tests."""

    def test_file_store_returns_clauses_for_known_hash(self, tmp_path: Path) -> None:
        rules_path = _write_rules(tmp_path, "rules.pl", "p(a).\n")
        store = FileRuleSetStore(rules_path)
        ruleset_hash = store.known_rulesets()[0]

        clauses = store.clauses_for(ruleset_hash)

        assert [str(clause) for clause in clauses] == ["p(a)."]

    def test_aggregate_dispatches_to_child_store(self, tmp_path: Path) -> None:
        left = FileRuleSetStore(_write_rules(tmp_path, "left.pl", "p(a).\n"))
        right = FileRuleSetStore(_write_rules(tmp_path, "right.pl", "q(b).\n"))
        aggregate = AggregateRuleSetStore([left, right])
        right_hash = right.known_rulesets()[0]

        clauses = aggregate.clauses_for(right_hash)

        assert [str(clause) for clause in clauses] == ["q(b)."]

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
