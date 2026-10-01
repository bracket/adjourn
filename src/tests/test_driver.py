"""Tests for the LLM driver in adjourn.driver.

The driver is exercised end to end against a real :class:`~adjourn.tools.Workspace`
over a temporary config, with a scripted fake Responses client standing in for
the model HTTP call.  No network access is required.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("haft.mcp_host")

from haft.mcp_host.session import MaxIterationsExceededError

from adjourn.driver import (
    DriveResult,
    Driver,
    DriverError,
    DriverIterationLimitError,
    DriverRoundLimitError,
    DriverStalledError,
)
from adjourn.prompts import read_prompt, render_usage
from adjourn.tools import Workspace
from tests.helpers import NONEMPTY_RULESET, write_config

# ---------------------------------------------------------------------------
# Scripted fake Responses client
# ---------------------------------------------------------------------------


def _function_call(name: str, arguments: dict[str, Any], call_id: str) -> dict[str, Any]:
    """Build a Responses-API dict containing one ``function_call`` item."""
    return {
        "output": [
            {
                "type": "function_call",
                "name": name,
                "arguments": json.dumps(arguments),
                "call_id": call_id,
            }
        ]
    }


def _text_response(text: str = "done") -> dict[str, Any]:
    """Build a Responses-API dict with no function calls, ending the turn."""
    return {
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        ]
    }


class FakeResponsesClient:
    """A scripted stand-in for haft's model HTTP call.

    Each call pops the next scripted response and records the keyword
    arguments haft passed, so tests can inspect the system prompt, the
    rendered user prompt, and the tool results replayed back to the model.
    """

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        """Initialise the client with the responses to return, in order."""
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        """Record the call and return the next scripted response."""
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("FakeResponsesClient ran out of scripted responses")
        return self._responses.pop(0)

    def user_prompts(self) -> list[str]:
        """Return the rendered user prompt of every recorded call, in order."""
        prompts: list[str] = []
        for call in self.calls:
            for item in call["input_items"]:
                if item.get("role") == "user":
                    prompts.append(item["content"][0]["text"])
        return prompts

    def tool_outputs(self, call_id: str) -> list[str]:
        """Return every recorded tool output for *call_id*, in order."""
        outputs: list[str] = []
        for call in self.calls:
            for item in call["input_items"]:
                if item.get("type") == "function_call_output" and item.get("call_id") == call_id:
                    outputs.append(item["output"])
        return outputs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_workspace(
    tmp_path: Path,
    rules: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    *,
    prolog_modes: dict[str, str] | None = None,
) -> Workspace:
    """Build a real Workspace over a temporary config."""
    config_path = write_config(tmp_path, rules, prolog_modes=prolog_modes)
    monkeypatch.delenv("ADJOURN_CONFIG", raising=False)
    return Workspace(config_path, sessions_dir=tmp_path / "sessions")


def _session_id(workspace: Workspace) -> str:
    """Return the single session id in *workspace*'s sessions directory."""
    states = [
        path
        for path in workspace.sessions_dir.glob("*.json")
        if not path.name.endswith(".context.json")
    ]
    assert len(states) == 1
    return states[0].stem


