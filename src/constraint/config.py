from pathlib import Path
from typing import Any

import yaml


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
                prolog_mode = store.get("prolog", "constraint")
                if prolog_mode not in {"constraint", "strict"}:
                    raise ValueError(
                        f"Invalid config file {self.path}: store #{index} 'prolog' must be 'constraint' or 'strict'"
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

        return {"stores": validated_stores, "aliases": validated_aliases}
