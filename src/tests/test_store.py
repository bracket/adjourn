"""Tests for config-backed ruleset stores."""

from __future__ import annotations

import hashlib
import shutil
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
    lookup,
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

    def test_constraint_mode_rejects_directives(self, tmp_path: Path) -> None:
        rules_path = _write_rules(tmp_path, "rules.pl", ":- dynamic foo/0.\nfoo.\n")
        store = FileRuleSetStore(rules_path)

        with pytest.raises(ValueError, match="unsupported item"):
            store.known_rulesets()

    def test_strict_mode_rejects_directives(self, tmp_path: Path) -> None:
        rules_path = _write_rules(
            tmp_path,
            "rules.pl",
            """:- dynamic foo/0.
rule(foo, true).
""",
        )
        store = FileRuleSetStore(rules_path, prolog="strict")

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

# ---------------------------------------------------------------------------
# Mnestic (CozoDB) store tests
# ---------------------------------------------------------------------------


from constraint.store import (
    MnesticAdapter,
    MnesticRuleSetStore,
    ColumnDescriptor,
    RelationDescriptor,
    BaseLiteral,
    DerivedLiteral,
    Guard,
)
from constraint.parser.ast import Variable


def _create_mnestic_db(path: str, relation_script: str) -> None:
    """Create and populate a mnestic rocksdb database with the given relation.

    Args:
        path: Filesystem path for the database.
        relation_script: CozoScript to create the relation (e.g.
            ``:create node { ... }``).
    """
    from mnestic import CozoDbPy

    db = CozoDbPy("rocksdb", path, "")
    db.run_script(relation_script, {}, immutable=False)
    db.close()


