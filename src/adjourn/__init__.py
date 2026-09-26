"""A suspendable, resumable Prolog meta-interpreter for long-running queries that interleave machine and human/LLM resolution."""

# Parser submodule is available as adjourn.parser
from adjourn import parser

__all__ = ["parser"]
