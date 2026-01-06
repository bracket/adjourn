# constraint

**A Prolog-first executable specification and completion-checking framework for agentic coding workflows**

## Purpose

`constraint` is a SWI-Prolog-based framework designed to support agentic coding workflows (e.g., GitHub Copilot Coding Agent) by providing hard checking of AI outputs using logic programming paradigms. It establishes a formal, verifiable "definition of done" for software tasks by comparing observed repository state against expected specifications.

The core principle: **a task is complete only when `bin/golden` succeeds** (exit code 0).

## Core Concepts

### Fact Schema
All information about the repository is represented as structured Prolog ground terms under the `fact/1` predicate:
- `fact(file(path("src/importer.py")))`
- `fact(doc_section(file("README.md"), heading("Installation")))`
- `fact(cli(command("golden"), subcommand("check")))`

### Extractors (Observation Pipeline)
Plugin-based extraction pipeline that derives **observed facts** from the working tree:
- **extractor_fs**: Enumerates files and performs basic file classification
- **extractor_git**: Computes touched files and branch context
- **extractor_docs**: Parses markdown headings and code examples

### Knowledge Bases
The system maintains two distinct knowledge bases:

1. **Observed KB**: Facts derived from the repository by extractors
2. **Expected KB**: Human-authored facts that define project requirements and specifications (stored in `data/expected/`)

### Spec Packs (Policy Modules)
Reusable policy modules (in `src/specs/packs/`) that encode constraints and coherence rules:
- Compare expected vs observed facts
- Derive `violation/1` terms for missing, unexpected, or incoherent artifacts
- Define `done` predicate that succeeds only when no violations exist

### Golden Command
`bin/golden` is the single authoritative completion gate that:
1. Runs all extractors to build the Observed KB
2. Loads the Expected KB (human truth set)
3. Evaluates all active spec packs to derive violations
4. Prints diagnostics (human-readable + machine-readable JSON)
5. Exits 0 iff `done` holds; nonzero otherwise

## Repository Layout

```
constraint/
  README.md                      # This file
  bin/
    golden                       # Gating command: extract → check → report
  
  src/
    core/
      schema.pl                  # Canonical fact shapes + helpers
      kb.pl                      # Load/store KB + provenance utilities
      diff.pl                    # Expected vs observed comparison
      explain.pl                 # Violation rendering
      runner.pl                  # Orchestration
    
    extractors/
      extractor_fs.pl            # Filesystem enumeration
      extractor_git.pl           # Git context
      extractor_docs.pl          # Documentation parsing
    
    specs/
      packs/
        definition_of_done.pl    # MVP pack: docs+tests+cli+code coherence
  
  data/
    expected/
      repo_expected.pl           # Project-specific expected facts (human-authored)
    snapshots/                   # Optional KB snapshots for regression testing
  
  tests/                         # Prolog unit tests (plunit)
  
  docs/
    constraint_project_overview_mvp.md  # Detailed specification
```

## Getting Started

### For Contributors

1. **Read the detailed specification**: See [`docs/constraint_project_overview_mvp.md`](docs/constraint_project_overview_mvp.md) for the complete project specification and MVP requirements

2. **Understand the workflow invariant**: All work is gated by `bin/golden` succeeding

3. **Key implementation areas**:
   - **Extractors**: Add new observation capabilities in `src/extractors/`
   - **Spec Packs**: Define new constraint rules in `src/specs/packs/`
   - **Expected KB**: Author project requirements in `data/expected/`

4. **Development cycle**:
   - Make changes to code, docs, or tests
   - Run `bin/golden` to check completion status
   - Address violations reported by the constraint engine
   - Iterate until `bin/golden` exits 0

### For AI Coding Agents

See [`.github/copilot-instructions.md`](.github/copilot-instructions.md) for agent-specific guidance on interacting with the constraint system.

## Detailed Documentation

For the complete project specification, including:
- Fact schema details (~10-15 shapes for MVP)
- Extractor plugin contract
- Constraint engine behavior
- Diagnostics output format
- MVP acceptance criteria

See: [`docs/constraint_project_overview_mvp.md`](docs/constraint_project_overview_mvp.md)

## License

TBD