class TestMnesticStore:
    """Tests for the MnesticRuleSetStore and its integration."""

    def test_mnestic_store_loads_node_relation(self, tmp_path: Path) -> None:
        """End-to-end: build a mnestic db with the node relation,
        load through build_store_from_config, and verify the generated
        base predicate."""
        db_path = tmp_path / "nodes.db"
        _create_mnestic_db(
            str(db_path),
            (
                ":create node {"
                "    id: Int"
                "    =>"
                "    kind: String,"
                "    parent_id: Int?,"
                "    start_byte: Int,"
                "    end_byte: Int,"
                "    start_row: Int,"
                "    start_col: Int,"
                "    end_row: Int,"
                "    end_col: Int,"
                "    is_named: Bool,"
                "    text: String,"
                "}"
            ),
        )

        # Write a config pointing at the mnestic database
        config_dir = tmp_path / ".constraint"
        config_dir.mkdir()
        config_path = config_dir / "config.yaml"
        config_path.write_text(
            yaml.safe_dump(
                {
                    "stores": [{"type": "mnestic", "path": str(db_path)}],
                    "aliases": {},
                }
            )
        )

        aggregate = build_store_from_config(Config(config_path))
        clauses = aggregate.clauses_for(aggregate.ruleset_hash)

        # There should be exactly one clause (the node/11 base predicate)
        assert len(clauses) == 1
        clause = clauses[0]
        assert clause.body is None  # it's a fact

        # The head should be node(Id, Kind, ParentId, StartByte, EndByte,
        # StartRow, StartCol, EndRow, EndCol, IsNamed, Text)
        head = clause.head
        assert isinstance(head, Compound)
        assert head.functor == "node"
        assert len(head.args) == 11

        # Check variable names match the expected CamelCase order
        expected_var_names = [
            "Id",
            "Kind",
            "ParentId",
            "StartByte",
            "EndByte",
            "StartRow",
            "StartCol",
            "EndRow",
            "EndCol",
            "IsNamed",
            "Text",
        ]
        for arg, expected_name in zip(head.args, expected_var_names, strict=True):
            assert isinstance(arg, Variable)
            assert arg.name == expected_name

        # The aggregate owns the mnestic store's generated clauses
        assert aggregate.owns(aggregate.ruleset_hash)

    def test_mnestic_store_generic_discovery(self, tmp_path: Path) -> None:
        """Prove schema discovery is generic: create a different relation
        shape and verify the generated base predicate matches."""
        db_path = tmp_path / "people.db"
        _create_mnestic_db(
            str(db_path),
            (
                ":create person {"
                "    ssn: Int"
                "    =>"
                "    name: String,"
                "    age: Int,"
                "    email: String?,"
                "}"
            ),
        )

        # Build the store directly (not through config) for simplicity
        store = MnesticRuleSetStore(db_path)
        clauses = store.clauses_for(store.ruleset_hash)

        assert len(clauses) == 1
        clause = clauses[0]
        assert clause.body is None

        head = clause.head
        assert isinstance(head, Compound)
        assert head.functor == "person"
        assert len(head.args) == 4  # ssn + name + age + email

        expected_var_names = ["Ssn", "Name", "Age", "Email"]
        for arg, expected_name in zip(head.args, expected_var_names, strict=True):
            assert isinstance(arg, Variable)
            assert arg.name == expected_name

    def test_mnestic_config_validates_without_prolog(self, tmp_path: Path) -> None:
        """A mnestic config entry must validate without a 'prolog' key."""
        config_dir = tmp_path / ".constraint"
        config_dir.mkdir()
        config_path = config_dir / "config.yaml"

        # Create a dummy mnestic database so the store path exists
        db_path = tmp_path / "dummy.db"
        _create_mnestic_db(
            str(db_path),
            ":create dummy { x: Int => y: Int }",
        )

        config_path.write_text(
            yaml.safe_dump(
                {
                    "stores": [{"type": "mnestic", "path": str(db_path)}],
                    "aliases": {},
                }
            )
        )

        config = Config(config_path)
        # The mnestic store should not have a 'prolog' key
        assert "prolog" not in config.store_configs[0]
        assert config.store_configs[0]["type"] == "mnestic"
        assert config.store_configs[0]["path"] == str(db_path)

    def test_mnestic_config_carries_optional_support(self, tmp_path: Path) -> None:
        """A mnestic config entry with an optional 'support' field carries
        it through onto the validated store dict."""
        config_dir = tmp_path / ".constraint"
        config_dir.mkdir()
        config_path = config_dir / "config.yaml"

        db_path = tmp_path / "dummy2.db"
        _create_mnestic_db(
            str(db_path),
            ":create dummy { x: Int => y: Int }",
        )

        config_path.write_text(
            yaml.safe_dump(
                {
                    "stores": [
                        {
                            "type": "mnestic",
                            "path": str(db_path),
                            "support": "support_file.pl",
                        }
                    ],
                    "aliases": {},
                }
            )
        )

        config = Config(config_path)
        assert config.store_configs[0]["support"] == "support_file.pl"
        assert "prolog" not in config.store_configs[0]

    def test_mnestic_hash_stability(self, tmp_path: Path) -> None:
        """Two stores opened against the same database produce the same
        ruleset_hash."""
        db_path = tmp_path / "stable.db"
        _create_mnestic_db(
            str(db_path),
            (
                ":create item {"
                "    code: String"
                "    =>"
                "    description: String,"
                "    price: Float,"
                "}"
            ),
        )

        # RocksDB holds an exclusive lock per database path within a process,
        # so open the second store against an identical copy of the database
        # (same content) to prove hash stability.
        db_copy = tmp_path / "stable_copy.db"
        shutil.copytree(db_path, db_copy)

        store1 = MnesticRuleSetStore(str(db_path))
        store2 = MnesticRuleSetStore(str(db_copy))

        assert store1.ruleset_hash == store2.ruleset_hash
        # Also verify the clauses are identical
        clauses1 = store1.clauses_for(store1.ruleset_hash)
        clauses2 = store2.clauses_for(store2.ruleset_hash)
        assert [str(c) for c in clauses1] == [str(c) for c in clauses2]

    def test_mnestic_store_with_support_file(self, tmp_path: Path) -> None:
        """A mnestic store with a support file merges base + query_rule/2 facts."""
        pytest.importorskip("mnestic")
        db_path = tmp_path / "support_test.db"
        _create_mnestic_db(
            str(db_path),
            (
                ":create node {"
                "    id: Int, kind: String, parent_id: Int,"
                "    a: Int, b: Int, c: Int, d: Int, e: Int, f: Int, g: Int, h: Int"
                "    => }"
            ),
        )
        support_file = tmp_path / "support.pl"
        support_file.write_text(
            "descendant(A, D) :- node(D, _, A, _,_,_,_,_,_,_,_).\n"
            "descendant(A, D) :- node(M, _, A, _,_,_,_,_,_,_,_), descendant(M, D).\n"
            "nested_fn(O, I) :-\n"
            "    node(O, function_definition, _, _,_,_,_,_,_,_,_),\n"
            "    node(I, function_definition, _, _,_,_,_,_,_,_,_),\n"
            "    descendant(O, I),\n"
            "    O \\= I.\n"
        )
        store = MnesticRuleSetStore(db_path, support=support_file)
        clauses = store.clauses_for(store.ruleset_hash)
        # First clause(s) are base predicates (node/11)
        base_functors = {c.head.functor for c in clauses if isinstance(c.head, Compound) and c.head.functor != "query_rule"}
        assert "node" in base_functors
        # Then query_rule/2 facts
        qr_clauses = [c for c in clauses if isinstance(c.head, Compound) and c.head.functor == "query_rule"]
        assert len(qr_clauses) == 3
        qr_heads = [c.head.args[0].functor for c in qr_clauses if isinstance(c.head.args[0], Compound)]
        assert qr_heads.count("descendant") == 2
        assert qr_heads.count("nested_fn") == 1
        assert clauses.index(qr_clauses[0]) > clauses.index(
            next(c for c in clauses if isinstance(c.head, Compound) and c.head.functor == "node")
        )

    def test_mnestic_store_without_support_unchanged(self, tmp_path: Path) -> None:
        """A mnestic store without support produces only base-predicate clauses."""
        pytest.importorskip("mnestic")
        db_path = tmp_path / "no_support.db"
        _create_mnestic_db(str(db_path), ":create item { code: String => val: Int }")
        store = MnesticRuleSetStore(db_path)
        clauses = store.clauses_for(store.ruleset_hash)
        assert all(
            isinstance(c.head, Compound) and c.head.functor != "query_rule"
            for c in clauses
        )

    def test_mnestic_support_changes_hash(self, tmp_path: Path) -> None:
        """Editing the support file changes the store hash."""
        pytest.importorskip("mnestic")
        db_path1 = tmp_path / "hash_sensitivity1.db"
        db_path2 = tmp_path / "hash_sensitivity2.db"
        _create_mnestic_db(str(db_path1), ":create item { code: String => val: Int }")
        shutil.copytree(db_path1, db_path2)
        support1 = tmp_path / "support1.pl"
        support2 = tmp_path / "support2.pl"
        support1.write_text("foo(X) :- item(X, _).\n")
        support2.write_text("bar(X) :- item(X, _).\n")
        store1 = MnesticRuleSetStore(db_path1, support=support1)
        store2 = MnesticRuleSetStore(db_path2, support=support2)
        assert store1.ruleset_hash != store2.ruleset_hash

    def test_mnestic_support_empty_raises(self, tmp_path: Path) -> None:
        """A present but empty support file raises ValueError."""
        pytest.importorskip("mnestic")
        db_path = tmp_path / "empty_support.db"
        _create_mnestic_db(str(db_path), ":create item { code: String => val: Int }")
        support_file = tmp_path / "empty.pl"
        support_file.write_text("")
        store = MnesticRuleSetStore(db_path, support=support_file)
        with pytest.raises(ValueError, match="contains no clauses"):
            _ = store.ruleset_hash

    def test_mnestic_build_store_from_config_threads_support(self, tmp_path: Path) -> None:
        """build_store_from_config passes support path to MnesticRuleSetStore."""
        pytest.importorskip("mnestic")
        import yaml

        db_path = tmp_path / "config_support.db"
        _create_mnestic_db(str(db_path), ":create item { code: String => val: Int }")
        support_file = tmp_path / "support.pl"
        support_file.write_text("foo(X) :- item(X, _).\n")

        config_dir = tmp_path / ".constraint"
        config_dir.mkdir()
        config_path = config_dir / "config.yaml"
        config_path.write_text(
            yaml.safe_dump(
                {
                    "stores": [
                        {
                            "type": "mnestic",
                            "path": str(db_path),
                            "support": str(support_file),
                        }
                    ],
                    "aliases": {},
                }
            )
        )
        config = Config(config_path)
        store = build_store_from_config(config)
        clauses = store.clauses_for(store.ruleset_hash)
        qr_clauses = [
            c for c in clauses
            if isinstance(c.head, Compound) and c.head.functor == "query_rule"
        ]
        assert len(qr_clauses) == 1



