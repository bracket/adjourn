# constraint

**A Python-based constraint checking system for validating code repositories against logical rules**

## Overview

`constraint` is a framework that combines Python 3.11+ with SWI-Prolog (via Janus integration) to validate code repositories against user-defined logical constraints. This system enables LLM-assisted coding workflows with formal verification, ensuring that code changes comply with project-specific requirements and conventions.

### What It Does

The constraint system:
- **Extracts facts** from code repositories (file structure, Git metadata, code patterns, documentation)
- **Defines constraints** using Prolog's declarative logic programming
- **Validates repositories** by comparing observed facts against expected constraints
- **Reports violations** with actionable feedback for developers or AI coding agents

### Use Cases

- Enforce coding standards and architectural patterns
- Validate documentation completeness and consistency
- Check test coverage and code organization requirements
- Ensure compliance with project-specific conventions
- Gate task completion in AI-assisted development workflows

## Architecture

### Two-Layer Design

1. **Python Layer** (Orchestration & Extraction)
   - CLI interface using Click framework
   - Knowledge extractors that scan repositories
   - Integration with SWI-Prolog via Janus
   - Package structure: `constraint` with `constraint.cli` submodule

2. **Prolog Layer** (Constraint Logic)
   - Constraint definitions in declarative logic
   - Query engine for validation
   - Composable rule sets ("spec packs")

### Core Workflow

```
Repository → [Python Extractors] → Observed Facts
                                         ↓
User Constraints → [Prolog Rules] → Expected Facts
                                         ↓
                            [Prolog Query Engine]
                                         ↓
                        Compliance Report / Violations
```

## Core Concepts

### Knowledge Bases

The system works with two types of knowledge:

1. **Observed KB**: Facts automatically extracted from the repository
   - File paths and types
   - Git history and branch context
   - Code structure and patterns
   - Documentation sections

2. **Expected KB**: Human-authored constraints defining requirements
   - Naming conventions
   - Required files or patterns
   - Documentation requirements
   - Test coverage expectations

### Fact Schema

Repository information is represented as structured Prolog ground terms:

```prolog
fact(file(path("src/constraint/cli.py")))
fact(doc_section(file("README.md"), heading("Installation")))
fact(function(module("constraint.cli"), name("validate")))
fact(test_exists(module("constraint.extractors")))
```

### Extractors (Observation)

Python modules that scan repositories and generate observed facts:

- **File System Extractor**: Enumerates files and classifies types
- **Git Extractor**: Analyzes commit history and branch context
- **Code Extractor**: Parses source code structure
- **Documentation Extractor**: Processes markdown and docstrings

Extractors are composable and can be extended for project-specific needs.

### Spec Packs (Expected Constraints)

Reusable Prolog modules encoding validation rules:

- Define expected repository properties
- Compare observed vs. expected facts
- Generate `violation/1` terms for non-compliance
- Implement a `compliant/0` predicate that succeeds only when all constraints pass

Example constraint:
```prolog
% Every Python module must have a corresponding test file
violation(missing_test(Module)) :-
    fact(file(path(ModulePath))),
    python_module(ModulePath, Module),
    \+ fact(test_file(Module)).
```

## Installation

> **Note**: This project is in early development. Installation instructions will be finalized as the implementation progresses.

### Prerequisites

- Python 3.11 or higher
- SWI-Prolog 9.1+ (for Janus Python integration)

### Planned Installation Steps

```bash
# Install SWI-Prolog with Janus support
# (Platform-specific instructions TBD)

# Clone the repository
git clone https://github.com/bracket/constraint.git
cd constraint

# Install Python dependencies
pip install -e .
```

## Usage

> **Note**: These are conceptual examples. The CLI and API are still being designed.

### Command-Line Interface

```bash
# Validate a repository against constraints
constraint check --repo-path /path/to/repo --constraints my_constraints.pl

# List available extractors
constraint extractors list

# Run specific extractors
constraint extract --repo-path /path/to/repo --extractor filesystem,git

# Validate with custom spec pack
constraint check --repo-path . --spec-pack python_project
```

### Python API (Conceptual)

```python
from constraint import ConstraintChecker
from constraint.extractors import FileSystemExtractor, GitExtractor

# Initialize checker with extractors
checker = ConstraintChecker(
    extractors=[FileSystemExtractor(), GitExtractor()],
    constraint_file="constraints.pl"
)

# Validate repository
result = checker.validate("/path/to/repo")

if result.is_compliant:
    print("✓ All constraints satisfied")
else:
    for violation in result.violations:
        print(f"✗ {violation}")
```

## Development Workflow

This project follows the **quickspec workflow**:

### Issue Management
- Issues live in `issues/` directory
- Use `issues/issue-template.md` for new issues
- See `issues/issue-creator.md` for guidance

### Scratch Work
- Conversations and notes go in `scratch/`
- Follow structure in `scratch/chatter_readme.md`
- Use `.chat` files for working transcripts

### Testing
- Tests located in `src/tests/`
- Run with `pytest`
- Add regression tests for new features

### Development Setup

```bash
# Run tests
pytest

# Type checking (planned)
mypy src/constraint

# Linting (planned)
ruff check src/constraint
```

## Project Status

This is an **early-stage project** under active development. Current status:

- [x] Project concept and architecture defined
- [x] Repository structure established
- [ ] Python package structure
- [ ] Janus/SWI-Prolog integration
- [ ] CLI framework (Click)
- [ ] Core extractors
- [ ] Constraint validation engine
- [ ] Example spec packs
- [ ] Documentation and examples

## Contributing

Contributions are welcome! Please:

1. Review issues in `issues/` directory
2. Follow coding standards in `.github/copilot-instructions.md`
3. Write tests for new features
4. Keep PRs focused and minimal

## License

TBD
