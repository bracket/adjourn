"""Tests for the adjourn MCP server tools."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import yaml

mcp = pytest.importorskip("adjourn.mcp")

from adjourn.mcp import (
    adjourn_add_rules,
    adjourn_init,
    adjourn_resume,
)
from adjourn.store import FileRuleSetStore
from adjourn.tools import Workspace

NONEMPTY_RULESET = "rule(test_fixture_placeholder, true).\n"


def _write_config(
    tmp_path: Path,
    rules: dict[str, str],
    *,
    aliases: dict[str, str] | None = None,
    store_names: dict[str, str] | None = None,
    prolog_modes: dict[str, str] | None = None,
) -> Path:
    """Create rules files plus a matching config file."""
    config_dir = tmp_path / ".adjourn"
    rules_dir = tmp_path / "rules"
    config_dir.mkdir()
    rules_dir.mkdir()

    stores: list[dict[str, str]] = []
    computed_aliases: dict[str, str] = {}
    for name, content in rules.items():
        rules_path = rules_dir / f"{name}.pl"
        rules_path.write_text(content)
        prolog_mode = prolog_modes.get(name, "wrapped") if prolog_modes else "wrapped"
        store = FileRuleSetStore(rules_path, prolog=prolog_mode)
        ruleset_hash = store.known_rulesets()[0]
        store_config = {"type": "file", "path": str(Path("rules") / rules_path.name)}
        if store_names is not None and name in store_names:
            store_config["name"] = store_names[name]
        store_config["prolog"] = prolog_mode
        stores.append(store_config)
        computed_aliases[name] = ruleset_hash

    config_path = config_dir / "config.yaml"
    if aliases is None:
        aliases = computed_aliases
    config_path.write_text(yaml.safe_dump({"stores": stores, "aliases": aliases}))
    return config_path


class TestMCPModuleSurface:
    """Tests for the MCP module surface and tool registration."""

    def test_tools_are_registered(self) -> None:
        """The three tools should be exposed as MCP tools."""
        tools = asyncio.run(mcp.mcp.list_tools())
        tool_names = {tool.name for tool in tools}
        assert "adjourn_init" in tool_names
        assert "adjourn_resume" in tool_names
        assert "adjourn_add_rules" in tool_names

    def test_module_workspace_is_workspace(self) -> None:
        """adjourn.mcp.workspace should be a Workspace instance."""
        import adjourn.mcp as mcp_mod

        assert isinstance(mcp_mod.workspace, Workspace)

    def test_module_has_no_legacy_helpers(self) -> None:
        """The module should no longer define the legacy helper globals."""
        import adjourn.mcp as mcp_mod

        assert not hasattr(mcp_mod, "_SESSIONS_DIR")
        assert not hasattr(mcp_mod, "_CONFIG_PATH")
        assert not hasattr(mcp_mod, "_TIMEOUT")
        assert not hasattr(mcp_mod, "_run_cli")


class TestMCPToolDelegation:
    """Tests that the MCP tools delegate to the module workspace."""

    def test_adjourn_init_delegates_to_workspace(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """adjourn_init should return the swapped workspace's init result."""
        import adjourn.mcp as mcp_mod

        class StubWorkspace:
            """Minimal stand-in exposing only the init method."""

            def init(self, goal: str) -> dict:
                return {"session": "stub", "goal": goal, "status": "running"}

        monkeypatch.setattr(mcp_mod, "workspace", StubWorkspace())

        result = adjourn_init("true")

        assert result == {"session": "stub", "goal": "true", "status": "running"}

    def test_adjourn_resume_delegates_to_workspace(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """adjourn_resume should return the swapped workspace's resume result."""
        import adjourn.mcp as mcp_mod

        class StubWorkspace:
            """Minimal stand-in exposing only the resume method."""

            def resume(self, session: str) -> dict:
                return {"session": session, "status": "done"}

        monkeypatch.setattr(mcp_mod, "workspace", StubWorkspace())

        result = adjourn_resume("abc123")

        assert result == {"session": "abc123", "status": "done"}

    def test_adjourn_add_rules_delegates_to_workspace(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """adjourn_add_rules should return the swapped workspace's add_rules result."""
        import adjourn.mcp as mcp_mod

        class StubWorkspace:
            """Minimal stand-in exposing only the add_rules method."""

            def add_rules(self, session: str, rules: str) -> dict:
                return {"session": session, "rules": rules, "status": "solution"}

        monkeypatch.setattr(mcp_mod, "workspace", StubWorkspace())

        result = adjourn_add_rules("abc123", "rule(extra_rule, true).\n")

        assert result == {
            "session": "abc123",
            "rules": "rule(extra_rule, true).\n",
            "status": "solution",
        }

    def test_adjourn_resume_missing_session_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Resuming a non-existent session should raise RuntimeError."""
        import adjourn.mcp as mcp_mod

        ws = Workspace(
            tmp_path / ".adjourn" / "config.yaml",
            sessions_dir=tmp_path / "sessions",
        )
        monkeypatch.setattr(mcp_mod, "workspace", ws)

        with pytest.raises(RuntimeError, match="not found"):
            adjourn_resume("missing")


class TestMCPCoroutineLoop:
    """End-to-end coroutine loop through the MCP tool functions."""

    def test_full_coroutine_loop_to_done(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Drive a session from init through resume to done."""
        config_path = _write_config(tmp_path, {"test_rules": NONEMPTY_RULESET})
        monkeypatch.setenv("ADJOURN_CONFIG", str(config_path))

        import adjourn.mcp as mcp_mod

        ws = Workspace(config_path, sessions_dir=tmp_path / "sessions")
        monkeypatch.setattr(mcp_mod, "workspace", ws)

        result = adjourn_init("true")
        session_id = result["session"]
        assert result["status"] == "running"

        # Resume to solution
        r1 = adjourn_resume(session_id)
        assert r1["status"] == "solution"

        # Resume to done
        r2 = adjourn_resume(session_id)
        assert r2["status"] == "done"

        # Resuming done is idempotent
        r3 = adjourn_resume(session_id)
        assert r3["status"] == "done"
