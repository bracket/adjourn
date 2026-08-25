# AGENTS.md — working on `constraint`

Read this before touching any code. `constraint` is a **meta-interpreter
embedded in Prolog embedded in Python**. There are three levels and they are
easy to confuse. Most wasted effort here comes from an agent operating at the
wrong level — especially trying to `use_module`/import at the level between the
meta-interpreter and Python. This document tells you which level you're at and
how the levels load each other.

## The three levels

```
┌─────────────────────────────────────────────────────────────┐
│ L3  Interpreted program        rule/2 facts (user's ruleset) │  ← data
│     - plain Prolog clauses, auto-wrapped as rule/2 facts     │
│     - runs INSIDE the meta-interpreter, not by SWI directly  │
├─────────────────────────────────────────────────────────────┤
│ L2  Host Prolog (SWI-Prolog)   meta.pl + qc_*.pl + user      │  ← engine
│     - the real SWI engine that step/3 actually runs in       │
│     - modules loaded here via :- use_module / janus.consult  │
├─────────────────────────────────────────────────────────────┤
│ L1  Python orchestration       constraint.* package (Janus)  │  ← driver
│     - CLI, Runner, stores, state (de)serialization           │
│     - drives L2 through janus_swi                             │
└─────────────────────────────────────────────────────────────┘
```

- **L1 Python** owns the CLI, the `Runner` singleton, rule/state stores, and
  all serialization. It calls into L2 via `janus_swi` (`janus.consult`,
  `janus.query_once`, `py_call`).
- **L2 host Prolog** is the meta-interpreter itself (`meta.pl`, module
  `constraint_meta`) plus the query-compiler modules (`query_compiler.pl` and
  the `qc_*.pl` family). This is a normal SWI-Prolog program. Prolog module
  machinery (`:- module`, `:- use_module`) lives **here and only here**.
- **L3 interpreted program** is the *user's* logic program: `rule/2` facts that
  `step/3` walks over. L3 is **data**, not code SWI executes directly. It has
  no module system of its own — you do not `use_module` an L3 ruleset, you
  *load it as `rule/2` facts* (see below).

### The failure mode this file exists to prevent

If you find yourself trying to "import a module into the interpreter" —
**stop and identify which interpreter.**

- Want a predicate available to the **meta-interpreter and compiler** (L2)?
  Add `:- use_module(...)` in the relevant `.pl` file and, if it's a new file
  that Python must load, add a `janus.consult` seam in `meta.py` (see
  "Loading Prolog from Python"). This is ordinary SWI module usage.
- Want a predicate available to the **interpreted program** (L3, the user's
  `rule/2` program)? There is **no import**. The meta-interpreter resolves L3
  goals against `user:rule/2` and, failing that, against visible `user:`
  predicates. You make something available to L3 by defining it in `user` (or
  by adding a `reduce_goal/5` clause in `meta.pl` for a new builtin). Do **not**
  reach for `use_module` at this level — it will not do what you expect.

## L2: how the host Prolog is structured

### `meta.pl` — module `constraint_meta`

The canonical meta-interpreter. It lives inside the Python package source tree
so it can be reached via `importlib.resources`. Exports: `init/2`, `step/3`,
`run/3`, `step_packed/4`, `parse_packed_branches/2`, `extract_bindings_str/4`.

Key facts an agent must know:

- **State shape (L2):** `state(Branches)` where `Branches` is a list of
  `branch(Goals)`, and `Goals` is the resolvent (remaining goals). This is the
  Prolog-side representation; the Python-side JSON schema is different (see L1).
- **`rule/2` is `:- multifile user:rule/2`.** Any consulted ruleset adds
  `user:rule/2` facts **without module qualification**. This is the seam
  between L2 and L3.
- **`step/3` is one reduction step**, emitting an `Event`:
  `done` | `solution` | `suspended(Label)` | `checkpoint(Label)`.
- **Goal reduction** (`reduce_goal/5`) handles builtins directly:
  `true`, `(A,B)`, `X=Y`, `yield/1`, `checkpoint/1`, `foreign/3`. The general
  case collects **all** matching `user:rule/2` clauses via `findall/3` (making
  choice points explicit and resumable), else falls back to a visible `user:`
  predicate, else throws `unknown_goal`.
- **`findall/3` severs variable identity.** This is why `bindings` is
  best-effort on `solution` — do not "fix" it casually; there is a tracked
  state-schema change (v0→v1) for propagating `OrigGoal` per-branch.
- New builtins for the interpreted language (L3) are added as `reduce_goal/5`
  clauses **before** the general `user:rule/2` clause.

### `query_compiler.pl` + `qc_*.pl` — the query compiler

`query_compiler.pl` (module `query_compiler`, exports `compile_query/3`) is the
top-level entry; it `:- use_module`s the `qc_*` family:

- `qc_surface.pl`  — `classify_goal/3`, keyed-pair (`:/2`) handling
- `qc_builtins.pl` — `is_builtin/1`, `translate_builtin/2`
- `qc_projection.pl` — `template_of/2`, `projection_cols/2`
- `qc_derived.pl`  — `collect_derived/2`, `is_derived/1`
- `qc_obligations.pl` — `base_obligations/2`

This is a **conventional multi-module SWI program**. Normal `:- use_module`
rules apply. If you add a `qc_*.pl` file, wire it with `:- use_module` in
`query_compiler.pl` **and** add a `janus.consult` seam in `meta.py`.

