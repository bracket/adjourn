"""Unit tests for constraint.state (init_state, set_resume_hash, resolve_ruleset_hash)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from constraint.config import Config
from constraint.state import init_state, resolve_ruleset_hash, set_resume_hash
from constraint.store import (
    AggregateRuleSetStore,
    FileRuleSetStore,
    build_store_from_config,
)

NONEMPTY_RULESET = "rule(test_fixture_placeholder, true).\n"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_config(
    tmp_path: Path,
    rules: dict[str, str],
    *,
    aliases: dict[str, str] | None = None,
    store_names: dict[str, str] | None = None,
) -> Path:
    """Create rules files plus a matching config file."""
    config_dir = tmp_path / ".constraint"
    rules_dir = tmp_path / "rules"
    config_dir.mkdir()
    rules_dir.mkdir()

    stores: list[dict[str, str]] = []
    computed_aliases: dict[str, str] = {}
    for name, content in rules.items():
        rules_path = rules_dir / f"{name}.pl"
        rules_path.write_text(content)
        store = FileRuleSetStore(rules_path)
        ruleset_hash = store.known_rulesets()[0]
        store_config: dict[str, str] = {"type": "file", "path": str(Path("rules") / rules_path.name)}
        if store_names is not None and name in store_names:
            store_config["name"] = store_names[name]
        stores.append(store_config)
        computed_aliases[name] = ruleset_hash

    config_path = config_dir / "config.yaml"
    if aliases is None:
        aliases = computed_aliases
    config_path.write_text(yaml.safe_dump({"stores": stores, "aliases": aliases}))
    return config_path


def _build_store_and_config(config_path: Path) -> tuple[AggregateRuleSetStore, Config]:
    """Build store and config from a config path."""
    config = Config(config_path)
    store = build_store_from_config(config)
    return store, config


# ---------------------------------------------------------------------------
# Tests for resolve_ruleset_hash
# ---------------------------------------------------------------------------


class TestResolveRulesetHash:
    """Tests for resolve_ruleset_hash resolution branches."""

    def test_resolves_system_top_alias(self, tmp_path: Path) -> None:
        config_path = _write_config(
            tmp_path,
            {"first_rules": "p(a).\n", "second_rules": "q(b).\n"},
            aliases={},
        )
        store, config = _build_store_and_config(config_path)
        h = resolve_ruleset_hash("@top", store, config)
        assert h == store.ruleset_hash

    def test_resolves_system_first_alias(self, tmp_path: Path) -> None:
        config_path = _write_config(
            tmp_path,
            {"first_rules": "p(a).\n", "second_rules": "q(b).\n"},
            aliases={},
        )
        store, config = _build_store_and_config(config_path)
        h = resolve_ruleset_hash("@first", store, config)
        first_hash = FileRuleSetStore(tmp_path / "rules" / "first_rules.pl").known_rulesets()[0]
        assert h == first_hash

    def test_resolves_per_store_name(self, tmp_path: Path) -> None:
        config_path = _write_config(
            tmp_path,
            {"test_rules": NONEMPTY_RULESET},
            aliases={},
            store_names={"test_rules": "named-rules"},
        )
        store, config = _build_store_and_config(config_path)
        h = resolve_ruleset_hash("named-rules", store, config)
        expected = FileRuleSetStore(tmp_path / "rules" / "test_rules.pl").known_rulesets()[0]
        assert h == expected

    def test_resolves_config_alias(self, tmp_path: Path) -> None:
        config_path = _write_config(
            tmp_path,
            {"test_rules": NONEMPTY_RULESET},
            aliases={"my-alias": "placeholder"},
        )
        store, config = _build_store_and_config(config_path)
        # The alias "my-alias" maps to "placeholder" which is not a real hash.
        # We need a real hash for the alias to work.
        # Let's use the actual hash.
        actual_hash = FileRuleSetStore(tmp_path / "rules" / "test_rules.pl").known_rulesets()[0]
        # Rewrite config with the real hash
        config_path.write_text(
            yaml.safe_dump(
                {
                    "stores": [{"type": "file", "path": "rules/test_rules.pl"}],
                    "aliases": {"my-alias": actual_hash},
                }
            )
        )
        store, config = _build_store_and_config(config_path)
        h = resolve_ruleset_hash("my-alias", store, config)
        assert h == actual_hash

    def test_resolves_raw_hash(self, tmp_path: Path) -> None:
        config_path = _write_config(
            tmp_path,
            {"test_rules": NONEMPTY_RULESET},
            aliases={},
        )
        store, config = _build_store_and_config(config_path)
        actual_hash = FileRuleSetStore(tmp_path / "rules" / "test_rules.pl").known_rulesets()[0]
        h = resolve_ruleset_hash(actual_hash, store, config)
        assert h == actual_hash

    def test_unknown_ruleset_raises_value_error(self, tmp_path: Path) -> None:
        config_path = _write_config(
            tmp_path,
            {"test_rules": NONEMPTY_RULESET},
            aliases={},
        )
        store, config = _build_store_and_config(config_path)
        with pytest.raises(ValueError, match="Unknown ruleset"):
            resolve_ruleset_hash("nonexistent", store, config)

    def test_unknown_system_alias_raises_value_error(self, tmp_path: Path) -> None:
        config_path = _write_config(
            tmp_path,
            {"test_rules": NONEMPTY_RULESET},
            aliases={},
        )
        store, config = _build_store_and_config(config_path)
        with pytest.raises(ValueError, match="Unknown system alias"):
            resolve_ruleset_hash("@unknown", store, config)

    def test_first_alias_with_no_stores_raises(self, tmp_path: Path) -> None:
        config_dir = tmp_path / ".constraint"
        config_dir.mkdir()
        config_path = config_dir / "config.yaml"
        config_path.write_text(yaml.safe_dump({"stores": [], "aliases": {}}))
        store, config = _build_store_and_config(config_path)
        with pytest.raises(ValueError, match="@first"):
            resolve_ruleset_hash("@first", store, config)


# ---------------------------------------------------------------------------
# Tests for init_state
# ---------------------------------------------------------------------------


class TestInitState:
    """Tests for init_state."""

    def test_returns_v0_state(self, tmp_path: Path) -> None:
        config_path = _write_config(tmp_path, {"test_rules": NONEMPTY_RULESET})
        store, config = _build_store_and_config(config_path)
        state = init_state("true", "test_rules", store, config)
        assert state["version"] == 0
        assert state["original_goal"] == "true"
        assert state["branches"] == [{"goals": ["true"]}]
        assert state["status"] == "running"

    def test_ruleset_hash_and_resume_hash_equal(self, tmp_path: Path) -> None:
        config_path = _write_config(tmp_path, {"test_rules": NONEMPTY_RULESET})
        store, config = _build_store_and_config(config_path)
        state = init_state("true", "test_rules", store, config)
        assert "ruleset_hash" in state
        assert "resume_hash" in state
        assert state["ruleset_hash"] == state["resume_hash"]

    def test_hash_matches_resolved_hash(self, tmp_path: Path) -> None:
        config_path = _write_config(tmp_path, {"test_rules": NONEMPTY_RULESET})
        store, config = _build_store_and_config(config_path)
        state = init_state("true", "test_rules", store, config)
        expected = resolve_ruleset_hash("test_rules", store, config)
        assert state["ruleset_hash"] == expected
        assert state["resume_hash"] == expected

    def test_uses_system_alias(self, tmp_path: Path) -> None:
        config_path = _write_config(
            tmp_path,
            {"first_rules": "p(a).\n"},
            aliases={},
        )
        store, config = _build_store_and_config(config_path)
        state = init_state("true", "@top", store, config)
        assert state["ruleset_hash"] == store.ruleset_hash

    def test_unknown_ruleset_raises(self, tmp_path: Path) -> None:
        config_path = _write_config(tmp_path, {"test_rules": NONEMPTY_RULESET})
        store, config = _build_store_and_config(config_path)
        with pytest.raises(ValueError, match="Unknown ruleset"):
            init_state("true", "nonexistent", store, config)


# ---------------------------------------------------------------------------
# Tests for set_resume_hash
# ---------------------------------------------------------------------------


class TestSetResumeHash:
    """Tests for set_resume_hash."""

    def test_sets_resume_hash(self, tmp_path: Path) -> None:
        config_path = _write_config(
            tmp_path,
            {"first_rules": "p(a).\n", "second_rules": "q(b).\n"},
            aliases={},
        )
        store, config = _build_store_and_config(config_path)
        state = {"version": 0, "original_goal": "true", "branches": [], "status": "running"}
        new_state = set_resume_hash(state, "@first", store, config)
        first_hash = FileRuleSetStore(tmp_path / "rules" / "first_rules.pl").known_rulesets()[0]
        assert new_state["resume_hash"] == first_hash
        assert new_state is state  # modified in place

    def test_blind_set_no_ruleset_hash(self, tmp_path: Path) -> None:
        """set_resume_hash must succeed even when state has no ruleset_hash."""
        config_path = _write_config(tmp_path, {"test_rules": NONEMPTY_RULESET})
        store, config = _build_store_and_config(config_path)
        state = {"version": 0, "original_goal": "true", "branches": [], "status": "running"}
        # No ruleset_hash in state
        new_state = set_resume_hash(state, "test_rules", store, config)
        assert "resume_hash" in new_state
        assert "ruleset_hash" not in new_state

    def test_preserves_existing_keys(self, tmp_path: Path) -> None:
        config_path = _write_config(tmp_path, {"test_rules": NONEMPTY_RULESET})
        store, config = _build_store_and_config(config_path)
        state = {
            "version": 0,
            "original_goal": "true",
            "branches": [],
            "status": "running",
            "ruleset_hash": "old_hash",
        }
        new_state = set_resume_hash(state, "test_rules", store, config)
        assert new_state["ruleset_hash"] == "old_hash"
        assert new_state["resume_hash"] != "old_hash"

    def test_unknown_ruleset_raises(self, tmp_path: Path) -> None:
        config_path = _write_config(tmp_path, {"test_rules": NONEMPTY_RULESET})
        store, config = _build_store_and_config(config_path)
        state = {"version": 0, "original_goal": "true", "branches": [], "status": "running"}
        with pytest.raises(ValueError, match="Unknown ruleset"):
            set_resume_hash(state, "nonexistent", store, config)
