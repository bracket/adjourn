# LLM Driver and Context Stack

## Goal

Half 2 of MCP exposure: adjourn acts as its own driver. When a goal
suspends, adjourn calls an LLM and offers it adjourn's own MCP tools,
so the LLM can extend the ruleset, manage context, and resume. (Half 1,
adjourn as an MCP server to a chat agent, is complete.)

No concrete first use case is fixed yet; the first cut is a proof of the
loop.

## First-cut architecture

- The driver is a haft-mcp-host `ChatSession`
  (`haft/packages/haft-mcp-host/haft/mcp_host/session.py`) pointed directly
  at the existing adjourn MCP server via `add_mcp_server`. No in-process
  library API is required for the first cut.
- The LLM sees the full adjourn MCP tool surface, including sessions,
  resume hashes, and store names, and chooses which session/suspend point to
  resume itself.
- Loop shape:
  1. Adjourn runs until it suspends.
  2. The driver calls `ChatSession.send()` with the rendered context stack.
  3. The LLM calls tools (e.g. `add_rules`, `push_context`) and then
     resumes.
  4. Repeat on the next suspension.
- `resume` remains a separate tool from `add_rules` (which also resumes), so
  the LLM can resume a suspend point without adding rules.
- `add_rules` keeps its current (non-atomic) behavior for the first cut.

## Handoff to a human

The checkpoint mechanism is the handoff. Both of the following leave the
session suspended and persisted, and return the state plus the `ChatSession`
transcript to the caller:

- `send()` raises `MaxIterationsExceededError` (the iteration budget).
- The model finishes its turn while the session is still suspended.

## Prompt

- Adjourn ships a standard default prompt that instructs the LLM how to
  use adjourn. It is customizable by the caller.
- The "how to use adjourn" text has a single source of truth shared with
  the MCP server's instructions to chat agents.

## Context stack

- **Frames are plain text produced by the LLM**, not Prolog terms. The LLM
  may also manage files whose contents are interpolated into the context.
- **Context files live in the `.adjourn` directory, not in the store.**
  This extends the per-session files the MCP server already keeps.
- **Primitives:**
  - An MCP tool for pushing context. This is the primary channel for LLM
    context.
  - Explicit `push_context/1` / `pop_context/0` builtins at L3. These let
    the program author supply context from within the metainterpreter (e.g.
    the initial prompt stating the session's overall goal).
  - A scoped `with_context/2` will later be built on these primitives; it
    is not part of the first cut.
- **The stack is per-session state outside the resolvent.** It is
  non-logical (like `assert`) and checkpointed with the session.
- **The stack is not unwound on backtracking.** A failed branch leaves the
  stack as it is, and its matching `pop_context` simply never runs. Stale
  frames from failed branches accumulating is accepted for the first cut.
- **Suspension carries no built-in "question" frame.** The program brackets
  a suspension manually: push context, suspend, pop context.
- **Rendering:** at suspend time, the whole stack is rendered and sent to
  the LLM as the `ChatSession.send()` prompt.

## Invariants

- Only one janus instance may run per process; this is the basis of
  suspend/resume. Anything that moves adjourn in-process (e.g. the
  library API below) must respect it.

## Deferred (decided later, own tickets)

- In-process Python library API (session object with init / add_rules /
  resume, same state shapes as the MCP tools), with the MCP server
  refactored into a thin wrapper over it. Accepted in principle; not needed
  for the first cut.
- One-live-session-per-process enforcement, or janus module reset between
  sessions.
- Atomic `add_rules` (validate before consulting, roll back on failure).
- In-process local tools via `ChatSession.add_local_tool` with a narrowed,
  hash-free tool surface.
- Scoped context (`with_context/2`).
- Opt-in compressed summaries of failed branches retained in context. This
  depends on scoped context and on cut, which the metalanguage does not yet
  have.

## Open questions

- The overall mechanism for transferring context between the LLM and
  adjourn is not settled beyond the stack described here.
- Can a frame reference a context file (e.g. `push_context(file(Name))`),
  interpolated at render time, or are files interpolated some other way?
- Does the LLM also get a pop-context MCP tool, and file read/write tools
  for context files?
- Is the transcript returned to the caller only, or also persisted alongside
  the session?
- Rendering format of the stack in the prompt.
- Long-term handling of stale frames left by failed branches.
