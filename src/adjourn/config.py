from pathlib import Path
from typing import Any

import yaml


class _AppendFileStoreResult(dict):
    """Store config dict returned by :meth:`Config.append_file_store`.

    Behaves as a plain mapping of the store configuration while also
    carrying a ``changed`` flag so callers can tell whether the config
    file was modified (``True``) or the store was already configured
    (``False``).
    """

    def __init__(self, store_config: dict[str, Any], changed: bool) -> None:
        super().__init__(store_config)
        self.changed = changed


class Config:
    """Read and validate a project rule-store configuration file."""

    def __init__(self, path: str | Path, create: bool = False) -> None:
        """Initialize the config from *path*.

        Args:
            path: Path to the YAML config file.
            create: When True, create the config file (with an empty
                ``stores`` list) if it does not already exist.  Existing
                files are never rewritten.

        Raises:
            FileNotFoundError: If *path* does not exist and *create* is
                False.
            ValueError: If the config file at *path* is invalid.
        """
        self.path = Path(path)
        if create:
            self._create_if_missing()
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
    def foreign_plugins(self) -> list[str]:
        """Return the list of foreign plugin module names, or [] if absent."""
        foreign = self._data.get("foreign") or {}
        return list(foreign.get("plugins", []))

    @property
    def base_dir(self) -> Path:
        """Return the base directory for relative ruleset file paths."""
        if self.path.parent.name == ".adjourn":
            return self.path.parent.parent
        return self.path.parent

    def alias_hash(self, name: str) -> str:
        """Resolve a configured alias to its ruleset hash."""
        try:
            return self._data["aliases"][name]
        except KeyError as exc:
            raise ValueError(f"Unknown ruleset alias: {name}") from exc

    def _create_if_missing(self) -> None:
        """Create the config file with an empty ``stores`` list if missing.

        Parent directories are created as needed.  When the file is created,
        ``self._data`` is refreshed from disk so property reads reflect the
        newly created (empty) configuration.
        """
        if self.path.exists():
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            yaml.safe_dump({"stores": []}, default_flow_style=False),
            encoding="utf-8",
        )
        self._data = self._load()

    def append_file_store(self, path: str) -> _AppendFileStoreResult:
        """Append a ``file`` store entry for *path* and persist the config.

        The store name is derived from ``Path(path).stem`` and auto-suffixed
        (``-2``, ``-3``, ...) until it is unique among existing store names
        and alias keys.  If a store with the identical ``path`` string is
        already configured, the existing entry is returned with
        ``changed`` set to ``False`` and the file is not rewritten.

        Args:
            path: The ruleset file path, stored verbatim.

        Returns:
            The added (or already existing) store configuration dict.  The
            returned dict carries a ``changed`` attribute that is ``True``
            when the config file was modified and ``False`` when the store
            was already configured (idempotent no-op).

        Raises:
            ValueError: If a store name cannot be derived from *path*.
            OSError: If the config file cannot be written.
        """
        self._create_if_missing()

        name = Path(path).stem
        if not name:
            raise ValueError(f"Cannot derive a store name from path: {path!r}")

        stores = self._data.setdefault("stores", [])
        for store in stores:
            if store.get("path") == path:
                return _AppendFileStoreResult(store, False)

        used_names = {
            store["name"] for store in stores if "name" in store
        }
        used_names.update(self._data.setdefault("aliases", {}).keys())

        derived_name = name
        suffix = 2
        while derived_name in used_names:
            derived_name = f"{name}-{suffix}"
            suffix += 1

        store_config: dict[str, Any] = {
            "type": "file",
            "path": path,
            "prolog": "wrapped",
            "name": derived_name,
        }
        stores.append(store_config)
        self._write()
        return _AppendFileStoreResult(store_config, True)

    def _write(self) -> None:
        """Persist ``self._data`` to ``self.path`` as YAML."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            yaml.safe_dump(self._data, default_flow_style=False),
            encoding="utf-8",
        )

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            raise FileNotFoundError(f"Config file not found: {self.path}")

        with self.path.open(encoding="utf-8") as handle:
            raw_data = yaml.safe_load(handle) or {}

        if not isinstance(raw_data, dict):
            raise ValueError(f"Invalid config file {self.path}: expected a mapping")
        if "stores" not in raw_data:
            raise ValueError(f"Invalid config file {self.path}: missing 'stores'")

        stores = raw_data["stores"]
        aliases = raw_data.get("aliases", { })

        if not isinstance(stores, list):
            raise ValueError(f"Invalid config file {self.path}: 'stores' must be a list")
        if not isinstance(aliases, dict):
            raise ValueError(f"Invalid config file {self.path}: 'aliases' must be a mapping")

        validated_aliases: dict[str, str] = {}
        for alias_name, ruleset_hash in aliases.items():
            if not isinstance(alias_name, str):
                raise ValueError(
                    f"Invalid config file {self.path}: alias names must be strings"
                )
            if alias_name.startswith("@"):
                raise ValueError(
                    f"Invalid config file {self.path}: alias '{alias_name}' cannot start with '@'"
                )
            if not isinstance(ruleset_hash, str):
                raise ValueError(
                    f"Invalid config file {self.path}: alias '{alias_name}' must map to a string hash"
                )
            validated_aliases[alias_name] = ruleset_hash

        validated_stores: list[dict[str, Any]] = []
        store_names: set[str] = set()
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
            store_type = store["type"]
            if store_type == "mnestic":
                validated_store: dict[str, Any] = {
                    "type": store_type,
                    "path": store["path"],
                }
                if "support" in store:
                    support = store["support"]
                    if not isinstance(support, str):
                        raise ValueError(
                            f"Invalid config file {self.path}: store #{index} support must be a string"
                        )
                    validated_store["support"] = support
            else:
                prolog_mode = store.get("prolog", "wrapped")
                if prolog_mode not in {"wrapped", "strict"}:
                    raise ValueError(
                        f"Invalid config file {self.path}: store #{index} 'prolog' must be 'wrapped' or 'strict'"
                    )
                validated_store = {
                    "type": store_type,
                    "path": store["path"],
                    "prolog": prolog_mode,
                }
            if "name" in store:
                store_name = store["name"]
                if not isinstance(store_name, str):
                    raise ValueError(
                        f"Invalid config file {self.path}: store #{index} name must be a string"
                    )
                if store_name.startswith("@"):
                    raise ValueError(
                        f"Invalid config file {self.path}: store #{index} name cannot start with '@'"
                    )
                if store_name in store_names:
                    raise ValueError(
                        f"Invalid config file {self.path}: duplicate store name '{store_name}'"
                    )
                if store_name in validated_aliases:
                    raise ValueError(
                        f"Invalid config file {self.path}: store name '{store_name}' collides with alias"
                    )
                store_names.add(store_name)
                validated_store["name"] = store_name
            validated_stores.append(validated_store)

        foreign = raw_data.get("foreign")
        if foreign is not None:
            if not isinstance(foreign, dict):
                raise ValueError(
                    f"Invalid config file {self.path}: 'foreign' must be a mapping"
                )
            plugins = foreign.get("plugins")
            if plugins is not None:
                if not isinstance(plugins, list):
                    raise ValueError(
                        f"Invalid config file {self.path}: 'foreign.plugins' must be a list"
                    )
                for i, item in enumerate(plugins):
                    if not isinstance(item, str):
                        raise ValueError(
                            f"Invalid config file {self.path}: 'foreign.plugins[{i}]' must be a string"
                        )

        return {
            "stores": validated_stores,
            "aliases": validated_aliases,
            "foreign": foreign if foreign is not None else {},
        }
