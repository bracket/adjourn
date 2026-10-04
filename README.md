# adjourn

[![CI](https://github.com/bracket/adjourn/actions/workflows/ci.yml/badge.svg)](https://github.com/bracket/adjourn/actions/workflows/ci.yml)

**A Prolog engine that stops and asks for help.** `adjourn` runs logic
queries that pause when they get stuck, persist their exact state, and resume
once an LLM (or a person) has supplied what was missing.

## Why

LLM agents are good at filling gaps and bad at keeping track of where they
are. Logic programs are the opposite: they track exactly which goals remain
and which alternatives are still open, but stall the moment they need a fact
they don't have.

`adjourn` pairs the two. The program owns control flow. When it needs outside
input it suspends at a labelled `yield(Label)`, and a resolver (an LLM, a
human, or another program) gets a chance to extend the rules before
resolution continues. The resolver can change *what* the program knows. It
never decides *when* execution moves on.

## The LLM driver

The driver runs a goal to completion with an LLM in the loop:

```python
from adjourn.tools import Workspace
from adjourn.driver import Driver

driver = Driver(
    Workspace.from_env(),
    model="<model-name>",
    base_url="<responses-compatible endpoint>",
)
result = driver.drive(
    "plan(Steps)",
    initial_context=["We are planning a three-step data migration."],
)
print(result.status, result.solutions)
```

Each time the goal suspends, the driver opens a fresh LLM round with the
suspension label, the session state, and a small context stack. The LLM has
three tools:

- `add_rules(rules)`: add Prolog clauses and point the session at `@top`,
  the ruleset containing every registered rule, so they are in scope on the
  next resume.
- `push_context(text)` / `pop_context()`: manage its own working notes,
  which are the only memory carried between rounds.

There is no resume tool. When the LLM ends its turn, the driver resumes, and
the program decides what happens next. No transcript carries over between
rounds; the context stack and the persisted state are the whole story.

## How it works

`adjourn` is a continuation-style meta-interpreter: the entire resolution
state (every open branch and its remaining goals) is an explicit,
serializable value instead of living on the Prolog engine's stack. That is
what makes it possible to stop anywhere, write the state to disk as JSON, and
resume later in a different process.

Resolution stops at one of three statuses:

- **suspended**: the program hit `yield(Label)` and is waiting for input.
- **solution**: a set of bindings was found. Resuming backtracks for the
  next one.
- **done**: every alternative is exhausted.

A program can also declare checkpoints, where the state is saved and
resolution continues without stopping.

Python owns the orchestration (persistence, ruleset storage, the driver,
and the MCP server). SWI-Prolog, embedded via Janus, owns unification and
the single-step reducer. All resolution runs in CLI subprocesses, so a driver
process never loads Prolog itself.

Rulesets are **content-addressed**: a hash over a canonical form of the
clauses, so a persisted session pins exactly the program it was running.
Rulesets compose into ordered chains with deterministic composite hashes.

## Installation

Requires Python 3.11+ and [SWI-Prolog](https://www.swi-prolog.org/) 10.x.
Install SWI-Prolog first, since the `janus-swi` dependency builds against it:

```bash
brew install swi-prolog                       # macOS (Homebrew)

sudo apt-add-repository ppa:swi-prolog/stable # Ubuntu
sudo apt-get update && sudo apt-get install swi-prolog
```

For other platforms, see the
[SWI-Prolog downloads](https://www.swi-prolog.org/Download.html).

Then install adjourn directly from GitHub:

```bash
pip install "adjourn @ git+https://github.com/bracket/adjourn.git"
```

Optional extras use the same form, for example
`pip install "adjourn[mcp] @ git+https://github.com/bracket/adjourn.git"`:

- `[mcp]`: MCP server and LLM driver.
- `[query]`: mnestic (CozoDB) ruleset stores.

To work on adjourn itself, clone it and install in editable mode instead:

```bash
git clone https://github.com/bracket/adjourn.git
cd adjourn
pip install -e ".[dev]"
```

## Example

[`examples/graph_coloring`](examples/graph_coloring/) colors a small graph
entirely from the command line. Each `adjourn resume` is a fresh process that
picks the search up from a JSON state file, and backtracks into the next
coloring. [`examples/graph_coloring_llm`](examples/graph_coloring_llm/)
solves the same problem with the LLM driver: an LLM writes the program when
the seed program suspends.

## Command line

```bash
adjourn init "<goal>" state.json --ruleset <alias-or-hash>
adjourn resume state.json next_state.json
adjourn store list
```

`init` writes a starting state without invoking Prolog. `resume` advances to
the next solution, suspension, or exhaustion and prints a one-line status.
Because state is plain JSON, a suspended session can be inspected or resolved
by hand between resumes. `adjourn complete` emits a shell completion script
(bash, zsh, fish).

## MCP server

`adjourn` can also be exposed as an MCP server, with a chat agent as the
driver. The agent gets `adjourn_init`, `adjourn_resume`, and
`adjourn_add_rules`; here the agent owns the loop, and must resume after
adding rules.

```bash
ADJOURN_MCP_AUTH_DISABLED=1 python -m adjourn.mcp   # local, no auth
```

Configuration is via `ADJOURN_MCP_HOST`, `ADJOURN_MCP_PORT`, and the
`ADJOURN_MCP_AUTH0_*` variables for OAuth. A container setup lives in
[`images/service-adjourn/`](images/service-adjourn/).

## Relationship to other projects

`enbug`, a coding-agent harness, is built on `adjourn`: it encodes an agent
loop as rules and uses suspensions as the points where a coding agent takes
over.

## Project status

Under active development. The meta-interpreter, suspend/resume,
content-addressed rulesets, the MCP server, and the Python driver API are in
place. A `drive` CLI command and suspension event hooks are next.

## Development

```bash
pip install -e ".[dev]"
pre-commit install

pytest
mypy src/adjourn
ruff check src/adjourn
```

## License

MIT. See [`LICENSE`](LICENSE).
