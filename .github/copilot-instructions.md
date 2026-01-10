````instructions
# Copilot Instructions (Template)

## Context
- This repository is a starting point; refine these instructions after the onboarding chat in `scratch/onboard.chat`.
- Follow the quickspec workflow: issues live in `issues/` using `issue-template.md`; creation guidance in `issue-creator.md`. Scratch conversations and notes stay in `scratch/` (see `scratch/chatter_readme.md` for chat file structure).

## Workflow Expectations
- Read the relevant issue before coding; validate requirements, acceptance criteria, and forbidden modifications.
- Keep changes minimal and reviewable; prefer small, focused PRs.
- Record design decisions and open questions in the working `.chat` transcript or the issue.

## Python Standards
- Target Python 3.11+ unless the project narrows this later.
- Follow PEP 8 and PEP 257; type-hint all functions and methods.
- Prefer free functions over static methods unless state management requires otherwise.
- Avoid nested try/except; handle errors close to the source with specific exception types.
- Prefer comprehensions over imperative loops when readable.
- Keep helpers private (prefix with `_`) and colocated beneath their primary consumers.
- Export public APIs explicitly via `__all__` once the surface stabilizes.
- Maintain consistent docstrings on public modules, classes, and methods; very short, self-explanatory helpers can omit docstrings.
- No trailing whitespace; keep files ASCII unless the domain requires otherwise.

## Testing
- Use pytest for tests under `src/tests/`.
- Add regression tests with new behaviors; keep fixtures small and explicit.

## Tooling
- Debug with `debugpy` on port 5678 (see `.vscode/launch.json`). Use `.vscode/bin/vsdebug` after pointing `MODULE` to the CLI entry point.
- Update `.vscode/settings.json` and `extensions.json` only when necessary for the project; keep defaults minimal.

## After Onboarding
- Replace template names (`project_name`, placeholder versions, etc.).
- Tighten or extend these standards per project constraints (e.g., supported Python versions, dependency policies, linting rules).
````
