# LLM Driver and Context Stack

## Goal

Half 2 of MCP exposure: adjourn drives its own resolution and calls an LLM
as a subsidiary handler. When a goal suspends, the driver calls an LLM and
offers it tools to extend the ruleset and manage its context; when the LLM
ends its turn, the driver resumes the session. The LLM never resumes. (Half
1, adjourn as an MCP server to a chat agent, is complete; there the chat
agent is the driver.)

No concrete first use case is fixed yet; the first cut is a proof of the
loop.

## Architecture

Three layers, all in one process:

- **`Workspace`** (`src/adjourn/tools.py`): the tool operations as methods
  -- `init`, `resume`, `add_rules` -- holding the sessions directory,
  config path, and CLI timeout. `Workspace.from_env()` reads the existing
  `ADJOURN_*` environment variables. All resolution still runs through CLI
  subprocesses (`_run_cli`), so janus is never loaded in the calling
  process. `add_rules` adds the rules and repoints the session's resume
  hash to `@top`, but **does not resume**; resuming is always a separate
  `resume` call.
- **MCP server** (`src/adjourn/mcp/__init__.py`): a thin wrapper over a
  module-level `Workspace`. The chat agent is the driver here, so it keeps
  `adjourn_resume`; after `adjourn_add_rules` it must call `adjourn_resume`
  itself. Its `instructions` come from the shared usage text (see Prompt).
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

- `Driver(workspace, model, base_url, *, system_prompt=None, max_rounds=30,
  max_iterations=10, request_headers=None, _responses_client=None)` holds
  the configuration; `drive(goal, initial_context=(), all_solutions=False)`
  performs one run on a fresh session. `_responses_client` is passed
  through to every `ChatSession` so tests can script the model.
- The driver allocates one session and **binds its id**. The LLM's tools
  carry no session ids or hashes.
- **The driver alone resumes.** The LLM is called during a suspension and
  can only change what happens next.
- **LLM tool surface** (local tools):
  - `add_rules(rules)` -- adds the rules and repoints the resume to the top
    of the current goal. Does not resume. Stays non-atomic.
  - `push_context(text)`, `pop_context()` -- see Context stack.
- **Tool errors:** the tool adapters catch exceptions and return them as
  error results, so the LLM can correct itself. (haft otherwise re-raises
  tool exceptions out of `send()`.)

### Loop

1. Initialize the session, then resume once (no LLM), so the first round
   starts at a real stop: suspended, solution, or done.
2. Each suspension is one **round**: a fresh `ChatSession`, prompted with
   the rendered context stack and state. No transcript carries over between
   rounds; the context stack is the only memory. The LLM may make any number
   of tool calls, including none.
3. When `send()` returns, the driver saves the context stack and resumes
   the session, continuing past the yield. If rules were added, the session
   was repointed at `@top` (the ruleset containing every registered rule),
   so the new rules are in scope for the goals still to be reduced.
4. At the next stop: suspended -> next round; solution or done -> finish
   (see Solutions).

Ending a turn without tool calls is a valid "just continue", so there is no
stalled-round error; `max_rounds` is the only loop guard.

### Solutions

- **Once** by default: return on the first solution.
- `all_solutions=True`: the driver resumes past each solution and collects
  bindings until `done`. These resumes involve no LLM and do not count as
  rounds.

### Limits, errors, results

- `max_rounds` (default 30) caps LLM rounds per drive; exceeding it raises
  `DriverRoundLimitError`.
- haft's `MaxIterationsExceededError` is wrapped in
  `DriverIterationLimitError`.
- All driver errors subclass `DriverError` and carry the **session id and
  the state**, not the transcript.
- The result is `DriveResult(status, solutions, state)`, where `solutions`
  holds the bindings dict of each solution. No transcript is returned;
  transcripts belong in the future event log.

## Context stack

`ContextStack` (`src/adjourn/context.py`).

- **Frames are plain text.**
- **The stack is driver-side only.** Nothing is added to the adjourn
  language or to the session state: there are no L3 `push_context` /
  `pop_context` builtins, context is not carried across yield/resume, and
  backtracking never touches the stack.
- **Pinned frames** come from `initial_context` (the caller's context, e.g.
  the session's overall goal). They are a fixed base of the stack and are
  not poppable.
- **Pushed frames** come from the LLM via `push_context` / `pop_context`.
  `pop_context` with only pinned frames left raises
  `ContextStackEmptyError`, which the tool adapter returns as an error
  result.
- **Persistence:** the stack is saved to
  `<sessions_dir>/<id>.context.json` (`Workspace.context_path`), beside the
  session state, after every round and before raising any driver error.
  Pinned frames are saved too. Adjourn never reads it.
- **Program-author context** for a specific suspension goes in the `yield`
  label, which reaches the LLM through the state.
- **Rendering**, per round: a `## Background` section (pinned frames), a
  `## Your context stack` section (pushed frames, oldest first), and a
  `## Session state` section (the full state JSON); empty sections are
  omitted. Prompt caching will likely break often; accepted.

Rejected: L3 builtins for context, either native or as a foreign callout.
Context only matters to the driver, and keeping it out of the language
avoids driver-specific primitives in L3.

## Prompt

- The "how to use adjourn" text has a single source of truth,
  `src/adjourn/prompts/usage.md` (loaded via `importlib.resources`). It is
  neutral about who drives: it describes the coroutine, the lifecycle,
  suspensions, and adding rules.
- Each caller layers its own preamble on top via `render_usage(preamble)`:
  - `prompts/mcp_preamble.md` -- the chat agent drives, and must call
    `adjourn_resume` after `adjourn_add_rules` or any other tool calls.
  - `prompts/driver_preamble.md` -- the LLM is called during a suspension,
    ends its turn when done, and cannot resume.
- A caller-supplied `system_prompt` is appended to the driver's default
  system prompt, not a replacement for it.

## Invariants

- Only one janus instance may run per process; this is the basis of
  suspend/resume. The driver process never loads janus: all resolution goes
  through CLI subprocesses. Anything that moves resolution in-process (e.g.
  calling `Runner` directly) must respect this.

## Deferred (decided later, own tickets)

- haft: return local tool exceptions as tool results instead of
  re-raising.
- A way for the LLM to give up on a suspension (e.g. a `give_up(reason)`
  tool that stops the drive with an error).
- Structured `yield` labels serialized to JSON, and safe state-file naming
  (see INBOX).
- Continuing an existing session with `drive`.
- Context tools on the MCP server.
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
- How to trim the state in the rendered prompt if it is too large.
- Long-term handling of prompt caching.
