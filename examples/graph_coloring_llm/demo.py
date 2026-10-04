"""LLM-driven graph coloring: the LLM writes the program that solves it.

The seed program (llm_seed.pl) defines coloring/4 in terms of
implementation/4, which does not exist yet.  Resolving coloring(A, B, C, D)
suspends at implement_program; the driver hands the suspension to an LLM,
which adds rules defining implementation/4; the driver then resumes and
reports the first solution.

Edit the constants below to point at your LLM, then run:

    python demo.py
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from adjourn.config import Config
from adjourn.driver import Driver, DriverError
from adjourn.tools import Workspace

# --- Point this at your LLM -------------------------------------------------
# The endpoint must speak the OpenAI Responses API (for example OpenAI).
MODEL = "gpt-5"
BASE_URL = "https://api.openai.com/v1"
# Name of the environment variable holding your API key, sent as a Bearer
# token.  Set to None (or "") for endpoints that need no key.
API_KEY_ENV: str | None = "OPENAI_API_KEY"
# ----------------------------------------------------------------------------

GOAL = "coloring(A, B, C, D)"

PROBLEM = """\
Color the vertices of the cycle graph a-b-c-d-a with red, green and blue so
that adjacent vertices have different colors. Vertex a is red.
When the program suspends at implement_program, add rules defining
implementation(A, B, C, D), which binds A, B, C and D to the colors of
vertices a, b, c and d."""

HERE = Path(__file__).resolve().parent
RUN_DIR = HERE / "llm_run"
CONFIG_PATH = RUN_DIR / ".adjourn" / "config.yaml"


def request_headers() -> dict[str, str] | None:
    """Return the auth header for the model endpoint, if a key is configured."""
    if not API_KEY_ENV:
        return None
    key = os.environ.get(API_KEY_ENV)
    if not key:
        sys.exit(f"Set ${API_KEY_ENV} to your API key (or set API_KEY_ENV = None).")
    return {"Authorization": f"Bearer {key}"}


def prepare_workspace() -> Workspace:
    """Start from an empty llm_run/ whose config registers only the seed."""
    shutil.rmtree(RUN_DIR, ignore_errors=True)
    # Store paths are relative to the directory containing .adjourn/.
    Config(CONFIG_PATH, create=True).append_file_store("../llm_seed.pl")
    return Workspace(CONFIG_PATH)


def report(rules_files: list[Path]) -> None:
    """Print the rules the LLM wrote."""
    for path in rules_files:
        print(f"--- {path.relative_to(HERE)} (written by the LLM) ---")
        print(path.read_text().rstrip())
        print()


def main() -> None:
    headers = request_headers()
    workspace = prepare_workspace()
    driver = Driver(workspace, MODEL, BASE_URL, request_headers=headers)

    try:
        result = driver.drive(GOAL, initial_context=[PROBLEM])
    except DriverError as exc:
        report(sorted(RUN_DIR.glob("rules_*.pl")))
        sys.exit(f"Driver error: {exc}")

    report(sorted(RUN_DIR.glob("rules_*.pl")))
    print(f"status: {result.status}")
    for bindings in result.solutions:
        print("solution: " + ", ".join(f"{k}={v}" for k, v in bindings.items()))


if __name__ == "__main__":
    main()
