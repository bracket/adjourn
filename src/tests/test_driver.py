"""Tests for the adjourn LLM driver in adjourn.driver."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("haft.mcp_host")

from haft.mcp_host import MaxIterationsExceededError

from adjourn.driver import (
    Driver,
    DriverIterationLimitError,
    DriverRoundLimitError,
)
from adjourn.prompts import read_prompt, render_usage
from adjourn.tools import Workspace
from tests.helpers import write_config

Responder = Callable[[int, dict[str, Any]], dict[str, Any]]


class FakeModel:
    """A scripted stand-in for haft's Responses HTTP client.

    Records every call it receives and delegates the reply to *responder*,
    which is given the one-based call index and the keyword arguments.
    """

    def __init__(self, responder: Responder) -> None:
        """Store the responder and start with no recorded calls."""
        self.calls: list[dict[str, Any]] = []
        self._responder = responder

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        """Record the call and return the responder's reply."""
        self.calls.append(kwargs)
        return self._responder(len(self.calls), kwargs)


def _function_call(
    name: str, arguments: dict[str, Any], call_id: str
) -> dict[str, Any]:
    """Build a Responses-API ``function_call`` output item."""
    return {
        "type": "function_call",
        "name": name,
        "arguments": json.dumps(arguments),
        "call_id": call_id,
    }


def _response(*items: dict[str, Any]) -> dict[str, Any]:
    """Build a Responses-API reply carrying *items* as its output."""
    return {"output": list(items)}


