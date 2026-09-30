"""Tests for adjourn.prompts (shared LLM-facing usage text)."""

from __future__ import annotations

import pytest

from adjourn.prompts import read_prompt, render_usage


def test_empty_preamble_returns_core() -> None:
    assert render_usage() == read_prompt("usage.md")
    assert render_usage("") == read_prompt("usage.md")


def test_whitespace_preamble_returns_core() -> None:
    assert render_usage("  \n\t ") == read_prompt("usage.md")


def test_preamble_joined_with_blank_line() -> None:
    assert render_usage("  Preamble text.\n") == "Preamble text.\n\n" + read_prompt("usage.md")


@pytest.mark.parametrize("tool", ["adjourn_init", "adjourn_resume", "adjourn_add_rules"])
def test_core_names_no_mcp_tools(tool: str) -> None:
    assert tool not in read_prompt("usage.md")


def test_read_prompt_mcp_preamble() -> None:
    assert "adjourn_init" in read_prompt("mcp_preamble.md")


def test_read_prompt_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        read_prompt("no_such_prompt.md")