def _make_driver(
    workspace: Workspace,
    client: FakeResponsesClient,
    **kwargs: Any,
) -> Driver:
    """Build a Driver wired to the fake client."""
    return Driver(
        workspace,
        "test-model",
        "http://example.invalid",
        _responses_client=client,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Error hierarchy (no haft runtime semantics)
# ---------------------------------------------------------------------------


def test_error_subclasses() -> None:
    """The three driver errors should subclass DriverError."""
    assert issubclass(DriverStalledError, DriverError)
    assert issubclass(DriverRoundLimitError, DriverError)
    assert issubclass(DriverIterationLimitError, DriverError)


# ---------------------------------------------------------------------------
# Driving
# ---------------------------------------------------------------------------


def test_solution_without_llm_rounds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A goal solved by the initial auto-resume never calls the model."""
    workspace = _make_workspace(tmp_path, {"test_rules": NONEMPTY_RULESET}, monkeypatch)
    client = FakeResponsesClient([])
    driver = _make_driver(workspace, client)

    result = driver.drive("true")

    assert isinstance(result, DriveResult)
    assert result.status == "solution"
    assert result.solutions == [{}]
    assert result.state["status"] == "solution"
    assert client.calls == []


def test_add_rules_reaches_solution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A suspended session is advanced by the LLM calling add_rules."""
    workspace = _make_workspace(
        tmp_path,
        {"test_rules": "rule(my_yield_goal, yield(checkpoint)).\n"},
        monkeypatch,
        prolog_modes={"test_rules": "strict"},
    )
    client = FakeResponsesClient(
        [
            _function_call("add_rules", {"rules": "rule(my_yield_goal, true).\n"}, "call-1"),
            _text_response(),
        ]
    )
    driver = _make_driver(workspace, client)

    result = driver.drive("my_yield_goal")

    assert result.status == "solution"
    assert result.solutions == [{}]
    assert len(client.calls) == 2


def test_push_context_persists_into_next_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pushed note appears in the next round's prompt and the sidecar."""
    workspace = _make_workspace(
        tmp_path,
        {"test_rules": "rule(two, (yield(a), yield(b))).\n"},
        monkeypatch,
        prolog_modes={"test_rules": "strict"},
    )
    client = FakeResponsesClient(
        [
            _function_call("push_context", {"text": "remember this"}, "call-1"),
            _function_call("resume", {}, "call-2"),
            _text_response(),
            _function_call("resume", {}, "call-3"),
            _text_response(),
        ]
    )
    driver = _make_driver(workspace, client)

    result = driver.drive("two")

    assert result.status == "solution"
    prompts = client.user_prompts()
    assert "remember this" not in prompts[0]
    assert "remember this" in prompts[-1]

    session = _session_id(workspace)
    sidecar = json.loads(workspace.context_path(session).read_text(encoding="utf-8"))
    assert sidecar["pushed"] == ["remember this"]


def test_pop_context_without_frames_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Popping with no pushed frames yields an error result, not an exception."""
    workspace = _make_workspace(
        tmp_path,
        {"test_rules": "rule(two, (yield(a), yield(b))).\n"},
        monkeypatch,
        prolog_modes={"test_rules": "strict"},
    )
    client = FakeResponsesClient(
        [
            _function_call("pop_context", {}, "call-1"),
            _function_call("resume", {}, "call-2"),
            _text_response(),
            _function_call("resume", {}, "call-3"),
            _text_response(),
        ]
    )
    driver = _make_driver(workspace, client)

    result = driver.drive("two")

    assert result.status == "solution"
    outputs = client.tool_outputs("call-1")
    assert outputs
    payload = json.loads(outputs[0])
    assert "error" in payload


def test_stalled_round_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A round that neither resumes nor adds rules raises DriverStalledError."""
    workspace = _make_workspace(
        tmp_path,
        {"test_rules": "rule(two, (yield(a), yield(b))).\n"},
        monkeypatch,
        prolog_modes={"test_rules": "strict"},
    )
    client = FakeResponsesClient([_text_response()])
    driver = _make_driver(workspace, client)

    with pytest.raises(DriverStalledError) as excinfo:
        driver.drive("two")

    error = excinfo.value
    assert error.session == _session_id(workspace)
    assert error.state["status"] == "suspended"
    assert workspace.context_path(error.session).exists()


def test_round_limit_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exceeding max_rounds raises DriverRoundLimitError."""
    workspace = _make_workspace(
        tmp_path,
        {"test_rules": "rule(loop, (yield(a), loop)).\n"},
        monkeypatch,
        prolog_modes={"test_rules": "strict"},
    )
    client = FakeResponsesClient(
        [
            _function_call("resume", {}, "call-1"),
            _text_response(),
        ]
    )
    driver = _make_driver(workspace, client, max_rounds=1)

    with pytest.raises(DriverRoundLimitError) as excinfo:
        driver.drive("loop")

    assert excinfo.value.session == _session_id(workspace)
    assert excinfo.value.state["status"] == "suspended"


def test_iteration_limit_becomes_driver_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """haft's MaxIterationsExceededError becomes DriverIterationLimitError."""
    workspace = _make_workspace(
        tmp_path,
        {"test_rules": "rule(loop, (yield(a), loop)).\n"},
        monkeypatch,
        prolog_modes={"test_rules": "strict"},
    )
    client = FakeResponsesClient([_function_call("resume", {}, "call-1")])
    driver = _make_driver(workspace, client, max_iterations=1)

    with pytest.raises(DriverIterationLimitError) as excinfo:
        driver.drive("loop")

    assert isinstance(excinfo.value.__cause__, MaxIterationsExceededError)


def test_all_solutions_collects_and_does_not_count_rounds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """all_solutions collects every solution; auto-resumes are not rounds."""
    workspace = _make_workspace(
        tmp_path,
        {"test_rules": "rule(m(1), true).\nrule(m(2), true).\n"},
        monkeypatch,
        prolog_modes={"test_rules": "strict"},
    )
    client = FakeResponsesClient([])
    driver = _make_driver(workspace, client, max_rounds=0)

    result = driver.drive("m(X)", all_solutions=True)

    assert result.status == "done"
    assert result.solutions == [{"X": "1"}, {"X": "2"}]
    assert client.calls == []


def test_caller_system_prompt_is_appended(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A caller system prompt follows the default preamble and usage text."""
    workspace = _make_workspace(
        tmp_path,
        {"test_rules": "rule(my_yield_goal, yield(checkpoint)).\n"},
        monkeypatch,
        prolog_modes={"test_rules": "strict"},
    )
    client = FakeResponsesClient(
        [
            _function_call("add_rules", {"rules": "rule(my_yield_goal, true).\n"}, "call-1"),
            _text_response(),
        ]
    )
    driver = _make_driver(workspace, client, system_prompt="CALLER TEXT")

    driver.drive("my_yield_goal")

    system_item = client.calls[0]["input_items"][0]
    assert system_item["role"] == "system"
    expected = render_usage(read_prompt("driver_preamble.md")) + "\n\n" + "CALLER TEXT"
    assert system_item["content"][0]["text"] == expected


def _assert_no_session_or_hashes(output: str, session: str) -> None:
    """Assert *output* leaks neither the session id nor any hash keys."""
    assert session not in output
    for key in ("session", "ruleset_hash", "resume_hash"):
        assert key not in output


def test_tool_results_hide_session_and_hashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """resume and add_rules tool results carry no session id or hash keys."""
    resume_dir = tmp_path / "resume"
    resume_dir.mkdir()
    resume_workspace = _make_workspace(
        resume_dir,
        {"test_rules": "rule(my_yield_goal, yield(checkpoint)).\n"},
        monkeypatch,
        prolog_modes={"test_rules": "strict"},
    )
    resume_client = FakeResponsesClient(
        [
            _function_call("resume", {}, "call-1"),
            _text_response(),
        ]
    )
    resume_driver = _make_driver(resume_workspace, resume_client)

    resume_result = resume_driver.drive("my_yield_goal")

    assert resume_result.status == "solution"
    resume_output = resume_client.tool_outputs("call-1")[0]
    _assert_no_session_or_hashes(resume_output, _session_id(resume_workspace))

    add_dir = tmp_path / "add"
    add_dir.mkdir()
    add_workspace = _make_workspace(
        add_dir,
        {"test_rules": "rule(my_yield_goal, yield(checkpoint)).\n"},
        monkeypatch,
        prolog_modes={"test_rules": "strict"},
    )
    add_client = FakeResponsesClient(
        [
            _function_call("add_rules", {"rules": "rule(my_yield_goal, true).\n"}, "call-1"),
            _text_response(),
        ]
    )
    add_driver = _make_driver(add_workspace, add_client)

    add_result = add_driver.drive("my_yield_goal")

    assert add_result.status == "solution"
    add_output = add_client.tool_outputs("call-1")[0]
    _assert_no_session_or_hashes(add_output, _session_id(add_workspace))
