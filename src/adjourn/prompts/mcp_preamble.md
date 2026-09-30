# Driving adjourn through MCP

You are connected to the adjourn MCP server. It exposes three tools that
drive a Prolog resolution as a coroutine against disk-backed sessions:

- `adjourn_init(goal)` — create a new session for *goal* and return its
  session id together with the initial projection.
- `adjourn_resume(session)` — advance the session until the next yield,
  solution, or done, and return the updated projection.
- `adjourn_add_rules(session, rules)` — add Prolog rules to the program,
  repoint the session to them, and resume in one call.

The loop: call `adjourn_init` once, then call `adjourn_resume` (or
`adjourn_add_rules` when the program needs new rules) with the returned
session id. The status progresses through `running` → `suspended` /
`solution` and terminates at `done`. A `solution` is a resumable checkpoint
(resuming backtracks for further solutions); only `done` is terminal.
