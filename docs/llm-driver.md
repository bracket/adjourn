# LLM Driver and Context Stack

## Goal

Half 2 of MCP exposure: adjourn acts as its own driver. When a goal
suspends, adjourn calls an LLM and offers it tools so the LLM can extend
the ruleset, manage context, and resume. (Half 1, adjourn as an MCP server
to a chat agent, is complete.)

No concrete first use case is fixed yet; the first cut is a proof of the
loop.

## Architecture

Three layers, all in one process:

- **`Workspace`** (`src/adjourn/tools.py`): the tool operations as methods
  -- `init`, `resume`, `add_rules` -- holding the sessions directory,
  config path, and CLI timeout. `Workspace.from_env()` reads the existing
  `ADJOURN_*` environment variables. All resolution still runs through CLI
  subprocesses (`_run_cli`), so janus is never loaded in the calling
  process.
- **MCP server** (`src/adjourn/mcp/__init__.py`): a thin wrapper over a
  module-level `Workspace`. Tool names and behavior are unchanged for the
  chat-agent half. Its `instructions` come from the shared usage text (see
  Prompt).
- **Driver** (`src/adjourn/driver.py`): a `Driver` class that uses a
  haft-mcp-host `ChatSession`
  (`haft/packages/haft-mcp-host/haft/mcp_host/session.py`) with **local
  tools only** (`add_local_tool`). There is no MCP transport between the
  driver and adjourn.

Rejected: the driver as a `ChatSession` pointed at the adjourn MCP server.
It split state between the driver and the server (split brain) and
required running a server. Driving a remote adjourn is out of scope.

The entry point for the first cut is the Python API only.

## Driver

- `Driver(workspace, goal, ...)` takes the workspace, the goal, the
  `ChatSession` model settings, an optional system prompt, `initial_context`,
  `max_rounds=30`, and `all_solutions=False`.
- The driver allocates one session and **binds its id**. The LLM's tools
  carry no session ids or hashes.
- **LLM tool surface** (local tools):
  - `resume()` -- runs to the next `yield`, solution, or `done`
    (`Runner.run`, continuing through checkpoints).
  - `add_rules(rules)` -- adds the rules and resumes in one call. Stays
    non-atomic.
  - `push_context(text)`, `pop_context()` -- see Context stack.
- **Tool errors:** the tool adapters catch exceptions and return them as
  error results, so the LLM can correct itself. (haft otherwise re-raises
  tool exceptions out of `send()`.)
- **Only the LLM resumes a suspension.**

### Loop

1. Initialize the session and run until suspended, solution, or done.
2. Each suspension is one **round**: a fresh `ChatSession`, prompted with
   the rendered context. No transcript carries over between rounds; the
   context stack is the only memory.
3. When `send()` returns:
   - if neither `resume` nor `add_rules` was called during the turn, the
     session is incorrectly still suspended -> raise `DriverStalledError`;
   - if the session is suspended at a new point -> next round;
   - if solution or done -> finish.

### Solutions

- **Once** by default: return on the first solution.
- `all_solutions=True`: the driver itself (no LLM involvement) resumes past
  each solution and collects bindings until `done`.

### Limits, errors, results

- `max_rounds` (default 30) caps suspension rounds per drive; exceeding it
  raises `DriverRoundLimitError`.
- haft's `MaxIterationsExceededError` is wrapped in a driver error.
- All driver errors carry the **state**, not the transcript.
- The result is `DriveResult(status, solutions, state)`. No transcript is
  returned; transcripts belong in the future event log.

## Context stack

- **Frames are plain text.**
- **The stack is driver-side only.** Nothing is added to the adjourn
  language or to the session state: there are no L3 `push_context` /
  `pop_context` builtins, context is not carried across yield/resume, and
  backtracking never touches the stack.
- **Pinned frames** come from `initial_context` (the caller's context, e.g.
  the session's overall goal). They are a fixed base of the stack and are
  not poppable.
- **Pushed frames** come from the LLM via `push_context` / `pop_context`.
  `pop_context` with only pinned frames left returns an error result.
- **Persistence:** the stack is saved to
  `<sessions_dir>/<id>.context.json`, beside the session state. Adjourn
  never reads it.
- **Program-author context** for a specific suspension goes in the `yield`
  label, which is an arbitrary term and reaches the LLM through the state.
- **Rendering**, per round: pinned frames, then pushed frames oldest-first,
  then the full state JSON (so the LLM can see what will happen next; trim
  later if too large). Prompt caching will likely break often; accepted.

Rejected: L3 builtins for context, either native or as a foreign callout.
Context only matters to the driver, and keeping it out of the language
avoids driver-specific primitives in L3.

## Prompt

- Adjourn ships a standard default prompt that instructs the LLM how to
  use adjourn. It is customizable by the caller.
- The "how to use adjourn" text has a single source of truth,
  `src/adjourn/prompts/usage.md` (loaded via `importlib.resources`), shared
  with the MCP server's `instructions`.

## Invariants

- Only one janus instance may run per process; this is the basis of
  suspend/resume. The driver process never loads janus: all resolution goes
  through CLI subprocesses. Anything that moves resolution in-process (e.g.
  calling `Runner` directly) must respect this.

## Deferred (decided later, own tickets)

- haft: return local tool exceptions as tool results instead of
  re-raising.
- Event hooks to notify the user on each suspend/resume (needed for the
  CLI).
- Logging / an event log that carries transcripts.
- A trace tree of rounds tied to the context stack.
- CLI entry point (`adjourn drive`).
- Distinguishing human-in-the-loop suspensions from LLM suspensions.
- In-process resolution (direct `Runner` calls instead of CLI
  subprocesses), with one-live-session-per-process enforcement or janus
  module reset.
- Atomic `add_rules` (validate before consulting, roll back on failure).
- Driving a remote adjourn.

## Open questions

- LLM-managed context files interpolated into the prompt, and whether the
  LLM gets file read/write tools for them.
- Exact rendering layout beyond ordering, and how to trim the state if it
  is too large.
- Long-term handling of prompt caching.
