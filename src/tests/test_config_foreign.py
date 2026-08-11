"""Tests for Config.foreign_plugins and load_foreign_plugins."""

from pathlib import Path

import pytest
import yaml

from constraint.config import Config
from constraint.constraint_foreign import _registry, load_foreign_plugins


def _write_config(tmp_path: Path, data: dict) -> Path:
    """Write a minimal valid config and return its path."""
    config_dir = tmp_path / ".constraint"
    config_dir.mkdir()
    config_path = config_dir / "config.yaml"
    base = {"stores": [{"type": "file", "path": "rules.pl"}]}
    base.update(data)
    config_path.write_text(yaml.safe_dump(base))
    return config_path


class TestForeignPluginsProperty:
    """Tests for Config.foreign_plugins."""

    def test_no_foreign_block_returns_empty(self, tmp_path: Path) -> None:
        path = _write_config(tmp_path, {})
        config = Config(path)
        assert config.foreign_plugins == []

    def test_foreign_without_plugins_returns_empty(self, tmp_path: Path) -> None:
        path = _write_config(tmp_path, {"foreign": {}})
        config = Config(path)
        assert config.foreign_plugins == []

    def test_foreign_plugins_empty_list(self, tmp_path: Path) -> None:
        path = _write_config(tmp_path, {"foreign": {"plugins": []}})
        config = Config(path)
        assert config.foreign_plugins == []

    def test_foreign_plugins_populated(self, tmp_path: Path) -> None:
        path = _write_config(tmp_path, {"foreign": {"plugins": ["os", "sys"]}})
        config = Config(path)
        assert config.foreign_plugins == ["os", "sys"]

    def test_foreign_not_mapping_raises(self, tmp_path: Path) -> None:
        path = _write_config(tmp_path, {"foreign": "bad"})
        with pytest.raises(ValueError, match="'foreign' must be a mapping"):
            Config(path)

    def test_foreign_plugins_not_list_raises(self, tmp_path: Path) -> None:
        path = _write_config(tmp_path, {"foreign": {"plugins": "bad"}})
        with pytest.raises(ValueError, match="'foreign.plugins' must be a list"):
            Config(path)

    def test_foreign_plugins_non_string_element_raises(self, tmp_path: Path) -> None:
        path = _write_config(tmp_path, {"foreign": {"plugins": [42]}})
        with pytest.raises(ValueError, match="'foreign.plugins\\[0\\]' must be a string"):
            Config(path)


class TestLoadForeignPlugins:
    """Tests for load_foreign_plugins."""

    def test_unimportable_module_raises(self) -> None:
        with pytest.raises(ImportError):
            load_foreign_plugins(["_constraint_no_such_module_xyz"])

    def test_valid_module_imported(self) -> None:
        """Importing a module with @register makes its callout dispatchable."""
        # Use the built-in 'os' module (no side effects); verify no error.
        load_foreign_plugins(["os"])

    def test_registered_callout_dispatchable_after_load(self, tmp_path: Path) -> None:
        """A @register callout in a dynamically-imported module enters the registry."""
        import importlib.util
        import sys

        mod_name = "_test_foreign_plugin_xyz"
        mod_path = tmp_path / f"{mod_name}.py"
        mod_path.write_text(
            "from constraint.constraint_foreign import register\n"
            "@register('_test_fn_xyz')\n"
            "def _fn(arg): return 'ok'\n"
        )
        spec = importlib.util.spec_from_file_location(mod_name, mod_path)
        assert spec is not None
        # Remove from sys.modules if present so we can reload cleanly.
        sys.modules.pop(mod_name, None)
        # Add parent dir to sys.path temporarily
        import sys as _sys
        _sys.path.insert(0, str(tmp_path))
        try:
            load_foreign_plugins([mod_name])
            assert "_test_fn_xyz" in _registry
        finally:
            _sys.path.pop(0)
            sys.modules.pop(mod_name, None)
            _registry.pop("_test_fn_xyz", None)
