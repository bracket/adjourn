# constraint — Project Overview + MVP Specification

## 1) Purpose

`constraint` is a Prolog-first (SWI-Prolog) executable specification and completion-checking framework intended to support agentic coding workflows (e.g., GitHub Copilot Coding Agent). It provides:

- A **fact schema** for describing a repository/corpus (code, docs, tests, CLI, etc.)
- A plugin-based **extraction pipeline** that derives *observed* facts from a working tree
- A human-authored **expected (“true”) knowledge base** + reusable **spec packs**
- A **constraint engine** that compares observed vs expected and reports actionable violations
- A single **golden command** that gates “done” (exit code 0 iff completion criteria pass)

Primary workflow invariant: a task is complete only when `bin/golden` succeeds.

## 2) Core Model

### 2.1 Facts
All extracted information is represented as *ground terms* under a single predicate:

- `fact(Term).` where `Term` is structured (recommended)  
  - Example: `fact(file(path("src/importer.py"))).`

Facts are divided logically into two sets:

- **Observed KB**: facts derived from the repo by extractors
- **Expected KB**: facts asserted by humans (project truth set/spec)

### 2.2 Provenance (separate from facts)
Track where each observed fact came from (and optionally confidence/metadata):

- `prov(FactTerm, source(extractor(Name), Location, Confidence, Timestamp)).`

### 2.3 Constraints and Completion
Specs are written as Prolog rules that produce:

- `violation(V).` terms describing missing/incoherent requirements
- `done.` succeeds iff no violations exist

Diagnostics should be:
- human-readable summary
- plus machine-readable (prefer JSON lines) to support coding agents

## 3) MVP “Golden Command” Contract

`bin/golden` MUST:

1. Run extractors to build the **Observed KB**
2. Load the **Expected KB** (human truth set)
3. Evaluate all active **spec packs** to derive `violation/1`
4. Print diagnostics (human + machine)
5. Exit **0** iff `done` holds; else exit **nonzero**

This command is the only completion gate; CI and agents should treat it as authoritative.

## 4) Repository Layout (Proposed)

```
constraint/
  README.md
  LICENSE
  Makefile

  bin/
    golden                 # gating command: extract -> check -> report

  src/
    core/
      schema.pl            # canonical fact shapes + constructors/helpers
      kb.pl                # load/store KB + provenance utilities
      diff.pl              # expected vs observed diffs + conflict utilities
      explain.pl           # render violations into actionable diagnostics
      runner.pl            # orchestrates extraction + checking + reporting

    extractors/
      extractor_fs.pl      # filesystem enumeration + basic parsing
      extractor_git.pl     # git diff/touched files + branch context (minimal)
      extractor_docs.pl    # README/doc headings/examples parsing (minimal)

    specs/
      packs/
        definition_of_done.pl   # MVP pack: docs+tests+cli+code coherence
        cli_coherence.pl        # optional (can be folded into DoD)
        docs_examples.pl        # optional (can be folded into DoD)

    cli/
      main.pl              # CLI entrypoint used by bin/golden

  data/
    expected/
      repo_expected.pl     # project-specific expected facts (human authored)
    snapshots/
      observed_YYYYMMDD.pl # optional KB snapshots for regression/testing

  tests/
    test_schema.pl
    test_kb.pl
    test_diff.pl
    test_runner.pl
```

## 5) Extractor Plugin Contract (MVP)

Define an extractor registry and execution order:

- `extractor(Name, Priority, Goal).`

Each extractor:
- inspects a repo root
- emits `observed/1` facts (or `fact/1` tagged as observed)
- emits `prov/2` provenance entries

Initial extractors (MVP):
- `extractor_fs`: enumerate files, basic file classification
- `extractor_git`: compute touched files (`git diff --name-only`), branch info
- `extractor_docs`: parse markdown headings and code-fence examples (lightweight)

Language-aware AST extractors (Python/TS/etc.) are explicitly **out of scope** for MVP.

## 6) Fact Schema (MVP targets ~10–15 shapes)

Use structured terms under `fact/1`, e.g.:

- `file(path(Path))`
- `touched(path(Path))`
- `doc_section(file(File), heading(Heading))`
- `doc_example(file(File), snippet(SnippetIdOrHash))`
- `cli(command(Cmd), subcommand(Sub))`
- `cli_flag(command(Cmd), flag(Flag))`
- `test(file(File), name(TestName))`
- `exports(module(Mod), symbol(Sym))` *(placeholder until AST extractors exist)*
- `build_target(name(Target))`
- `todo_blocking(path(Path))` or `no_todo_blocking(path(Path))`

NOTE: For MVP, keep schema stable and additive; do not require deep language parsing.

## 7) Spec Packs (Policy Modules) vs Repo Expected Facts (Truth Set)

### 7.1 Repo Truth Set
`data/expected/repo_expected.pl` contains human-coded expectations:

- `expected(Term).`
- optional allowlist rules: `allowed(Term).`

### 7.2 Spec Packs
`src/specs/packs/*.pl` are reusable policy modules that derive:

- `violation(V).`
- `done.`

They compare expected vs observed and enforce coherence rules.

## 8) MVP “Definition of Done” Spec Pack

Implement `definition_of_done.pl` with violations in three categories:

### 8.1 Missing obligations (expected not observed)
- `violation(missing(ExpectedTerm)).`

### 8.2 Unexpected artifacts (observed not permitted)
- `violation(unexpected(ObservedTerm)).`
- `allowed/1` can be “expected OR permitted by policy” to avoid brittle whitelists.

### 8.3 Incoherence (cross-artifact consistency)
Examples (MVP should include a small handful):
- Docs mention CLI flag that is not present in extracted CLI flags
- Expected CLI subcommand exists but there are no tests (or no doc section)
- Touched modules contain blocking TODO markers
- Doc examples do not match discovered CLI surface (best-effort)

`done` succeeds iff no `violation/1` solutions exist.

## 9) Diagnostics Output (Agent-Friendly)

`bin/golden` must print:
- a human-readable summary (counts + top violations)
- plus machine-readable JSON lines, one per violation, e.g.:

```json
{"type":"missing","term":"doc_section(file(README.md),heading(Import))"}
{"type":"unexpected","term":"file(path(tmp/debug.txt))"}
{"type":"incoherent","detail":"docs_reference_missing_cli_flag","flag":"--dry-run"}
```

Exit code:
- `0` if `done.`
- `1` (or nonzero) otherwise

## 10) MVP Acceptance Criteria

The MVP is complete when:

1. `bin/golden` runs end-to-end on a sample repo and gates success/failure via exit code
2. Extractors generate a nontrivial Observed KB (files + docs + git touched)
3. Expected KB loads cleanly and can express basic obligations
4. The DoD spec pack produces clear violations for missing/unexpected/incoherent cases
5. Tests (plunit) cover:
   - schema helpers
   - KB load/store
   - diff logic
   - runner behavior (golden pass/fail)
6. Output includes JSON lines suitable for consumption by a coding agent

## 11) Non-Goals (MVP)

- Full AST extraction (Python/TS/etc.) beyond minimal heuristics
- Datalog/Mercury performance optimizations
- Interactive UI; the primary interface is `bin/golden`
- Complex probabilistic reasoning or nonmonotonic semantics beyond basic Prolog rules
