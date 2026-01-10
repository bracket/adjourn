### **Issue Title:**
Onboard project documentation for constraint repo

---

## **Objective**
Update the `README.md` and `.github/copilot-instructions.md` files to clearly introduce the constraint project, explain its purpose (hard checking of AI outputs using logic programming paradigms), and prepare contributors and coding agents for implementation.

---

## **Background / Context**
The constraint repo is a Prolog-first (SWI-Prolog) executable specification and completion-checking framework intended to support agentic coding workflows. The project provides:

- A fact schema for describing a repository/corpus (code, docs, tests, CLI, etc.)
- A plugin-based extraction pipeline that derives observed facts from a working tree
- A human-authored expected ("true") knowledge base + reusable spec packs
- A constraint engine that compares observed vs expected and reports actionable violations
- A single "golden command" (`bin/golden`) that gates task completion (exit code 0 iff criteria pass)

The primary workflow invariant is: **a task is complete only when `bin/golden` succeeds.**

Detailed specification is available in:
- `docs/constraint_project_overview_mvp.md`

---

## **Inputs**
List all required inputs and their locations.

- Code to reference:
  - `docs/constraint_project_overview_mvp.md` — authoritative project specification
  - `README.md` — file to be updated
  - `.github/copilot-instructions.md` — file to be updated

---

## **Requirements**
Define explicit expectations.

**Functional requirements:**
- `README.md` must provide a high-level project introduction including:
  - Project name and purpose
  - Core concepts (fact schema, extractors, expected/observed KB, spec packs, golden command)
  - Link to the detailed specification (`docs/constraint_project_overview_mvp.md`)
  - Brief overview of the proposed repository layout
  - Getting started / next steps for contributors
- `.github/copilot-instructions.md` must provide guidance for AI coding agents including:
  - Project context and purpose
  - Reference to the detailed spec
  - Key workflow invariant (task complete only when `bin/golden` succeeds)
  - Guidance on where to find expected facts, spec packs, and extractors
  - Instructions for how agents should interact with the constraint system

**Technical constraints:**
- Changes are limited to `README.md` and `.github/copilot-instructions.md` only
- No other files should be created or modified

**Coding standards:**
- Use clear, concise Markdown formatting
- Ensure documentation is accessible to both human contributors and AI coding agents

**Forbidden modifications:**
- Do **not** modify any files other than:
  - `README.md`
  - `.github/copilot-instructions.md`

---

## **Tasks for Copilot**
Provide a deterministic, ordered set of actions.

1. Read `docs/constraint_project_overview_mvp.md` to extract authoritative project details
2. Draft updates to `README.md` with:
   - Project title and purpose statement
   - Core concepts overview (fact schema, extractors, observed/expected KB, spec packs, golden command)
   - Link to detailed specification
   - Proposed repository layout summary
   - Getting started section for contributors
3. Draft updates to `.github/copilot-instructions.md` with:
   - Project context and purpose for AI agents
   - Reference to the detailed spec document
   - Key workflow invariant explanation
   - Guidance on constraint system interaction
4. Create a PR with the changes limited to the two target files
5. Include a clear PR description linking to `docs/constraint_project_overview_mvp.md`
6. Request review/approval once the PR is ready

---

## **Acceptance Criteria**
The issue is complete when all of the following are met:

- A PR is submitted that updates `.github/copilot-instructions.md` and `README.md`
- The `README.md` clearly presents the project purpose, core concepts, and references the detailed spec
- The `.github/copilot-instructions.md` provides AI agents with project context and workflow guidance
- The updates reference the detailed specification at `docs/constraint_project_overview_mvp.md`
- The PR contents are limited to the two intended onboarding documentation files
- Updates outline preparatory steps required to implement the project

---

## **Verification Checklist (for the Agent)**
The agent must validate the following before closing the issue:

- [ ] `README.md` has been updated with project introduction and core concepts
- [ ] `.github/copilot-instructions.md` has been updated with AI agent guidance
- [ ] Both files reference `docs/constraint_project_overview_mvp.md` as the detailed specification
- [ ] No files other than `README.md` and `.github/copilot-instructions.md` were modified
- [ ] All tasks in "Tasks for Copilot" are complete
- [ ] All acceptance criteria are satisfied
- [ ] PR description clearly links to the specification document
