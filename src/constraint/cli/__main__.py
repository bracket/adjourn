"""Main CLI entry point for the constraint checking system."""

import json
import sys
from pathlib import Path
from typing import Optional

import click

from constraint.meta import init_state, resume_state


@click.group(invoke_without_command=True)
@click.version_option(version="0.0.0", prog_name="constraint")
@click.help_option("-h", "--help")
@click.pass_context
def main(ctx: click.Context) -> None:
    """Constraint checking system for validating code repositories against logical rules.
    
    This tool validates code repositories against user-defined constraints
    using Python extractors and Prolog logic rules.
    """
    # If no subcommand is provided, show help
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@main.command("init")
@click.argument("query")
@click.argument("state_file", type=click.Path(path_type=Path))
def cmd_init(query: str, state_file: Path) -> None:
    """Initialise a new resolution state and write it to STATE_FILE.

    QUERY is a Prolog goal string (e.g. "color(X, Y)").
    STATE_FILE is the path to write the initial JSON state to.

    This command does not invoke Prolog; it simply constructs the initial
    v0 state and writes it as pretty-printed JSON.  Use the ``resume``
    command to drive the meta-interpreter forward.

    Examples:

        constraint init "color(X, Y)" state.json
    """
    try:
        state = init_state(query)
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(state, indent=2) + "\n")
    except OSError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@main.command("resume")
@click.argument("state_file", type=click.Path(exists=True, path_type=Path))
@click.argument("ruleset_file", type=click.Path(exists=True, path_type=Path))
@click.argument("output_file", type=click.Path(path_type=Path))
def cmd_resume(
    state_file: Path,
    ruleset_file: Path,
    output_file: Path,
) -> None:
    """Advance a resolution state by one step and write the result.

    STATE_FILE  — path to the current state JSON (must exist).
    RULESET_FILE — path to a Prolog .pl file with rule/2 facts (must exist).
    OUTPUT_FILE  — path to write the updated state JSON (created or overwritten).

    Reads STATE_FILE, consults RULESET_FILE, calls step/3 once, writes the
    updated state to OUTPUT_FILE, and prints a one-line status summary to
    stdout.

    If the state is already ``done`` it is written unchanged and exits 0.

    Examples:

        constraint resume state.json rules.pl next_state.json
        constraint resume state.json rules.pl state.json   # overwrite in place
    """
    try:
        raw = state_file.read_text()
        state = json.loads(raw)
    except OSError as exc:
        click.echo(f"Error reading {state_file}: {exc}", err=True)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        click.echo(f"Error parsing {state_file}: {exc}", err=True)
        sys.exit(1)

    try:
        new_state = resume_state(state, ruleset_file)
    except Exception as exc:  # noqa: BLE001  — Janus/Prolog errors are opaque
        click.echo(f"Error during resume: {exc}", err=True)
        sys.exit(1)

    try:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(json.dumps(new_state, indent=2) + "\n")
    except OSError as exc:
        click.echo(f"Error writing {output_file}: {exc}", err=True)
        sys.exit(1)

    _print_status_summary(new_state)


def _print_status_summary(state: dict) -> None:
    """Print a one-line human-readable summary of the state status.

    Args:
        state: A v0 state dictionary.  Recognised keys:

            - ``status`` (str): one of ``"done"``, ``"solution"``,
              ``"suspended"``, or ``"running"``.
            - ``bindings`` (dict, optional): variable bindings present when
              ``status`` is ``"solution"``.
            - ``suspension`` (dict, optional): dict with a ``"label"`` key
              present when ``status`` is ``"suspended"``.
            - ``branches`` (list, optional): remaining branch list used when
              ``status`` is ``"running"``.
    """
    status = state.get("status", "unknown")
    if status == "done":
        click.echo("status: done")
    elif status == "solution":
        bindings = state.get("bindings", {})
        if bindings:
            pairs = ", ".join(f"{k}={v}" for k, v in bindings.items())
            click.echo(f"status: solution — bindings: {pairs}")
        else:
            click.echo("status: solution")
    elif status == "suspended":
        label = state.get("suspension", {}).get("label", "")
        click.echo(f'status: suspended — label: "{label}"')
    elif status == "running":
        branches = len(state.get("branches", []))
        click.echo(f"status: running — {branches} branch(es) remaining")
    else:
        click.echo(f"status: {status}")