class TestMnesticAdapterRegistry:
    """Tests for the store-name → MnesticAdapter registry."""

    def test_registration_and_lookup(self, tmp_path: Path) -> None:
        """A named MnesticRuleSetStore registers its adapter for lookup."""
        db_path = tmp_path / "registry_test.db"
        _create_mnestic_db(
            str(db_path),
            ":create item { code: String => val: Int }",
        )
        store = MnesticRuleSetStore(str(db_path), name="my_store")
        # Trigger lazy load so registration happens
        _ = store.ruleset_hash

        adapter = lookup("my_store")
        assert adapter is store._adapter

    def test_lookup_unknown_name_raises(self) -> None:
        """lookup on an unregistered name raises KeyError with a clear message."""
        with pytest.raises(KeyError, match="Unknown mnestic store: 'no_such_store'"):
            lookup("no_such_store")

    def test_unnamed_store_does_not_register(self, tmp_path: Path) -> None:
        """A store with name=None does not register anything."""
        db_path = tmp_path / "unnamed.db"
        _create_mnestic_db(
            str(db_path),
            ":create item { code: String => val: Int }",
        )
        store = MnesticRuleSetStore(str(db_path))  # no name
        _ = store.ruleset_hash

        # The registry should still be empty for any name
        with pytest.raises(KeyError, match="Unknown mnestic store"):
            lookup("anything")

