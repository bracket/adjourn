# Graph coloring, written by an LLM

[`demo.py`](demo.py) solves the same problem as the
[CLI graph coloring example](../graph_coloring/), but an LLM writes the
program. It starts from a seed program, [`llm_seed.pl`](llm_seed.pl), that
defines `coloring/4` in terms of an `implementation/4` that does not exist
yet:

```prolog
coloring(A, B, C, D) :- implement_program, fail.
coloring(A, B, C, D) :- implementation(A, B, C, D).

implement_program :- yield(implement_program).
```

Resolving `coloring(A, B, C, D)` suspends at `implement_program`. The adjourn
driver hands that suspension, plus a short problem statement, to the LLM,
which calls `add_rules` with clauses defining `implementation/4`. The driver
then resumes the session against `@top`, the ruleset containing every
registered rule, so the LLM's rules are in scope: the first `coloring/4`
clause fails, the second calls `implementation/4`, and the first solution
comes back.

## Running it

Install the MCP extra, which carries the driver:

```bash
pip install "adjourn[mcp] @ git+https://github.com/bracket/adjourn.git"
```

Then edit the constants at the top of `demo.py` to point at your LLM:

- `MODEL` and `BASE_URL`: the model name and endpoint. The endpoint must
  speak the OpenAI Responses API.
- `API_KEY_ENV`: the name of the environment variable holding your API key,
  sent as a Bearer token. Set it to `None` for endpoints that need no key.

```bash
export OPENAI_API_KEY=...
python demo.py
```

The demo prints the rules the LLM wrote, followed by the first solution.

## Files left behind

Each run wipes and recreates `llm_run/` (gitignored) next to `demo.py`:

- `llm_run/.adjourn/config.yaml`: the project config, registering
  `../llm_seed.pl` and each rules file the LLM added.
- `llm_run/rules_NNN.pl`: the rules the LLM wrote, one file per `add_rules`
  call.
- `llm_run/.adjourn/mcp-sessions/<id>.json`: the session state.
- `llm_run/.adjourn/mcp-sessions/<id>.context.json`: the driver's context
  stack (the problem statement and any notes the LLM pushed).
- `llm_run/.adjourn/state_init.json` and
  `llm_run/.adjourn/states/state_implement_program.json`: snapshots of the
  initial state and of the state at the `implement_program` suspension.
