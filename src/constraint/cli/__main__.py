"""Main CLI entry point for the constraint checking system."""

import sys
from pathlib import Path
from typing import Optional

import click


@click.group()
@click.version_option(version="0.0.0", prog_name="constraint")
@click.help_option("-h", "--help")
def main() -> None:
    """Constraint checking system for validating code repositories against logical rules.
    
    This tool validates code repositories against user-defined constraints
    using Python extractors and Prolog logic rules.
    """
    pass


@main.command()
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
