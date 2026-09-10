"""Tests for the Config write seam (append_file_store / _create_if_missing)."""

from pathlib import Path

import pytest
import yaml

from constraint.config import Config


def _write_config(tmp_path: Path, data: dict) -> Path:
    """Write a config file and return its path."""
    config_dir = tmp_path / ".constraint"
    config_dir.mkdir()
    config_path = config_dir / "config.yaml"
    config_path.write_text(yaml.safe_dump(data))
    return config_path


def _config_for_missing_path(path: Path) -> Config:
    """Build a Config instance for a config file that does not exist yet."""
    config = Config.__new__(Config)
    config.path = Path(path)
    config._data = {"stores": [], "aliases": {}, "foreign": {}}
    return config


class TestCreateIfMissing:
    """Tests for Config._create_if_missing."""

    def test_creates_file_with_empty_stores(self, tmp_path: Path) -> None:
        config_path = tmp_path / ".constraint" / "config.yaml"
        config = _config_for_missing_path(config_path)
        config._create_if_missing()
        assert config_path.exists()
        assert yaml.safe_load(config_path.read_text()) == {"stores": []}
        assert config.store_configs == []

    def test_existing_file_is_left_untouched(self, tmp_path: Path) -> None:
        config_path = _write_config(
            tmp_path, {"stores": [{"type": "file", "path": "a.pl"}]}
        )
        original = config_path.read_text()
        config = Config(config_path)
        config._create_if_missing()
        assert config_path.read_text() == original
        assert len(config.store_configs) == 1


class TestAppendFileStore:
    """Tests for Config.append_file_store."""

    def test_appends_file_store_and_round_trips(self, tmp_path: Path) -> None:
        config_path = _write_config(tmp_path, {"stores": [], "aliases": {}})
        config = Config(config_path)

        result = config.append_file_store("rules.pl")

        assert result.changed is True
        assert result == {
            "type": "file",
            "path": "rules.pl",
            "prolog": "constraint",
            "name": "rules",
        }
        assert isinstance(result, dict)
        # In-memory state reflects the addition immediately.
        assert config.store_configs == [dict(result)]
        # Round-trip: a fresh Config loads the appended store.
        reloaded = Config(config_path)
        assert reloaded.store_configs == [dict(result)]

    def test_creates_missing_config_file(self, tmp_path: Path) -> None:
        config_path = tmp_path / ".constraint" / "config.yaml"
        config = _config_for_missing_path(config_path)

        result = config.append_file_store("rules.pl")

        assert result.changed is True
        assert config_path.exists()
        assert result["name"] == "rules"
        reloaded = Config(config_path)
        assert reloaded.store_configs == [dict(result)]

    def test_duplicate_path_is_idempotent(self, tmp_path: Path) -> None:
        config_path = _write_config(tmp_path, {"stores": [], "aliases": {}})
        config = Config(config_path)

        first = config.append_file_store("rules.pl")
        before = config_path.read_text()
        second = config.append_file_store("rules.pl")

        assert first.changed is True
        assert second.changed is False
        assert second == first
        # File must not be rewritten on a duplicate.
        assert config_path.read_text() == before
        assert len(Config(config_path).store_configs) == 1

    def test_name_collision_with_store_name_auto_suffixes(
        self, tmp_path: Path
    ) -> None:
        config_path = _write_config(
            tmp_path,
            {
                "stores": [
                    {"type": "file", "path": "other.pl", "name": "rules"}
                ],
                "aliases": {},
            },
        )
        config = Config(config_path)

        result = config.append_file_store("rules.pl")

        assert result.changed is True
        assert result["name"] == "rules-2"
        assert Config(config_path).store_configs[-1]["name"] == "rules-2"

    def test_name_collision_with_alias_key_auto_suffixes(
        self, tmp_path: Path
    ) -> None:
        config_path = _write_config(
            tmp_path,
            {
                "stores": [],
                "aliases": {"rules": "abc123"},
            },
        )
        config = Config(config_path)

        result = config.append_file_store("rules.pl")

        assert result.changed is True
        assert result["name"] == "rules-2"
        assert Config(config_path).store_configs[-1]["name"] == "rules-2"

    def test_auto_suffix_skips_existing_suffixed_names(self, tmp_path: Path) -> None:
        config_path = _write_config(
            tmp_path,
            {
                "stores": [
                    {"type": "file", "path": "a.pl", "name": "rules"},
                    {"type": "file", "path": "b.pl", "name": "rules-2"},
                ],
                "aliases": {},
            },
        )
        config = Config(config_path)

        result = config.append_file_store("rules.pl")

        assert result["name"] == "rules-3"

    def test_empty_stem_raises_value_error(self, tmp_path: Path) -> None:
        config_path = _write_config(tmp_path, {"stores": [], "aliases": {}})
        config = Config(config_path)

        with pytest.raises(ValueError, match="derive a store name"):
            config.append_file_store("")

    def test_preserves_aliases_through_rewrite(self, tmp_path: Path) -> None:
        config_path = _write_config(
            tmp_path,
            {
                "stores": [],
                "aliases": {"main": "deadbeef"},
            },
        )
        config = Config(config_path)

        config.append_file_store("rules.pl")

        reloaded = Config(config_path)
        assert reloaded.aliases == {"main": "deadbeef"}

    def test_preserves_foreign_plugins_through_rewrite(
        self, tmp_path: Path
    ) -> None:
        config_path = _write_config(
            tmp_path,
            {
                "stores": [],
                "aliases": {},
                "foreign": {"plugins": ["os", "sys"]},
            },
        )
        config = Config(config_path)

        config.append_file_store("rules.pl")

        reloaded = Config(config_path)
        assert reloaded.foreign_plugins == ["os", "sys"]

    def test_write_failure_raises_oserror(self, tmp_path: Path) -> None:
        # Point the config at a path whose parent is a regular file so the
        # parent-directory creation / write fails with an OSError.
        blocker = tmp_path / "blocker"
        blocker.write_text("not a directory")
        config_path = blocker / "config.yaml"
        config = _config_for_missing_path(config_path)

        with pytest.raises(OSError):
            config.append_file_store("rules.pl")

    def test_append_file_store_verbatim_path(self, tmp_path: Path) -> None:
        """The path string must be stored exactly as given, not normalized."""
        config_path = _write_config(tmp_path, {"stores": [], "aliases": {}})
        config = Config(config_path)

        result = config.append_file_store("./rules/rel.pl")

        assert result.changed is True
        assert result["path"] == "./rules/rel.pl"
        # The on-disk YAML must contain the verbatim path too.
        assert "./rules/rel.pl" in config_path.read_text()
        reloaded = Config(config_path)
        assert reloaded.store_configs[0]["path"] == "./rules/rel.pl"

    def test_append_file_store_path_with_spaces_and_special_chars(
        self, tmp_path: Path
    ) -> None:
        """Paths with spaces and special characters are preserved and named."""
        config_path = _write_config(tmp_path, {"stores": [], "aliases": {}})
        config = Config(config_path)

        result = config.append_file_store("my rules/foo bar (1).pl")

        assert result.changed is True
        assert result["path"] == "my rules/foo bar (1).pl"
        assert result["name"] == "foo bar (1)"
        reloaded = Config(config_path)
        assert reloaded.store_configs[0]["path"] == "my rules/foo bar (1).pl"
        assert reloaded.store_configs[0]["name"] == "foo bar (1)"
