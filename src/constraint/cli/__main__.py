"""Main CLI entry point for the constraint checking system."""

import json
import os
import sys
from pathlib import Path
from typing import Any

import click

from constraint.config import Config
from constraint.constraint_foreign import load_foreign_plugins
from constraint.runner import Runner
from constraint.state import init_state, set_resume_hash
from constraint.state_store import JsonFileStateStore
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
    default="@top",
    help="Ruleset alias or raw hash to pin into the state.",
)
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
def cmd_init(
    query: str,
    state_file: Path,
    ruleset_name: str,
    config_path: Path | None,
    output_format: str,
    pretty_print: bool,
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
        config = Config(_resolve_config_path(config_path))
        load_foreign_plugins(config.foreign_plugins)
        store = build_store_from_config(config)
        state = init_state(query, ruleset_name, store, config)

        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(state, indent=2) + "\n")

        # Also persist through the state seam (writes .constraint/state_init.json).
        JsonFileStateStore().store_init_state(state)

        if output_format == "json":
            projection = _build_state_projection(state)
            click.echo(_format_state_json(projection, pretty_print))

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
def cmd_resume(
    state_file: Path,
    output_file: Path,
    config_path: Path | None,
    output_format: str,
    pretty_print: bool,
) -> None:
    """Advance a resolution state by one step and write the result.

    STATE_FILE  — path to the current state JSON (must exist).
    OUTPUT_FILE  — path to write the updated state JSON (created or overwritten).

    Reads STATE_FILE, resolves the pinned ruleset hash from the project config,
    drives the resume loop (auto-continuing across checkpoints and halting at
    the next yield/solution/done via Runner.run), writes the resulting state to
    OUTPUT_FILE, and prints a one-line status summary to stdout.

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
        config = Config(_resolve_config_path(config_path))
        load_foreign_plugins(config.foreign_plugins)
        store = build_store_from_config(config)
        runner = Runner(store)
        new_state = runner.run(state)
        if "resume_hash" in state:
            new_state["resume_hash"] = state["resume_hash"]
    except Exception as exc:  # noqa: BLE001  — Janus/Prolog errors are opaque
        click.echo(f"Error during resume: {exc}", err=True)
        sys.exit(1)

    try:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(json.dumps(new_state, indent=2) + "\n")
    except OSError as exc:
        click.echo(f"Error writing {output_file}: {exc}", err=True)
        sys.exit(1)

    if output_format == "json":
        projection = _build_state_projection(new_state)
        click.echo(_format_state_json(projection, pretty_print))
    else:
        _print_status_summary(new_state)


@main.command("set-resume")
@click.argument("ruleset_name")
@click.argument("state_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-o",
    "--output",
    "output_file",
    type=click.Path(path_type=Path),
    default=None,
    help="Output file path (default: rewrite state_file in place). Use '-' for stdout.",
)
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
def cmd_set_resume(
    ruleset_name: str,
    state_file: Path,
    output_file: Path | None,
    config_path: Path | None,
    output_format: str,
    pretty_print: bool,
) -> None:
    """Set or update the resume_hash in a state file.

    RULESET_NAME is a ruleset alias, store name, system alias, or raw hash.
    STATE_FILE is the path to the existing state JSON.

    The resolved ruleset hash is written as the ``resume_hash`` field.
    The ``ruleset_hash`` field is left untouched.

    Examples:

        constraint set-resume other-rules state.json
        constraint set-resume other-rules state.json -o updated_state.json
        constraint set-resume other-rules state.json -o -
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
        config = Config(_resolve_config_path(config_path))
        store = build_store_from_config(config)
        new_state = set_resume_hash(state, ruleset_name, store, config)
    except (ValueError, KeyError, OSError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    serialized = json.dumps(new_state, indent=2) + "\n"

    if output_file is None:
        state_file.write_text(serialized)
    elif str(output_file) != "-":
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(serialized)

    if output_format == "json":
        projection = _build_state_projection(new_state)
        click.echo(_format_state_json(projection, pretty_print))
    elif str(output_file) == "-":
        click.echo(serialized, nl=False)

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
    config_path: Path | None,
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


@main.group("rules")
def rules_group() -> None:
    """Manage rule stores."""


@rules_group.command("add")
@click.argument("path", type=click.Path(exists=False))
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
def cmd_rules_add(
    path: str,
    config_path: Path | None,
    output_format: str,
    pretty_print: bool,
) -> None:
    """Register a file-based ruleset store.

    PATH is the path to a ruleset file to register as a ``file`` store in
    the project config.  The path is stored verbatim in the config file.

    Examples:

        constraint rules add rules/my_rules.pl
        constraint rules add rules/my_rules.pl --format json
    """
    resolved_config_path = _resolve_config_path(config_path)

    if not os.path.exists(path):
        click.echo(f"Error: Path '{path}' does not exist.", err=True)
        sys.exit(1)

    try:
        try:
            config = Config(resolved_config_path)
        except FileNotFoundError:
            config = Config.__new__(Config)
            config.path = Path(resolved_config_path)
            config._data = {"stores": [], "aliases": {}, "foreign": {}}
            config._create_if_missing()

        store_config = config.append_file_store(path)
    except (OSError, ValueError, KeyError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    if output_format == "json":
        status = "added" if store_config.changed else "unchanged"
        payload = {"status": status, "store": dict(store_config)}
        if pretty_print:
            click.echo(json.dumps(payload, indent=2))
        else:
            click.echo(json.dumps(payload))
        return

    if store_config.changed:
        click.echo(f"Added file store '{store_config['name']}' at path '{path}'.")
    else:
        click.echo(f"Store with path '{path}' already registered.")


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

    ruleset_hash = state.get("ruleset_hash")
    if isinstance(ruleset_hash, str) and ruleset_hash:
        click.echo(f"ruleset_hash: {ruleset_hash[:12]}")
        resume_hash = state.get("resume_hash")
        if isinstance(resume_hash, str) and resume_hash:
            click.echo(f"resume_hash:  {resume_hash[:12]}")


def _resolve_config_path(config_path: Path | None) -> Path:
    """Resolve the config path from CLI flag, env var, or default."""
    if config_path is not None:
        return config_path
    env_path = os.getenv("CONSTRAINT_CONFIG")
    if env_path:
        return Path(env_path)
    return Path(".constraint/config.yaml")


# TODO: This will contain more than just the store at some point

def _load_store(config_path: Path | None) -> AggregateRuleSetStore:
    """Load the configured aggregate ruleset store."""
    config = Config(_resolve_config_path(config_path))
    return build_store_from_config(config)


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


def _build_state_projection(state: dict[str, Any]) -> dict[str, Any]:
    """Build a JSON projection dict from a state dictionary.

    The projection contains exactly these keys:

    - ``status`` — from ``state["status"]``.
    - ``label`` — from ``state.get("suspension", {}).get("label")``; ``None``
      when the state is not suspended or has no label.
    - ``ruleset_hash`` — from ``state.get("ruleset_hash")``.
    - ``resume_hash`` — from ``state.get("resume_hash")``; ``None`` when absent.

    Args:
        state: A v0 state dictionary.

    Returns:
        A dict with the four projection keys.
    """
    return {
        "status": state.get("status"),
        "label": state.get("suspension", {}).get("label"),
        "ruleset_hash": state.get("ruleset_hash"),
        "resume_hash": state.get("resume_hash"),
    }


def _format_state_json(
    projection: dict[str, Any],
    pretty_print: bool,
) -> str:
    """Return JSON serialization of a state projection.

    Args:
        projection: A state projection dict (from :func:`_build_state_projection`).
        pretty_print: If ``True``, produce indented JSON.

    Returns:
        A JSON string.
    """
    if pretty_print:
        return json.dumps(projection, indent=2)
    return json.dumps(projection)



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
def complete(output: Path | None, shell: str) -> None:
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
    completion_script = generate_completion(shell_lower)
    
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


def generate_completion(shell: str) -> str:
    """Generate the completion script body for SHELL.

    Emits the source-able eval form rather than the rendered completion
    function, so the emitted script stays valid across CLI versions and does
    not require a `constraint` binary on PATH at generation time.

    Args:
        shell: One of "bash", "zsh", or "fish".

    Returns:
        The completion script body as a string.
    """
    if shell == "zsh":
        return (
            "#compdef constraint\n"
            "\n"
            'eval "$(_CONSTRAINT_COMPLETE=zsh_source constraint)"\n'
        )
    if shell == "fish":
        return "_CONSTRAINT_COMPLETE=fish_source constraint | source\n"
    return 'eval "$(_CONSTRAINT_COMPLETE=bash_source constraint)"\n'


if __name__ == "__main__":
    main()