def _no_tool_calls(call_index: int, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Reply with no function calls, ending the turn."""
    del call_index, kwargs
    return {"output": []}


def _message_text(call: dict[str, Any], role: str) -> str | None:
    """Return the text of the first *role* message in a recorded call."""
    for item in call["input_items"]:
        if item.get("type") == "message" and item.get("role") == role:
            return item["content"][0]["text"]
    return None


def _tool_outputs(call: dict[str, Any]) -> list[Any]:
    """Decode every ``function_call_output`` in a recorded call."""
    outputs: list[Any] = []
    for item in call["input_items"]:
        if item.get("type") == "function_call_output":
            outputs.append(json.loads(item["output"]))
    return outputs


def _workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rules: str
) -> Workspace:
    """Build a real Workspace over a temporary config with *rules*."""
    monkeypatch.delenv("ADJOURN_CONFIG", raising=False)
    config_path = write_config(tmp_path, {"prog": rules})
    return Workspace(config_path, sessions_dir=tmp_path / "sessions")


def _session_id(workspace: Workspace) -> str:
    """Return the single session id present in the workspace."""
    states = [
        path
        for path in workspace.sessions_dir.glob("*.json")
        if not path.name.endswith(".context.json")
    ]
    assert len(states) == 1
    return states[0].stem


@pytest.mark.parametrize(
    ("status", "suspension", "bindings", "expected_label", "expected_bindings"),
    [
        ("running", None, None, None, None),
        ("suspended", {"label": "need_input"}, None, "need_input", None),
        ("solution", None, {"X": "1"}, None, {"X": "1"}),
        ("done", None, None, None, None),
    ],
)
def test_driver_tool_state_always_projects_all_three_fields(
    tmp_path: Path,
    status: str,
    suspension: dict[str, str] | None,
    bindings: dict[str, str] | None,
    expected_label: str | None,
    expected_bindings: dict[str, str] | None,
) -> None:
    state_path = tmp_path / "state.json"
    state = {"status": status}
    if suspension is not None:
        state["suspension"] = suspension
    if bindings is not None:
        state["bindings"] = bindings
    state_path.write_text(json.dumps(state))

    driver = object.__new__(Driver)
    driver.workspace = SimpleNamespace(state_path=lambda session: state_path)

    assert driver._tool_state("session") == {
        "status": status,
        "label": expected_label,
        "bindings": expected_bindings,
    }


class TestDriverSolutions:
    """Tests for reaching solutions without and with LLM rounds."""

    def test_solution_on_initial_resume_runs_no_round(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A goal solved on the first resume should never call the model."""
        workspace = _workspace(tmp_path, monkeypatch, "g :- true.\n")
        fake = FakeModel(_no_tool_calls)
        driver = Driver(workspace, "model", "http://example", _responses_client=fake)

        result = driver.drive("true")

        assert result.status == "solution"
        assert fake.calls == []
        assert len(result.solutions) == 1
        assert result.solutions[0] == result.state["bindings"]

    def test_add_rules_tool_reaches_solution(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The model adding the missing fact should let the goal succeed."""
        workspace = _workspace(
            tmp_path, monkeypatch, "g :- yield(need_fact), have_fact.\n"
        )
        added = {"done": False}

        def responder(call_index: int, kwargs: dict[str, Any]) -> dict[str, Any]:
            del call_index, kwargs
            if not added["done"]:
                added["done"] = True
                return _response(
                    _function_call("add_rules", {"rules": "have_fact.\n"}, "call-1")
                )
            return {"output": []}

        fake = FakeModel(responder)
        driver = Driver(workspace, "model", "http://example", _responses_client=fake)

        result = driver.drive("g")

        assert result.status == "solution"
        assert len(result.solutions) == 1

    def test_round_without_tool_calls_resumes_past_yield(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A round with no tool calls should resume past the yield cleanly."""
        workspace = _workspace(tmp_path, monkeypatch, "g :- yield(checkpoint), true.\n")
        fake = FakeModel(_no_tool_calls)
        driver = Driver(workspace, "model", "http://example", _responses_client=fake)

        result = driver.drive("g")

        assert result.status == "solution"
        assert len(fake.calls) == 1

    def test_all_solutions_collects_every_solution_without_rounds(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """all_solutions should collect every solution without any LLM round."""
        workspace = _workspace(tmp_path, monkeypatch, "p(1).\np(2).\n")
        fake = FakeModel(_no_tool_calls)
        driver = Driver(
            workspace, "model", "http://example", max_rounds=0, _responses_client=fake
        )

        result = driver.drive("p(X)", all_solutions=True)

        assert result.status == "done"
        assert len(result.solutions) == 2
        assert all(isinstance(solution, dict) for solution in result.solutions)
        assert fake.calls == []


class TestDriverContextTools:
    """Tests for the push_context and pop_context tools."""

    def test_push_context_appears_in_next_round_and_sidecar(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A pushed note should show in the next prompt and the sidecar file."""
        workspace = _workspace(
            tmp_path, monkeypatch, "g :- yield(first), yield(second), true.\n"
        )
        pushed = {"done": False}

        def responder(call_index: int, kwargs: dict[str, Any]) -> dict[str, Any]:
            del call_index, kwargs
            if not pushed["done"]:
                pushed["done"] = True
                return _response(
                    _function_call(
                        "push_context", {"text": "remember the fact"}, "call-1"
                    )
                )
            return {"output": []}

        fake = FakeModel(responder)
        driver = Driver(workspace, "model", "http://example", _responses_client=fake)

        result = driver.drive("g")

        assert result.status == "solution"
        assert "remember the fact" in (_message_text(fake.calls[-1], "user") or "")
        session = _session_id(workspace)
        sidecar = json.loads(
            workspace.context_path(session).read_text(encoding="utf-8")
        )
        assert sidecar["pushed"] == ["remember the fact"]

    def test_pop_context_without_pushed_frames_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Popping an empty stack should return an error result, not raise."""
        workspace = _workspace(tmp_path, monkeypatch, "g :- yield(checkpoint), true.\n")
        popped = {"done": False}

        def responder(call_index: int, kwargs: dict[str, Any]) -> dict[str, Any]:
            del call_index, kwargs
            if not popped["done"]:
                popped["done"] = True
                return _response(_function_call("pop_context", {}, "call-1"))
            return {"output": []}

        fake = FakeModel(responder)
        driver = Driver(workspace, "model", "http://example", _responses_client=fake)

        result = driver.drive("g")

        assert result.status == "solution"
        outputs = [output for call in fake.calls for output in _tool_outputs(call)]
        assert outputs
        assert "error" in outputs[0]


class TestDriverLimits:
    """Tests for the driver's round and iteration limits."""

    def test_max_rounds_raises_round_limit_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Exceeding max_rounds should raise with the session and state set."""
        workspace = _workspace(
            tmp_path, monkeypatch, "g :- yield(a), yield(b), yield(c), true.\n"
        )
        fake = FakeModel(_no_tool_calls)
        driver = Driver(
            workspace, "model", "http://example", max_rounds=1, _responses_client=fake
        )

        with pytest.raises(DriverRoundLimitError) as excinfo:
            driver.drive("g")

        error = excinfo.value
        assert error.session == _session_id(workspace)
        assert error.state["status"] == "suspended"
        assert workspace.context_path(error.session).exists()

    def test_iteration_limit_becomes_driver_iteration_limit_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """haft's iteration limit should surface as a driver error with cause."""
        workspace = _workspace(tmp_path, monkeypatch, "g :- yield(checkpoint), true.\n")

        def responder(call_index: int, kwargs: dict[str, Any]) -> dict[str, Any]:
            del kwargs
            return _response(
                _function_call("push_context", {"text": "note"}, f"call-{call_index}")
            )

        fake = FakeModel(responder)
        driver = Driver(
            workspace,
            "model",
            "http://example",
            max_iterations=1,
            _responses_client=fake,
        )

        with pytest.raises(DriverIterationLimitError) as excinfo:
            driver.drive("g")

        error = excinfo.value
        assert isinstance(error.__cause__, MaxIterationsExceededError)
        assert error.session == _session_id(workspace)
        assert error.state["status"] == "suspended"


class TestDriverPromptAndTools:
    """Tests for the system prompt and the offered tool surface."""

    def test_caller_system_prompt_appended(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A caller system prompt should follow the default prompt and usage."""
        workspace = _workspace(tmp_path, monkeypatch, "g :- yield(checkpoint), true.\n")
        fake = FakeModel(_no_tool_calls)
        driver = Driver(
            workspace,
            "model",
            "http://example",
            system_prompt="CALLER TEXT",
            _responses_client=fake,
        )

        driver.drive("g")

        expected = (
            render_usage(read_prompt("driver_preamble.md")) + "\n\n" + "CALLER TEXT"
        )
        assert _message_text(fake.calls[0], "system") == expected

    def test_tools_offered_and_add_rules_result_shape(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The model should see exactly the three tools and no session hashes."""
        workspace = _workspace(
            tmp_path, monkeypatch, "g :- yield(need_fact), have_fact.\n"
        )
        added = {"done": False}

        def responder(call_index: int, kwargs: dict[str, Any]) -> dict[str, Any]:
            del call_index, kwargs
            if not added["done"]:
                added["done"] = True
                return _response(
                    _function_call("add_rules", {"rules": "have_fact.\n"}, "call-1")
                )
            return {"output": []}

        fake = FakeModel(responder)
        driver = Driver(workspace, "model", "http://example", _responses_client=fake)

        driver.drive("g")

        names = {tool["name"] for tool in fake.calls[0]["tools"]}
        assert names == {"add_rules", "push_context", "pop_context"}
        outputs = [output for call in fake.calls for output in _tool_outputs(call)]
        assert outputs
        result = outputs[0]
        assert "session" not in result
        assert "ruleset_hash" not in result
        assert "resume_hash" not in result


def test_driver_imports_without_haft() -> None:
    """Importing adjourn.driver should not require the haft package."""
    code = (
        "import sys; "
        "sys.modules['haft'] = None; "
        "sys.modules['haft.mcp_host'] = None; "
        "from adjourn.driver import ("
        "Driver, DriveResult, DriverError, DriverRoundLimitError, "
        "DriverIterationLimitError)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
