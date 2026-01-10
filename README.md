# constraint

Logic Programming Framework for Agentic Coding Workflows

## Purpose

`constraint` is a Python/SWI-Prolog-based framework designed to constraint AI agents

## Core Concepts

### Knowledge Bases
We care about two types of knowledge bases (KBs):

1. **Observed KB**: Facts derived from the repository by extractors
2. **Expected KB**: Human-authored facts that define project requirements and specifications

### Fact Schema
All information about the repository will be represented as structured Prolog ground terms under the `fact/1` predicate:
- `fact(file(path("src/importer.py")))`
- `fact(doc_section(file("README.md"), heading("Installation")))`
- `fact(cli(command("golden"), subcommand("check")))`


### Extractors (Observation Knowledge)
Extraction pipeline that derives **observed facts** (our observed knowledge base) from the working tree.  Examples might be:
- **extractor_fs**: Enumerates files and performs basic file classification
- **extractor_git**: Computes touched files and branch context
- **extractor_docs**: Parses markdown headings and code examples


### Spec Packs (Expected Knowledge)
Reusable policy modules that encode constraints and coherence rules:
- Used to compare expected vs observed facts
- Derive `violation/1` terms for missing, unexpected, or incoherent artifacts
- Will define `done` predicate that succeeds only when no violations exist


### Getting started
TBD
