# Copilot Instructions: constraint

## Project Overview
`constraint` is a Python-based constraint checking system that validates code repositories against user-defined logical rules. The system combines Python 3.11+ for orchestration and CLI with SWI-Prolog (via Janus Python integration) as the logic query engine.

### Architecture
- **Python Layer**: Orchestration, CLI (using Click), knowledge extraction from repositories
- **Prolog Layer**: Constraint definitions, logical queries, validation rules via SWI-Prolog/Janus
- **Package Structure**: `constraint` (main package) with `constraint.cli` (CLI submodule)
- **Core Workflow**:
  1. Extract observed facts from code repositories (Python extractors)
  2. Load expected facts defined in Prolog constraint files
  3. Query Prolog engine to check observed facts against expected facts
  4. Return compliance/violation feedback to LLM agents or users

## Context
- Follow the quickspec workflow: issues live in `issues/` using `issue-template.md`; creation guidance in `issue-creator.md`. Scratch conversations and notes stay in `scratch/` (see `scratch/chatter_readme.md` for chat file structure).
- This project enables LLM-assisted coding with formal constraint checking capabilities.

## Workflow Expectations
- Read the relevant issue before coding; validate requirements, acceptance criteria, and forbidden modifications.
- Keep changes minimal and reviewable; prefer small, focused PRs.
- Record design decisions and open questions in the working `.chat` transcript or the issue.
- When implementing constraint checking features, ensure bidirectional flow between Python extractors and Prolog validators.

## Python Standards
- Target Python 3.11+ for full compatibility with Janus/SWI-Prolog integration.
- Follow PEP 8 and PEP 257; type-hint all functions and methods.
- Prefer free functions over static methods unless state management requires otherwise.
- Avoid nested try/except; handle errors close to the source with specific exception types.
- Prefer comprehensions over imperative loops when readable.
- Keep helpers private (prefix with `_`) and colocated beneath their primary consumers.
- Export public APIs explicitly via `__all__` once the surface stabilizes.
- Maintain consistent docstrings on public modules, classes, and methods; very short, self-explanatory helpers can omit docstrings.
- No trailing whitespace; keep files ASCII unless the domain requires otherwise.

## Prolog Integration Standards
- Use Janus Python API for all Python-Prolog interactions.
- Structure Prolog files with clear predicate documentation.
- Use meaningful predicate names that reflect constraint semantics (e.g., `violates_naming_convention/2`, `has_required_test/1`).
- Keep Prolog constraint definitions declarative; avoid imperative patterns.
- Separate fact definitions from constraint rules for clarity.
- Test Prolog predicates independently before integration with Python.

## CLI Structure (Click)
- Use Click framework for all CLI commands.
- Structure commands hierarchically: main command with subcommands for different operations.
- Main entry point: `constraint.cli.__main__:main` (accessible via `constraint` command after installation)
- Can also be invoked as `python -m constraint.cli`
- Provide clear help text for all commands and options.
- Use consistent option naming (e.g., `--repo-path`, `--constraint-file`, `--verbose`).
- Implement graceful error handling with informative messages.
- Return appropriate exit codes: 0 for success, non-zero for errors/violations.

### Bash Completion
- The CLI supports shell completion via the `constraint complete` command
- Generate completion scripts for bash, zsh, or fish: `constraint complete --shell [bash|zsh|fish]`
- Output to stdout by default or to a file with `-o/--output` option
- Generated scripts include commented installation instructions
- To enable immediately: `eval "$(constraint complete)"`

## Knowledge Extraction Workflow
- **Extractors**: Python modules that scan repositories and generate facts.
- **Fact Format**: Structure extracted data as dictionaries/objects suitable for Prolog query.
- **Extraction Pipeline**: Composable extractors (file system, Git metadata, code structure, documentation).
- **Output**: Convert Python data structures to Prolog-compatible terms via Janus.

## Constraint Checking Workflow
- **Expected Facts**: User-defined Prolog files describing required repository properties.
- **Observed Facts**: Dynamically extracted from the repository by Python extractors.
- **Validation**: Prolog queries compare observed vs. expected, generating violation reports.
- **Feedback**: Structure violations as actionable messages for developers or LLM agents.

## Testing
- Use pytest for tests under `src/tests/`.
- Add regression tests with new behaviors; keep fixtures small and explicit.
- Test Python-Prolog integration with mock Prolog queries when appropriate.
- Include end-to-end tests for CLI commands.
- Test extractors with sample repository structures.
- Validate constraint checking logic with known-good and known-bad scenarios.

## Tooling
- **Click**: CLI framework for command-line interface
- **mypy**: Static type checking (development dependency)
- **ruff**: Fast Python linter (development dependency)
- **pytest**: Testing framework
- Debug with `debugpy` on port 5678 (see `.vscode/launch.json`). Use `.vscode/bin/vsdebug` which is configured to run `python -m constraint.cli`.
- Update `.vscode/settings.json` and `extensions.json` only when necessary for the project; keep defaults minimal.

### Linting and Type Checking
- Run type checking: `mypy src/constraint`
- Run linting: `ruff check src/constraint`
- All code must pass both mypy and ruff checks before commit

## Dependencies
- **Click**: CLI framework (>=8.1.0) - installed
- **mypy**: Static type checking (>=1.0.0) - development dependency
- **ruff**: Fast Python linter (>=0.1.0) - development dependency
- **pytest**: Testing framework (>=7.4.0) - development dependency
- **Janus**: SWI-Prolog Python integration (requires SWI-Prolog 9.1+) (planned)
- Additional dependencies should be minimal and justified.

## Development Notes
- This is an early-stage project; implementation details will evolve.
- Prioritize clear interfaces between Python and Prolog layers.
- Design extractors to be modular and composable.
- Keep constraint definitions simple and maintainable.
