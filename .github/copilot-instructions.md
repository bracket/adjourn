# Copilot Instructions for constraint Repository

## Project Context

You are working on **constraint**, a Prolog-first (SWI-Prolog) executable specification and completion-checking framework designed to support agentic coding workflows. This project uses logic programming paradigms to provide hard checking of AI outputs against formal specifications.

## Core Purpose

The constraint system ensures that software tasks meet explicit, verifiable completion criteria by:
- Extracting **observed facts** from the repository (code, docs, tests, CLI, etc.)
- Comparing against **expected facts** authored by humans (the "truth set")
- Running constraint rules (spec packs) to identify violations
- Reporting actionable diagnostics for missing, unexpected, or incoherent artifacts

## Critical Workflow Invariant

**⚠️ A task is complete ONLY when `bin/golden` succeeds (exit code 0).**

This is the single authoritative completion gate. You MUST:
1. Run `bin/golden` before claiming task completion
2. Address all violations reported by the constraint engine
3. Iterate until `bin/golden` exits with code 0
4. Never bypass or mock this check

## Detailed Specification

The authoritative project specification is located at:
**`docs/constraint_project_overview_mvp.md`**

Read this document to understand:
- Complete fact schema definitions
- Extractor plugin contracts
- Spec pack structure and rules
- Expected vs observed KB architecture
- Diagnostics output format
- MVP acceptance criteria

## Key System Components

### 1. Extractors (`src/extractors/`)
Plugins that observe the repository and emit facts:
- **extractor_fs.pl**: Filesystem enumeration and basic file classification
- **extractor_git.pl**: Git diff context (touched files, branch info)
- **extractor_docs.pl**: Markdown parsing (headings, code examples)

When adding extractors:
- Follow the `extractor(Name, Priority, Goal)` contract
- Emit `observed/1` facts
- Include `prov/2` provenance entries
- Keep MVP scope lightweight (no deep AST parsing)

### 2. Expected KB (`data/expected/`)
Human-authored specifications defining project requirements:
- **repo_expected.pl**: Contains `expected(Term)` facts
- Defines what MUST exist in the repository
- May include `allowed(Term)` for permissible variations

When updating:
- Use structured terms matching the fact schema
- Be explicit and specific
- Document the rationale for each expectation

### 3. Spec Packs (`src/specs/packs/`)
Reusable policy modules that enforce constraints:
- **definition_of_done.pl**: MVP pack for docs+tests+cli+code coherence
- Compare expected vs observed facts
- Derive `violation(V)` terms
- Define `done` predicate (succeeds iff no violations)

Violation categories:
- `violation(missing(ExpectedTerm))`: Expected but not observed
- `violation(unexpected(ObservedTerm))`: Observed but not allowed
- `violation(incoherent(...))`: Cross-artifact inconsistencies

### 4. Core Engine (`src/core/`)
Foundation modules:
- **schema.pl**: Canonical fact shapes and constructors
- **kb.pl**: Knowledge base load/store + provenance
- **diff.pl**: Expected vs observed comparison utilities
- **explain.pl**: Violation rendering for diagnostics
- **runner.pl**: Orchestrates extraction → checking → reporting

## How to Interact with the Constraint System

### When Implementing New Features

1. **Before starting**:
   - Check `data/expected/repo_expected.pl` for relevant expectations
   - Review applicable spec packs in `src/specs/packs/`
   - Understand what facts your changes should produce

2. **During implementation**:
   - Write code/docs/tests as specified
   - If adding new capabilities, update extractors to observe them
   - If defining new requirements, add expected facts

3. **Before completion**:
   - Run `bin/golden` to check constraint satisfaction
   - Review violation diagnostics (both human and JSON output)
   - Address each violation category:
     - **missing**: Add the required artifact
     - **unexpected**: Remove it or add to allowed list
     - **incoherent**: Fix cross-artifact inconsistencies

4. **Iterate until**:
   - `bin/golden` exits 0
   - All violations resolved
   - Task meets formal definition of done

### When Fixing Bugs or Issues

1. **Reproduce with golden**:
   - Run `bin/golden` to see current violation state
   - Identify which constraints are failing

2. **Make minimal fixes**:
   - Address the specific violations
   - Avoid introducing new violations

3. **Verify with golden**:
   - Confirm `bin/golden` exits 0 after fixes

### When Adding Tests

- Tests should validate constraint engine behavior
- Use Prolog unit testing framework (plunit)
- Cover: schema helpers, KB operations, diff logic, runner behavior
- Test both positive cases (done succeeds) and negative cases (violations detected)

### Diagnostics Output

`bin/golden` produces two output formats:

1. **Human-readable**: Summary with counts and top violations
2. **Machine-readable**: JSON lines (one per violation), e.g.:
   ```json
   {"type":"missing","term":"doc_section(file(README.md),heading(Import))"}
   {"type":"unexpected","term":"file(path(tmp/debug.txt))"}
   {"type":"incoherent","detail":"docs_reference_missing_cli_flag","flag":"--dry-run"}
   ```

Parse JSON output for programmatic violation handling.

## Development Guidelines

### DO:
- Always consult `docs/constraint_project_overview_mvp.md` for authoritative details
- Run `bin/golden` frequently during development
- Keep fact schema stable and additive
- Write clear, structured Prolog predicates
- Document complex constraint rules
- Use provenance tracking for observed facts

### DON'T:
- Bypass or mock the `bin/golden` check
- Modify expected facts without understanding the requirement
- Add deep AST parsing (out of scope for MVP)
- Break existing extractors or spec packs
- Ignore incoherence violations
- Assume task completion without `bin/golden` exit code 0

## File Locations Quick Reference

| Purpose | Location |
|---------|----------|
| Detailed spec | `docs/constraint_project_overview_mvp.md` |
| Expected facts | `data/expected/repo_expected.pl` |
| Spec packs | `src/specs/packs/*.pl` |
| Extractors | `src/extractors/*.pl` |
| Core engine | `src/core/*.pl` |
| Golden command | `bin/golden` |
| Tests | `tests/*.pl` |

## Questions or Uncertainty?

When unclear about:
- **Fact schema**: Check `src/core/schema.pl` and the spec document
- **What to extract**: Review `src/extractors/` examples and extractor contract
- **What's expected**: Read `data/expected/repo_expected.pl`
- **Constraint rules**: Examine `src/specs/packs/definition_of_done.pl`
- **Overall architecture**: Re-read `docs/constraint_project_overview_mvp.md`

Always prefer explicit verification via `bin/golden` over assumptions about completion.