# ---------------------------------------------------------------------------
# MnesticAdapter compiled-query parsing tests
# ---------------------------------------------------------------------------


class TestMnesticAdapterQueryCompile:
    """Tests for MnesticAdapter.parse_compiled_query()."""

    def _make_node_db(self, tmp_path: Path) -> str:
        """Create a small rocksdb database with a ``node`` relation.

        Returns the path string.
        """
        db_path = tmp_path / "query_compile.db"
        _create_mnestic_db(
            str(db_path),
            (
                ":create node {"
                "    id: Int"
                "    =>"
                "    kind: String,"
                "    parent_id: Int?,"
                "    start_byte: Int,"
                "    end_byte: Int,"
                "    start_row: Int,"
                "    start_col: Int,"
                "    end_row: Int,"
                "    end_col: Int,"
                "    is_named: Bool,"
                "    text: String,"
                "}"
            ),
        )
        return str(db_path)

    # ------------------------------------------------------------------
    # Success path
    # ------------------------------------------------------------------

    def test_well_formed_compiled_query(self, tmp_path: Path) -> None:
        """A well-formed compiled atom parses and classifies correctly."""
        db_path = self._make_node_db(tmp_path)
        adapter = MnesticAdapter(db_path)

        compiled_atom = (
            "compiled_query("
            "    store(source),"
            "    template(result, [outer_id, name_text, outer_start]),"
            "    derived(["
            "        rule(descendant(anc, desc), [ node([id-desc, parent_id-anc]) ]),"
            "        rule(descendant(anc, desc), [ descendant(anc, mid), node([id-desc, parent_id-mid]) ])"
            "    ]),"
            "    goals(["
            "        node([id-outer_id, kind-'function_definition', start_byte-outer_start]),"
            "        descendant(outer_id, inner_id),"
            "        node([id-inner_id, kind-'function_definition']),"
            "        '!='(outer_id, inner_id),"
            "        node([id-outer_id, kind-'identifier', text-name_text])"
            "    ])"
            ")"
        )
        obligations_atom = "obligations([])"

        result = adapter.parse_compiled_query(compiled_atom, obligations_atom)

        # Store name
        assert result.store_name == "source"

        # Projection columns
        assert result.projection_columns == ["outer_id", "name_text", "outer_start"]

        # Derived rules
        assert len(result.derived_rules) == 2
        assert result.derived_rules[0].head.functor == "descendant"
        assert result.derived_rules[1].head.functor == "descendant"

        # Goals — 5 literals
        assert len(result.goals) == 5

        # Goal 0: base literal node(...)
        assert result.goals[0].kind == "base"
        base0 = result.goals[0].detail
        assert isinstance(base0, BaseLiteral)
        assert base0.relation == "node"
        assert base0.column_bindings == {
            "id": "outer_id",
            "kind": "function_definition",
            "start_byte": "outer_start",
        }

        # Goal 1: derived literal descendant(...)
        assert result.goals[1].kind == "derived"
        derived1 = result.goals[1].detail
        assert isinstance(derived1, DerivedLiteral)
        assert derived1.head_functor == "descendant"
        assert [a.value for a in derived1.args] == ["outer_id", "inner_id"]

        # Goal 2: base literal node(...)
        assert result.goals[2].kind == "base"
        base2 = result.goals[2].detail
        assert isinstance(base2, BaseLiteral)
        assert base2.relation == "node"
        assert base2.column_bindings == {
            "id": "inner_id",
            "kind": "function_definition",
        }

        # Goal 3: guard !=
        assert result.goals[3].kind == "guard"
        guard3 = result.goals[3].detail
        assert isinstance(guard3, Guard)
        assert guard3.functor == "!="
        assert [a.value for a in guard3.args] == ["outer_id", "inner_id"]

        # Goal 4: base literal node(...)
        assert result.goals[4].kind == "base"
        base4 = result.goals[4].detail
        assert isinstance(base4, BaseLiteral)
        assert base4.relation == "node"
        assert base4.column_bindings == {
            "id": "outer_id",
            "kind": "identifier",
            "text": "name_text",
        }

    # ------------------------------------------------------------------
    # Ground-invariant rejection
    # ------------------------------------------------------------------

    def test_rejects_variable_in_base_literal_value(self, tmp_path: Path) -> None:
        """A Variable in a base-literal value position is rejected."""
        db_path = self._make_node_db(tmp_path)
        adapter = MnesticAdapter(db_path)

        # Variable 'X' in a value position
        compiled_atom = (
            "compiled_query("
            "    store(source),"
            "    template(result, [outer_id]),"
            "    derived([]),"
            "    goals(["
            "        node([id-X])"
            "    ])"
            ")"
        )
        obligations_atom = "obligations([])"

        with pytest.raises(ValueError, match="unbound variables"):
            adapter.parse_compiled_query(compiled_atom, obligations_atom)

    def test_rejects_variable_in_derived_body(self, tmp_path: Path) -> None:
        """A Variable in a derived-rule body literal is rejected."""
        db_path = self._make_node_db(tmp_path)
        adapter = MnesticAdapter(db_path)

        compiled_atom = (
            "compiled_query("
            "    store(source),"
            "    template(result, [outer_id]),"
            "    derived(["
            "        rule(p(X), [ q([id-X]) ])"
            "    ]),"
            "    goals(["
            "        p(outer_id)"
            "    ])"
            ")"
        )
        obligations_atom = "obligations([])"

        with pytest.raises(ValueError, match="unbound variables"):
            adapter.parse_compiled_query(compiled_atom, obligations_atom)

    def test_rejects_variable_in_guard_argument(self, tmp_path: Path) -> None:
        """A Variable in a guard argument is rejected."""
        db_path = self._make_node_db(tmp_path)
        adapter = MnesticAdapter(db_path)

        compiled_atom = (
            "compiled_query("
            "    store(source),"
            "    template(result, [outer_id]),"
            "    derived([]),"
            "    goals(["
            "        node([id-outer_id]),"
            "        '!='(outer_id, X)"
            "    ])"
            ")"
        )
        obligations_atom = "obligations([])"

        with pytest.raises(ValueError, match="unbound variables"):
            adapter.parse_compiled_query(compiled_atom, obligations_atom)

    # ------------------------------------------------------------------
    # Missing relation / column rejection
    # ------------------------------------------------------------------

    def test_rejects_missing_relation(self, tmp_path: Path) -> None:
        """A literal naming a relation not in schema or derived heads is rejected."""
        db_path = self._make_node_db(tmp_path)
        adapter = MnesticAdapter(db_path)

        compiled_atom = (
            "compiled_query("
            "    store(source),"
            "    template(result, [x]),"
            "    derived([]),"
            "    goals(["
            "        nonexistent([id-x])"
            "    ])"
            ")"
        )
        obligations_atom = "obligations([])"

        with pytest.raises(ValueError, match="Unknown goal literal 'nonexistent'"):
            adapter.parse_compiled_query(compiled_atom, obligations_atom)

    def test_rejects_missing_column(self, tmp_path: Path) -> None:
        """A base literal with a column not in the schema relation is rejected."""
        db_path = self._make_node_db(tmp_path)
        adapter = MnesticAdapter(db_path)

        compiled_atom = (
            "compiled_query("
            "    store(source),"
            "    template(result, [x]),"
            "    derived([]),"
            "    goals(["
            "        node([id-x, bogus_column-x])"
            "    ])"
            ")"
        )
        obligations_atom = "obligations([])"

        with pytest.raises(ValueError, match="Unknown column 'bogus_column'"):
            adapter.parse_compiled_query(compiled_atom, obligations_atom)

    # ------------------------------------------------------------------
    # Guard-set enforcement
    # ------------------------------------------------------------------

    def test_rejects_unknown_guard_functor(self, tmp_path: Path) -> None:
        """A guard functor outside {!=, column-constant} is rejected."""
        db_path = self._make_node_db(tmp_path)
        adapter = MnesticAdapter(db_path)

        # '<' is not a recognized guard, not a derived head, not a schema relation
        compiled_atom = (
            "compiled_query("
            "    store(source),"
            "    template(result, [x, y]),"
            "    derived([]),"
            "    goals(["
            "        node([id-x]),"
            "        '<'(x, y)"
            "    ])"
            ")"
        )
        obligations_atom = "obligations([])"

        with pytest.raises(ValueError, match="Unknown goal literal"):
            adapter.parse_compiled_query(compiled_atom, obligations_atom)

    def test_accepts_column_constant_match(self, tmp_path: Path) -> None:
        """A column-constant match (constant atom in base-literal value) is accepted."""
        db_path = self._make_node_db(tmp_path)
        adapter = MnesticAdapter(db_path)

        compiled_atom = (
            "compiled_query("
            "    store(source),"
            "    template(result, [outer_id]),"
            "    derived([]),"
            "    goals(["
            "        node([id-outer_id, kind-'function_definition'])"
            "    ])"
            ")"
        )
        obligations_atom = "obligations([])"

        result = adapter.parse_compiled_query(compiled_atom, obligations_atom)
        assert len(result.goals) == 1
        assert result.goals[0].kind == "base"
        base = result.goals[0].detail
        assert isinstance(base, BaseLiteral)
        assert base.column_bindings["kind"] == "function_definition"