> Invariant (from mnestic design): every `:/2` in a compiled body is a **keyed
> pair**, never a module qualifier. Disambiguation is centralized in
> `qc_surface:classify_goal/3` — do **not** re-derive `strip_qualification/2`
> or add ad-hoc `:/2` handling elsewhere.

## L1↔L2: loading Prolog from Python (the part agents get wrong)

All Prolog loading happens in **`src/constraint/meta.py`** through explicit,
idempotent `_ensure_*_loaded()` seams gated by a module-level `_consulted` set.
There is no autoloading, no consult-on-import. If a `.pl` file needs to be
present in the SWI engine, it needs a seam here:

- `_ensure_meta_loaded()` → consults `meta.pl` via
  `files("constraint").joinpath("meta.pl")` + `janus.consult`.
- `_ensure_query_compiler_loaded()` → consults `query_compiler.pl` (which
  pulls the `qc_*` modules via its own `use_module` directives — you do **not**
  consult each `qc_*.pl` from Python).
- `_ensure_ruleset_loaded(clauses)` → writes the L3 ruleset to a temp `.pl`
  file and `janus.consult`s it, hash-guarded so unchanged rulesets don't
  reload. **This is how L3 enters the engine — as consulted `rule/2` facts,
  not as a module.**
- `_ensure_foreign_loaded()` → registers `constraint.constraint_foreign` in
  `sys.modules` under the bare name `constraint_foreign` so that the Prolog
  goal `py_call(constraint_foreign:dispatch(Fn, In), Out)` resolves. **The
  `constraint_foreign:` here is a Python module reference for `py_call`, not a
  Prolog module** — another easy confusion.

Rules for adding a new `.pl` file that Python must load:

1. Give it a proper `:- module(...)` header (L2 file) **or** author it as plain
   clauses if it's an L3 ruleset.
2. If it's an L2 support file pulled in by an existing module's `use_module`,
   you usually **don't** need a new Python seam — the parent consult handles it.
3. If Python must consult it directly, add a new `_ensure_<x>_loaded()` seam
   mirroring the ones above (gate on `_consulted`, resolve via
   `importlib.resources`).
4. SWI-Prolog is **stateful within a process**; every seam is idempotent for a
   reason. Preserve that.

## L1: Python orchestration

- **CLI:** `constraint.cli.__main__:main` (Click). Also `python -m
  constraint.cli`. Subcommands include `init` / `resume`.
- **`Runner`** (`runner.py`): implicit singleton (`__new__` + module-global
  `instance_`; `RUNNER_ALWAYS_FORCE_NEW` / `force_new` for tests). Reads the
  pinned ruleset hash from a state dict, resolves clauses via a
  `RuleSetStore`, calls `meta.resume_state`.
- **State (L1 JSON schema, v0):** `{version, original_goal, branches:
  [{goals:[...]}], status}` plus `suspension` (when suspended/checkpoint),
  `bindings` (best-effort on solution), `ruleset_hash` (when pinned). Do not
  conflate this with the L2 `state(Branches)` term — `meta.py` packs/unpacks
  between them via `_build_packed_atom` / `parse_packed_branches`.
- **Packed-atom interop:** Janus can't marshal compound Prolog terms, so the
  L1↔L2 boundary passes **atom strings and flat atom lists** only
  (`step_packed/4`, `parse_packed_branches/2`). Keep new interop on that
  atom-string discipline.
- **Stores:** `constraint.store` — `RuleSetStore`, content-addressed rulesets,
  `hash_clauses`; `MnesticRuleSetStore` (CozoDB adapter, read-only) in
  `store/mnestic_store.py` + `store/mnestic_adapter.py`. Design in
  `docs/mnestic-store.md`.

## Architectural invariant (do not violate)

`constraint` is the **engine**. `enbug` and other consumers push features
**down into their own layer deliberately** rather than accreting inside
`constraint`. When a task tempts you to add consumer-specific behavior to the
meta-interpreter or CLI, that is almost always wrong — flag it rather than
building it.

## Quick "which level am I at?" checklist

- Editing `meta.py`, `runner.py`, `store/`, `cli/`, state JSON → **L1 Python.**
- Editing `meta.pl`, `query_compiler.pl`, `qc_*.pl`; writing `:- module` /
  `:- use_module` → **L2 host Prolog.**
- Writing `rule/2` facts / plain-Prolog rulesets the interpreter *runs* → **L3
  interpreted program** (data; loaded via `_ensure_ruleset_loaded`, never
  `use_module`d).
- Adding a builtin to the *interpreted* language → `reduce_goal/5` clause in
  `meta.pl` (L2), placed before the general `user:rule/2` case.
- "I need to import a module into the interpreter" → re-read **L1↔L2** above and
  determine whether you mean L2 `use_module` (yes, normal) or L3 (no such
  thing).

## Housekeeping

- Python 3.11+, type-hinted; ruff + mypy must pass (`ruff check src/constraint`,
  `mypy src/constraint`). Private helpers `_`-prefixed and colocated.
- Tests: pytest under `src/tests/`; add regression tests with new behavior.
- Prolog: `:- module` headers on L2 files, meaningful predicate names,
  declarative bodies. Test predicates independently before wiring through Janus.
- Note: the older `.github/copilot-instructions.md` describes an earlier
  "constraint-checking" framing and is **stale** relative to the
  meta-interpreter design; prefer this document.
