# constraint

**A suspendable, resumable Prolog meta-interpreter with content-addressed
rulesets and a Python orchestration layer, for long-running queries that
interleave machine and human/LLM resolution.**

## Overview

`constraint` runs logic-programming queries that are not expected to finish in
a single sitting. A query can pause mid-resolution, persist its exact state to
disk, and resume later — possibly in a different process, possibly after a
human or an LLM has supplied an answer that the program could not derive on its
own. This makes it a substrate for building long-lived problem-solving agents
whose reasoning is a mix of automated deduction and external intervention.

Concretely, the system provides:

- A **continuation-style meta-interpreter** over ordinary Prolog clauses, whose
  entire resolution state (the set of open branches and their remaining goals)
  is an explicit, serializable value rather than hidden in the Prolog engine's
  stack.
- **Explicit suspension and resumption**: a running query can yield control at
  declared points, be written to disk, and be picked back up exactly where it
  left off.
- **Content-addressed rulesets**: the interpreted program is identified by a
  hash of its clauses, so a persisted query pins the precise ruleset it was
  running against and rulesets can be composed and versioned deterministically.

> **Note:** `constraint` is a general meta-interpreter with tracking and
> suspension. Earlier revisions of this project were aimed at a narrower
> repository-validation use case; that framing is obsolete and does not
> describe the current system.

## Architecture

`constraint` deliberately splits responsibilities between a Prolog kernel and a
Python orchestration layer. It is **not** intended to run as a standalone
Prolog program — Python is an integral part of the design, owning I/O,
persistence, ruleset dispatch, and the driver loop.

**Prolog kernel.** Owns unification, the resolvent and branch machinery, the
single-step reducer, and the suspend/resume events. Its resolution state is a
plain Prolog term — a list of branches, each holding its remaining goals — so
the whole state serializes cleanly and carries no dependence on the engine's
implicit choice-point stack.

**Python orchestration.** Owns the driver loop, ruleset storage and dispatch,
content hashing and composition, state persistence, and the interface to
external actors. Python steps the kernel forward, decides what to do at each
event, and mediates every side-effecting or externally-answered goal.

The two communicate through an embedded SWI-Prolog runtime. Kernel-to-Python
callouts (for example, resolving a goal whose answer lives in a database or is
produced by generated code) happen inline and automatically; they are **not**
suspensions. Suspension is reserved for genuine external-intervention points.

## Core concepts

### State, branches, and stepping

A query's state is a set of **branches**, each of which is a list of goals still
to be resolved (its resolvent). The interpreter advances one reduction at a
time. Because branches are explicit data, choice points that a conventional
Prolog engine would keep on its internal stack are instead first-class,
inspectable, and serializable — which is what makes pausing and resuming
possible.

### Events

Each step produces one of a small set of events:

- **solution** — a branch resolved completely; a result (with any variable
  bindings) is available.
- **suspended** — resolution reached a declared external-intervention point and
  cannot proceed without outside input. The state is persisted and control
  returns to the caller.
- **checkpoint** — a declared save point. The state is persisted, but
  resolution continues automatically; checkpoints exist so long runs can be
  durably snapshotted without stopping.
- **done** — all branches are exhausted.

The distinction between **suspend** and **checkpoint** is the distinction
between "stop and wait for someone" and "save your place and keep going." A
callout into Python is neither: it resolves immediately and the interpreter
proceeds without emitting either event.

### Rulesets and content addressing

The interpreted program is a set of clauses identified by a content hash. The
hash is computed over a canonical form of the clauses — variables are
renumbered by first occurrence and cosmetic differences (whitespace, variable
names) are ignored — so clauses that differ only in naming hash identically,
while structural differences are preserved.

Content addressing gives two properties the persistence model depends on: a
persisted query can pin the exact ruleset it ran against, and the same hash
always denotes the same clauses, forever. That immutability is what lets a cold
resume in a fresh process reconstruct precisely the program the query was using.

### Composition and aliases

Rulesets compose into ordered **chains**. A chain concatenates its members'
clauses in order, suppresses repeated members, and takes a composite hash over
its member hashes — associative and deterministic, so the same composition
always yields the same identifier. Chains can nest, and their members can live
in different storage backends.

Configuration can attach human-readable **aliases** to rulesets, and a small
set of reserved names (such as an alias for the top-level aggregate) make the
common rulesets convenient to refer to from the command line.

## Installation

Requires Python 3.11+ and an embedded SWI-Prolog runtime (via Janus).

```bash
git clone https://github.com/bracket/constraint.git
cd constraint
pip install -e ".[dev]"
```

This installs the `constraint` package and its command-line tool.

## Usage

The command-line interface drives the interpreter through persisted state
files. The essential workflow is *initialise a query*, then *resume it* one
externally-observable step at a time.

```bash
# Create an initial state for a query, pinned to a ruleset, written to disk.
constraint init "<goal>" state.json --ruleset <alias-or-hash>

# Advance the query: auto-continues across checkpoints and halts at the next
# solution, suspension, or exhaustion. Writes the resulting state out.
constraint resume state.json next_state.json
```

`init` is pure bookkeeping — it constructs and writes the starting state
without invoking Prolog. `resume` drives the kernel forward, persisting state at
checkpoints and suspensions, and prints a one-line status summary (solution with
bindings, suspended with a label, still running, or done). Persisted state is
JSON, so a suspended query can be inspected, hand-edited, or resolved by an
external actor between resume calls.

Configured rulesets can be inspected with:

```bash
constraint store list
```

## Relationship to other projects

`constraint` is designed to be embedded as the resolution engine for other
systems. In particular, a separate coding harness is being built on top of it,
encoding an agent loop as rules and using suspension points as the seams where
an LLM or a human resolves goals the program cannot discharge automatically. The
harness is a consumer of `constraint`, not part of it; `constraint` itself is
agnostic about what drives it.

## Project status

`constraint` is under active development. The core is functional: the
meta-interpreter, explicit suspend/resume, content-addressed rulesets with chain
composition, and the state-persistence layer are all in place and driven through
the CLI. Additional ruleset backends, a richer query surface, and lower-level
documentation aimed at automated agents are in progress.

## Development

```bash
pip install -e ".[dev]"

pytest              # run the test suite
mypy src/constraint # type checking
ruff check src/constraint  # linting
```

## Contributing

Contributions are welcome. Keep changes focused, and add tests for new
behavior.
