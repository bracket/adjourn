"""Tests for the state storage seam (adjourn.state_store)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from adjourn.state_store import JsonFileStateStore, StateStore


class TestStateStoreABC:
    """Verify the ABC contract."""

    def test_abc_cannot_be_instantiated(self) -> None:
        with pytest.raises(TypeError):
            StateStore()  # type: ignore[abstract]


class TestJsonFileStateStore:
    """Tests for the JSON-file-backed implementation."""

    def test_round_trip(self, tmp_path: Path) -> None:
        store = JsonFileStateStore(root=tmp_path)
        state = {"version": 1, "original_goal": "p(X)", "branches": [], "status": "solved"}

        store.store_state("foo", state)
        loaded = store.load_state("foo")

        assert loaded == state

    def test_written_file_location(self, tmp_path: Path) -> None:
        store = JsonFileStateStore(root=tmp_path)
        state = {"key": "value"}

        store.store_state("foo", state)

        expected = tmp_path / "states" / "state_foo.json"
        assert expected.is_file()
        assert json.loads(expected.read_text(encoding="utf-8")) == state

    def test_last_write_wins(self, tmp_path: Path) -> None:
        store = JsonFileStateStore(root=tmp_path)
        first = {"value": 1}
        second = {"value": 2}

        store.store_state("foo", first)
        store.store_state("foo", second)
        loaded = store.load_state("foo")

        assert loaded == second

    def test_load_missing_raises(self, tmp_path: Path) -> None:
        store = JsonFileStateStore(root=tmp_path)

        with pytest.raises(FileNotFoundError):
            store.load_state("nonexistent")

    def test_custom_root(self, tmp_path: Path) -> None:
        custom_root = tmp_path / "custom_root"
        store = JsonFileStateStore(root=custom_root)
        state = {"a": 1}

        store.store_state("bar", state)
        loaded = store.load_state("bar")

        assert loaded == state
        assert (custom_root / "states" / "state_bar.json").is_file()

    def test_multiple_names_independent(self, tmp_path: Path) -> None:
        store = JsonFileStateStore(root=tmp_path)
        store.store_state("alpha", {"data": "first"})
        store.store_state("beta", {"data": "second"})

        assert store.load_state("alpha") == {"data": "first"}
        assert store.load_state("beta") == {"data": "second"}
