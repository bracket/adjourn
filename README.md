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

### Prerequisites

- Python 3.11 or higher
- pip (Python package manager)
- SWI-Prolog 9.2.9+ (for Janus Python integration)

### Installing from Source

```bash
# Clone the repository
git clone https://github.com/bracket/constraint.git
cd constraint

# Install in development mode with all dependencies
pip install -e ".[dev]"
```

This will install:
- The `constraint` package in editable mode
- Click framework for the CLI
- Development tools (mypy, ruff, pytest)
- The `constraint` command-line tool

## Usage

### Command-Line Interface

The constraint CLI provides commands for validating repositories against constraints:

```bash
# Display help and available commands
constraint --help

# Display version information
constraint --version
```

### Shell Completion

The CLI supports shell completion for bash, zsh, and fish. This enables tab-completion of commands and options.

#### Installing Bash Completion

```bash
# Generate and save the completion script
constraint complete -o ~/.local/share/bash-completion/completions/constraint

# Source it in your ~/.bashrc
echo 'source ~/.local/share/bash-completion/completions/constraint' >> ~/.bashrc

# Or enable it immediately for the current session
eval "$(constraint complete)"
```

#### Installing Zsh Completion

```bash
# Create completions directory if it doesn't exist
mkdir -p ~/.zsh/completions

# Generate and save the completion script
constraint complete --shell zsh -o ~/.zsh/completions/_constraint

# Add to your ~/.zshrc (if not already present)
echo 'fpath=(~/.zsh/completions $fpath)' >> ~/.zshrc
echo 'autoload -Uz compinit && compinit' >> ~/.zshrc

# Or enable it immediately for the current session
eval "$(constraint complete --shell zsh)"
```

#### Installing Fish Completion

```bash
# Generate and save to Fish's completion directory
constraint complete --shell fish -o ~/.config/fish/completions/constraint.fish

# Fish automatically loads completions from this directory
# Or enable it immediately for the current session
constraint complete --shell fish | source
```

### Future CLI Commands

> **Note**: The following commands are planned but not yet implemented.

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
# Install the package in development mode with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type checking
mypy src/constraint

# Linting
ruff check src/constraint

# Run the CLI in development mode
python -m constraint.cli --help
```

## Project Status

This is an **early-stage project** under active development. Current status:

- [x] Project concept and architecture defined
- [x] Repository structure established
- [x] Python package structure
- [x] CLI framework (Click) with bash completion
- [x] Type checking (mypy) and linting (ruff) configured
- [ ] Janus/SWI-Prolog integration
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