@main.command("complete")
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    default=None,
    help="Write completion script to FILE instead of stdout",
)
@click.option(
    "--shell",
    type=click.Choice(["bash", "zsh", "fish"], case_sensitive=False),
    default="bash",
    help="Shell type for completion script (default: bash)",
)
def complete(output: Optional[Path], shell: str) -> None:
    """Generate shell completion script.
    
    This command generates a shell completion script that enables
    tab-completion for the constraint CLI.
    
    Examples:
    
        # Output to stdout
        constraint complete
        
        # Save to file
        constraint complete -o ~/.local/share/bash-completion/completions/constraint
        
    After generating the script, source it in your shell configuration:
    
        # For bash, add to ~/.bashrc:
        source ~/.local/share/bash-completion/completions/constraint
        
        # Or for immediate use:
        eval "$(constraint complete)"
    """
    # Generate completion script using Click's built-in support
    shell_lower = shell.lower()
    
    # Get the completion script from Click
    if shell_lower == "bash":
        completion_script = _generate_bash_completion()
    elif shell_lower == "zsh":
        completion_script = _generate_zsh_completion()
    elif shell_lower == "fish":
        completion_script = _generate_fish_completion()
    else:
        click.echo(f"Error: Unsupported shell type: {shell}", err=True)
        sys.exit(1)
    
    # Add header with usage instructions
    header = _get_completion_header(shell_lower)
    full_script = header + "\n\n" + completion_script
    
    if output:
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(full_script)
            click.echo(f"Completion script written to: {output}")
        except OSError as e:
            click.echo(f"Error writing to {output}: {e}", err=True)
            sys.exit(1)
    else:
        click.echo(full_script)


def _get_completion_header(shell: str) -> str:
    """Generate header comment for completion script."""
    if shell == "bash":
        return """# Bash completion script for constraint CLI
#
# Installation:
#   1. Save this file to a completion directory, e.g.:
#      constraint complete -o ~/.local/share/bash-completion/completions/constraint
#
#   2. Source it in your ~/.bashrc:
#      source ~/.local/share/bash-completion/completions/constraint
#
#   3. Or load it immediately:
#      eval "$(constraint complete)"
#
# Usage:
#   After installation, type 'constraint <TAB>' to see available commands."""
    elif shell == "zsh":
        return """# Zsh completion script for constraint CLI
#
# Installation:
#   1. Save this file to a directory in your $fpath, e.g.:
#      constraint complete --shell zsh -o ~/.zsh/completions/_constraint
#
#   2. Add to your ~/.zshrc (if not already present):
#      fpath=(~/.zsh/completions $fpath)
#      autoload -Uz compinit && compinit
#
#   3. Or load it immediately:
#      eval "$(constraint complete --shell zsh)"
#
# Usage:
#   After installation, type 'constraint <TAB>' to see available commands."""
    elif shell == "fish":
        return """# Fish completion script for constraint CLI
#
# Installation:
#   1. Save this file to Fish's completion directory:
#      constraint complete --shell fish -o ~/.config/fish/completions/constraint.fish
#
#   2. Or load it immediately:
#      constraint complete --shell fish | source
#
# Usage:
#   After installation, type 'constraint <TAB>' to see available commands."""
    else:
        return f"# Completion script for {shell}"


def _generate_bash_completion() -> str:
    """Generate bash completion script using Click's internal support."""
    # Click provides completion support through the shell_complete module
    # We need to generate the appropriate script for bash
    prog_name = "constraint"
    
    return f"""_{prog_name.upper()}_COMPLETE=bash_source constraint"""


def _generate_zsh_completion() -> str:
    """Generate zsh completion script using Click's internal support."""
    prog_name = "constraint"
    
    return f"""#compdef constraint

_{prog_name.upper()}_COMPLETE=zsh_source constraint"""


def _generate_fish_completion() -> str:
    """Generate fish completion script using Click's internal support."""
    prog_name = "constraint"
    
    return f"""_{prog_name.upper()}_COMPLETE=fish_source constraint"""


if __name__ == "__main__":
    main()
