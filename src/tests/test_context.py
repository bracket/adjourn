"""Tests for the ContextStack class in adjourn.context."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from adjourn.context import ContextStack, ContextStackEmptyError


class TestContextStackPushPop:
    """Tests for push and pop behaviour."""

    def test_push_then_pop_is_lifo(self) -> None:
        """pop should return pushed frames last in, first out."""
        stack = ContextStack()
        stack.push("first")
        stack.push("second")
        stack.push("third")

        assert stack.pop() == "third"
        assert stack.pop() == "second"
        assert stack.pop() == "first"
        assert stack.pushed == []

    def test_pop_empty_stack_raises(self) -> None:
        """pop with no pushed frames should raise ContextStackEmptyError."""
        stack = ContextStack()
        with pytest.raises(ContextStackEmptyError):
            stack.pop()

    def test_pop_with_only_pinned_frames_raises_and_keeps_pinned(self) -> None:
        """pop should raise even when pinned frames exist, leaving them intact."""
        stack = ContextStack(pinned=("background-one", "background-two"))

        with pytest.raises(ContextStackEmptyError):
            stack.pop()

        assert stack.pinned == ["background-one", "background-two"]
        assert stack.pushed == []

    def test_pinned_frames_are_never_removed(self) -> None:
        """pop should never remove pinned frames."""
        stack = ContextStack(pinned=("pinned-one", "pinned-two"), pushed=("pushed-one",))

        assert stack.pop() == "pushed-one"

        assert stack.pinned == ["pinned-one", "pinned-two"]
        assert stack.pushed == []


class TestContextStackPersistence:
    """Tests for save and load."""

    def test_save_and_load_round_trip(self, tmp_path: Path) -> None:
        """save then load should restore pinned and pushed in order."""
        path = tmp_path / "context.json"
        stack = ContextStack(pinned=("p1", "p2"), pushed=("a", "b", "c"))

        stack.save(path)
        loaded = ContextStack.load(path)

        assert loaded.pinned == ["p1", "p2"]
        assert loaded.pushed == ["a", "b", "c"]

    def test_save_creates_missing_parent_directory(self, tmp_path: Path) -> None:
        """save should create a missing parent directory."""
        path = tmp_path / "nested" / "deeper" / "context.json"
        stack = ContextStack(pinned=("p",), pushed=("q",))

        stack.save(path)

        assert path.exists()
        loaded = ContextStack.load(path)
        assert loaded.pinned == ["p"]
        assert loaded.pushed == ["q"]

    def test_save_writes_versioned_json_format(self, tmp_path: Path) -> None:
        """save should write the versioned JSON format."""
        path = tmp_path / "context.json"
        ContextStack(pinned=("p",), pushed=("q",)).save(path)

        assert json.loads(path.read_text(encoding="utf-8")) == {
            "version": 1,
            "pinned": ["p"],
            "pushed": ["q"],
        }

    def test_load_missing_path_raises(self, tmp_path: Path) -> None:
        """load on a missing path should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            ContextStack.load(tmp_path / "missing.json")

    def test_load_wrong_version_raises(self, tmp_path: Path) -> None:
        """load on a file with version 2 should raise ValueError."""
        path = tmp_path / "context.json"
        path.write_text(
            json.dumps({"version": 2, "pinned": ["p"], "pushed": ["q"]}),
            encoding="utf-8",
        )

        with pytest.raises(ValueError):
            ContextStack.load(path)


class TestContextStackRender:
    """Tests for render."""

    def test_render_with_only_state(self) -> None:
        """render with no frames should produce only the Session state section."""
        stack = ContextStack()

        expected = (
            "## Session state\n"
            "\n"
            '{\n  "key": "value"\n}'
        )

        assert stack.render({"key": "value"}) == expected

    def test_render_with_pinned_and_pushed(self) -> None:
        """render should produce the three sections in order with blank-line separation."""
        stack = ContextStack(pinned=("p1", "p2"), pushed=("a", "b", "c"))

        expected = (
            "## Background\n"
            "\n"
            "p1\n"
            "\n"
            "p2\n"
            "\n"
            "## Your context stack (oldest first; pop_context removes the last entry)\n"
            "\n"
            "a\n"
            "\n"
            "b\n"
            "\n"
            "c\n"
            "\n"
            "## Session state\n"
            "\n"
            '{\n  "key": "value"\n}'
        )

        assert stack.render({"key": "value"}) == expected

    def test_render_omits_background_without_pinned(self) -> None:
        """render should omit the Background section when there are no pinned frames."""
        stack = ContextStack(pushed=("a",))

        expected = (
            "## Your context stack (oldest first; pop_context removes the last entry)\n"
            "\n"
            "a\n"
            "\n"
            "## Session state\n"
            "\n"
            '{\n  "key": "value"\n}'
        )

        assert stack.render({"key": "value"}) == expected

    def test_render_omits_context_stack_without_pushed(self) -> None:
        """render should omit the context stack section when there are no pushed frames."""
        stack = ContextStack(pinned=("p1",))

        expected = (
            "## Background\n"
            "\n"
            "p1\n"
            "\n"
            "## Session state\n"
            "\n"
            '{\n  "key": "value"\n}'
        )

        assert stack.render({"key": "value"}) == expected
