"""Main CLI entry point for the constraint checking system."""

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

import click

from constraint.meta import init_state, resume_state
from constraint.config import Config
from constraint.store import AggregateRuleSetStore, StoreInfo, build_store_from_config


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
@click.option(
    "--ruleset",
    "ruleset_name",
    required=True,
    help="Ruleset alias or raw hash to pin into the state.",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to the project config file.",
)
def cmd_init(
    query: str,
    state_file: Path,
    ruleset_name: str,
    config_path: Optional[Path],
) -> None:
    """Initialise a new resolution state and write it to STATE_FILE.

    QUERY is a Prolog goal string (e.g. "color(X, Y)").
    STATE_FILE is the path to write the initial JSON state to.

    This command does not invoke Prolog; it simply constructs the initial
    v0 state and writes it as pretty-printed JSON.  Use the ``resume``
    command to drive the meta-interpreter forward.

    Examples:

        constraint init "color(X, Y)" state.json --ruleset coloring
    """
    try:
        state = init_state(query)
        ruleset_hash = _resolve_ruleset_hash(ruleset_name, config_path)
        state["ruleset_hash"] = ruleset_hash
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(state, indent=2) + "\n")
    except (OSError, ValueError, KeyError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@main.command("resume")
@click.argument("state_file", type=click.Path(exists=True, path_type=Path))
@click.argument("output_file", type=click.Path(path_type=Path))
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to the project config file.",
)
def cmd_resume(
    state_file: Path,
    output_file: Path,
    config_path: Optional[Path],
) -> None:
    """Advance a resolution state by one step and write the result.

    STATE_FILE  — path to the current state JSON (must exist).
    OUTPUT_FILE  — path to write the updated state JSON (created or overwritten).

    Reads STATE_FILE, resolves the pinned ruleset hash from the project
    config, calls step/3 once, writes the updated state to OUTPUT_FILE, and
    prints a one-line status summary to stdout.

    If the state is already ``done`` it is written unchanged and exits 0.

    Examples:

        constraint resume state.json next_state.json
        constraint resume state.json state.json   # overwrite in place
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
        ruleset_hash = _state_ruleset_hash(state)
        store = _load_store(config_path)
        clauses = store.clauses_for(ruleset_hash)
        new_state = resume_state(state, clauses)
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


@main.group("store")
def store_group() -> None:
    """Inspect configured ruleset stores."""


@store_group.command("list")
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to the project config file.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["raw", "json"], case_sensitive=False),
    default="raw",
    show_default=True,
    help="Output format.",
)
@click.option(
    "--pretty-print",
    is_flag=True,
    default=False,
    help="Pretty-print JSON output.",
)
def cmd_store_list(
    config_path: Optional[Path],
    output_format: str,
    pretty_print: bool,
) -> None:
    """List configured ruleset stores."""
    store = _load_store(config_path)
    store_info = store.store_info_list()
    if output_format == "json":
        click.echo(_format_store_info_json(store_info, pretty_print))
        return
    click.echo(_format_store_info_raw(store_info))


def _print_status_summary(state: dict[str, Any]) -> None:
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


def _resolve_config_path(config_path: Optional[Path]) -> Path:
    """Resolve the config path from CLI flag, env var, or default."""
    if config_path is not None:
        return config_path
    env_path = os.getenv("CONSTRAINT_CONFIG")
    if env_path:
        return Path(env_path)
    return Path(".constraint/config.yaml")


# TODO: This will contain more than just the store at some point

def _load_store(config_path: Optional[Path]) -> AggregateRuleSetStore:
    """Load the configured aggregate ruleset store."""
    config = Config(_resolve_config_path(config_path))
    return build_store_from_config(config)


def _resolve_ruleset_hash(ruleset_name: str, config_path: Optional[Path]) -> str:
    """Resolve a ruleset alias or raw hash to a known ruleset hash."""
    resolved_config_path = _resolve_config_path(config_path)
    config = Config(resolved_config_path)
    store = build_store_from_config(config)
    if ruleset_name.startswith("@"):
        ruleset_hash = _resolve_system_alias(ruleset_name, store)
    elif (store_name_hash := _resolve_store_name_hash(ruleset_name, store)) is not None:
        ruleset_hash = store_name_hash
    elif ruleset_name in config.aliases:
        ruleset_hash = config.alias_hash(ruleset_name)
    else:
        ruleset_hash = ruleset_name
    if not store.owns(ruleset_hash):
        raise ValueError(
            f"Unknown ruleset '{ruleset_name}': not a configured alias or known hash"
        )
    return ruleset_hash


def _resolve_system_alias(
    name: str,
    store: AggregateRuleSetStore,
) -> str:
    """Resolve a reserved system alias to a ruleset hash."""
    if name == "@top":
        return store.ruleset_hash
    if name != "@first":
        raise ValueError(f"Unknown system alias: {name}")
    first_store_hash = _first_non_system_store_hash(store)
    if first_store_hash is None:
        raise ValueError("System alias '@first' requires at least one configured store")
    return first_store_hash


def _first_non_system_store_hash(store: AggregateRuleSetStore) -> str | None:
    """Return the hash of the first configured non-system store."""
    for store_info in store.store_info_list():
        if store_info.type != "system":
            return store_info.hash
    return None


def _resolve_store_name_hash(
    ruleset_name: str,
    store: AggregateRuleSetStore,
) -> str | None:
    """Resolve a configured per-store name to its ruleset hash."""
    for store_info in store.store_info_list():
        if store_info.name == ruleset_name:
            return store_info.hash
    return None


def _format_store_info_raw(store_info_list: list[StoreInfo]) -> str:
    """Return raw aligned store metadata output."""
    include_name = any(store_info.name is not None for store_info in store_info_list)
    columns: list[tuple[str, list[str]]] = [
        ("type", [store_info.type for store_info in store_info_list]),
    ]
    if include_name:
        columns.append(("name", [store_info.name or "" for store_info in store_info_list]))
    columns.extend(
        [
            ("path", [store_info.path for store_info in store_info_list]),
            ("hash", [store_info.hash for store_info in store_info_list]),
        ]
    )
    widths = [
        max(len(header), *(len(value) for value in values))
        for header, values in columns
    ]
    headers = [
        header.ljust(width)
        for width, (header, _) in zip(widths, columns, strict=False)
    ]
    lines = [" ".join(headers).rstrip()]
    for index in range(len(store_info_list)):
        row = [
            values[index].ljust(width)
            for width, (_, values) in zip(widths, columns, strict=False)
        ]
        lines.append(" ".join(row).rstrip())
    return "\n".join(lines)


def _format_store_info_json(
    store_info_list: list[StoreInfo],
    pretty_print: bool,
) -> str:
    """Return JSON store metadata output."""
    payload = []
    for store_info in store_info_list:
        item = {
            "type": store_info.type,
            "hash": store_info.hash,
        }
        if store_info.path:
            item["path"] = store_info.path
        if store_info.name is not None:
            item["name"] = store_info.name
        payload.append(item)
    if pretty_print:
        return json.dumps(payload, indent=2)
    return json.dumps(payload)


def _state_ruleset_hash(state: dict[str, Any]) -> str:
    """Return the pinned ruleset hash from a state dictionary."""
    ruleset_hash = state.get("ruleset_hash")
    if not isinstance(ruleset_hash, str) or not ruleset_hash:
        raise ValueError("State is missing required 'ruleset_hash'")
    return ruleset_hash



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
