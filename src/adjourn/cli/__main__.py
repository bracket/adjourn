"""Main CLI entry point for adjourn."""

import json
import os
import sys
from pathlib import Path
from typing import Any

import click
from click.shell_completion import get_completion_class

from adjourn.adjourn_foreign import load_foreign_plugins
from adjourn.config import Config, create_config_file
from adjourn.state import (
    DEFAULT_FIELDS,
    VERBOSE_FIELDS,
    init_state,
    set_resume_hash,
    state_projection,
)
from adjourn.state_store import JsonFileStateStore
from adjourn.store import (
    AggregateRuleSetStore,
    RuleSetStore,
    StoreInfo,
    build_store_from_config,
    build_store_from_config_entry,
    resolve_store_path,
)


@click.group(invoke_without_command=True)
@click.version_option(version="0.0.0", prog_name="adjourn")
@click.help_option("-h", "--help")
@click.pass_context
def main(ctx: click.Context) -> None:
    """adjourn: a suspendable, resumable Prolog meta-interpreter.

    Queries run until they reach a solution, a suspension point that needs
    outside input, or exhaustion; state persists to disk between resumes.
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

        adjourn init "color(X, Y)" state.json --ruleset coloring
    """
    try:
        config = _open_config(config_path)
        load_foreign_plugins(config.foreign_plugins)
        store = build_store_from_config(config)
        state = init_state(query, ruleset_name, store, config)

        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(state, indent=2) + "\n")

        # Also persist through the state seam (writes .adjourn/state_init.json).
        JsonFileStateStore().store_init_state(state)

        if output_format == "json":
            projection = state_projection(state, DEFAULT_FIELDS)
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
    """Resume a resolution state until the next yield, solution, or done
    (continuing through checkpoints) and write the result.

    STATE_FILE  — path to the current state JSON (must exist).
    OUTPUT_FILE  — path to write the updated state JSON (created or overwritten).

    Reads STATE_FILE, resolves the pinned ruleset hash from the project config,
    drives the resume loop (auto-continuing across checkpoints and halting at
    the next yield/solution/done via Runner.run), writes the resulting state to
    OUTPUT_FILE, and prints a one-line status summary to stdout.

    If the state is already ``done`` it is written unchanged and exits 0.

    Examples:

        adjourn resume state.json next_state.json
        adjourn resume state.json state.json   # overwrite in place
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
        config = _open_config(config_path)
        load_foreign_plugins(config.foreign_plugins)
        store = build_store_from_config(config)
        from adjourn.runner import Runner

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
        projection = state_projection(new_state, DEFAULT_FIELDS)
        click.echo(_format_state_json(projection, pretty_print))
    else:
        click.echo(_format_state_raw(new_state))


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

    Under ``--format json``, stdout receives the shared state projection
    used by ``resume``. Under the default ``raw`` format, stdout behavior is
    unchanged: in-place and file outputs are silent, while ``-o -`` writes the
    rewritten full state JSON.

    Examples:

        adjourn set-resume other-rules state.json
        adjourn set-resume other-rules state.json -o updated_state.json
        adjourn set-resume other-rules state.json -o -
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
        config = _open_config(config_path)
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
        projection = state_projection(new_state, DEFAULT_FIELDS)
        click.echo(_format_state_json(projection, pretty_print))
    elif str(output_file) == "-":
        click.echo(serialized, nl=False)


@main.group("state")
def state_group() -> None:
    """Inspect resolution state files."""


@state_group.command("show")
@click.argument("state_file", type=click.Path(path_type=Path))
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
@click.option("-v", "--verbose", is_flag=True, help="Show branches and full hashes.")
def cmd_state_show(
    state_file: Path,
    output_format: str,
    pretty_print: bool,
    verbose: bool,
) -> None:
    """Show the state stored in STATE_FILE."""
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            raise ValueError("expected a JSON object")
    except OSError as exc:
        click.echo(f"Error reading {state_file}: {exc}", err=True)
        sys.exit(1)
    except (json.JSONDecodeError, ValueError) as exc:
        click.echo(f"Error parsing {state_file}: {exc}", err=True)
        sys.exit(1)

    if output_format == "json":
        fields = VERBOSE_FIELDS if verbose else DEFAULT_FIELDS
        click.echo(_format_state_json(state_projection(state, fields), pretty_print))
    else:
        click.echo(_format_state_raw(state, verbose=verbose))


@main.group("config")
def config_group() -> None:
    """Inspect and initialize project configuration."""


@config_group.command("init")
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to the project config file.",
)
@click.option("-f", "--force", is_flag=True, help="Overwrite an existing config file.")
def cmd_config_init(config_path: Path | None, force: bool) -> None:
    """Create an empty project config file."""
    path = _resolve_config_path(config_path)
    try:
        create_config_file(path, force=force)
    except FileExistsError:
        click.echo(f"Error: config file already exists: {path}", err=True)
        sys.exit(1)
    except OSError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    click.echo(f"Initialized config: {path}")


@config_group.command("show")
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
def cmd_config_show(
    config_path: Path | None,
    output_format: str,
    pretty_print: bool,
) -> None:
    """Show resolved config, stores, aliases, and foreign plugins."""
    path = _resolve_config_path(config_path)
    try:
        config = _open_config(path)
    except (OSError, ValueError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    store_rows: list[dict[str, Any]] = []
    built_stores: list[RuleSetStore] = []
    has_store_errors = False
    for store_config in config.store_configs:
        item: dict[str, Any] = {
            "type": store_config["type"],
            "path": store_config["path"],
            "resolved_path": str(
                resolve_store_path(config, store_config["path"]).resolve()
            ),
        }
        for key in ("name", "prolog", "support"):
            if key in store_config:
                item[key] = store_config[key]
        try:
            store = build_store_from_config_entry(config, store_config)
            store_info = _gather_store_info(store)[0]
            item["type"] = store_info.type
            item["hash"] = store_info.hash
            if store_info.name is not None:
                item["name"] = store_info.name
            built_stores.append(store)
        except Exception as exc:  # noqa: BLE001 — store backends fail independently
            item["hash"] = None
            item["error"] = str(exc)
            has_store_errors = True
        store_rows.append(item)

    # The aggregate is assembled from the already-built stores so no rules
    # file is parsed twice.  It is unavailable whenever any store failed.
    aggregate: AggregateRuleSetStore | None = None
    top_error: str | None = None
    if has_store_errors:
        top_error = "one or more configured stores could not be built"
    else:
        try:
            aggregate = AggregateRuleSetStore(built_stores)
            _ = aggregate.ruleset_hash
        except Exception as exc:  # noqa: BLE001 — composite construction can fail per backend
            aggregate = None
            top_error = str(exc)
            has_store_errors = True

    aliases = [
        {
            "name": name,
            "hash": ruleset_hash,
            # Ownership is unknown (None) when the aggregate is unavailable.
            "owned": aggregate.owns(ruleset_hash) if aggregate is not None else None,
        }
        for name, ruleset_hash in config.aliases.items()
    ]

    payload: dict[str, Any] = {
        "config": str(path.resolve()),
        "base_dir": str(config.base_dir.resolve()),
        "top": aggregate.ruleset_hash if aggregate is not None else None,
    }
    if top_error is not None:
        payload["top_error"] = top_error
    payload.update(
        {
            "stores": store_rows,
            "aliases": aliases,
            "plugins": config.foreign_plugins,
        }
    )

    if output_format == "json":
        click.echo(json.dumps(payload, indent=2 if pretty_print else None))
    else:
        click.echo(_format_config_raw(payload))
    if has_store_errors:
        sys.exit(1)


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
    try:
        store = _load_store(config_path)
        store_info = _gather_store_info(store)
    except Exception as exc:  # noqa: BLE001 — store backends fail in backend-specific ways
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
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

        adjourn rules add rules/my_rules.pl
        adjourn rules add rules/my_rules.pl --format json
    """
    resolved_config_path = _resolve_config_path(config_path)

    if not os.path.exists(path):
        click.echo(f"Error: Path '{path}' does not exist.", err=True)
        sys.exit(1)

    try:
        config = _open_config(resolved_config_path)
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


def _format_state_raw(state: dict[str, Any], verbose: bool = False) -> str:
    """Format the human-readable state summary shared by resume and state show.

    Args:
        state: A v0 state dictionary.
        verbose: Include full hashes, resume kind, and branch stacks.
    """
    lines: list[str] = []
    status = state.get("status", "unknown")
    if status == "done":
        lines.append("status: done")
    elif status == "solution":
        bindings = state.get("bindings", {})
        if bindings:
            pairs = ", ".join(f"{k}={v}" for k, v in bindings.items())
            lines.append(f"status: solution — bindings: {pairs}")
        else:
            lines.append("status: solution")
    elif status == "suspended":
        label = state.get("suspension", {}).get("label", "")
        lines.append(f'status: suspended — label: "{label}"')
    elif status == "running":
        branches = len(state.get("branches", []))
        lines.append(f"status: running — {branches} branch(es) remaining")
    else:
        lines.append(f"status: {status}")

    ruleset_hash = state.get("ruleset_hash")
    if isinstance(ruleset_hash, str) and ruleset_hash:
        lines.append(
            f"ruleset_hash: {ruleset_hash if verbose else ruleset_hash[:12]}"
        )
    resume_hash = state.get("resume_hash")
    if isinstance(resume_hash, str) and resume_hash:
        lines.append(f"resume_hash:  {resume_hash if verbose else resume_hash[:12]}")
    lines.append(f"goal: {state.get('original_goal')}")
    if verbose:
        lines.append(f"resume_kind: {state.get('resume_kind')}")
        for branch in state.get("branches", []):
            lines.append(f"branch: {branch.get('orig_goal')}")
            lines.extend(f"  {goal}" for goal in branch.get("goals", []))
    return "\n".join(lines)


def _resolve_config_path(config_path: Path | None) -> Path:
    """Resolve the config path from CLI flag, env var, or default."""
    if config_path is not None:
        return config_path
    env_path = os.getenv("ADJOURN_CONFIG")
    if env_path:
        return Path(env_path)
    return Path(".adjourn/config.yaml")


def _open_config(config_path: Path | None) -> Config:
    """Load the project config, hinting at ``config init`` when it is missing.

    Raises:
        FileNotFoundError: If the resolved config file does not exist; the
            message names the path and suggests ``adjourn config init``.
        ValueError: If the config file is invalid.
    """
    path = _resolve_config_path(config_path)
    try:
        return Config(path)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"config file not found: {path}; run `adjourn config init` first"
        ) from exc


# TODO: This will contain more than just the store at some point

def _load_store(config_path: Path | None) -> AggregateRuleSetStore:
    """Load the configured aggregate ruleset store."""
    return build_store_from_config(_open_config(config_path))


def _gather_store_info(
    store: AggregateRuleSetStore | RuleSetStore,
) -> list[StoreInfo]:
    """Gather display metadata for an aggregate or individual store."""
    if isinstance(store, AggregateRuleSetStore):
        return store.store_info_list()
    return [store.store_info()]


def _format_store_info_raw(store_info_list: list[StoreInfo]) -> str:
    """Return raw aligned store metadata output."""
    include_name = any(store_info.name is not None for store_info in store_info_list)
    headers = ["type"]
    if include_name:
        headers.append("name")
    headers.extend(("path", "hash"))
    rows = []
    for store_info in store_info_list:
        row = [store_info.type]
        if include_name:
            row.append(store_info.name or "")
        row.extend((store_info.path, store_info.hash))
        rows.append(row)
    return _format_table(headers, rows)


def _format_table(headers: list[str], rows: list[list[str]]) -> str:
    """Return rows as a plain-text table with aligned columns."""
    widths = [
        max(len(header), *(len(row[index]) for row in rows))
        for index, header in enumerate(headers)
    ]
    lines = [" ".join(header.ljust(width) for header, width in zip(headers, widths))]
    lines.extend(
        " ".join(value.ljust(width) for value, width in zip(row, widths)).rstrip()
        for row in rows
    )
    return "\n".join(line.rstrip() for line in lines)


def _format_config_raw(payload: dict[str, Any]) -> str:
    """Format the resolved config view as sectioned plain text."""
    lines = [
        f"config: {payload['config']}",
        f"base_dir: {payload['base_dir']}",
    ]
    if payload.get("top_error") is not None:
        lines.append(f"top: ERROR: {payload['top_error']}")
    else:
        lines.append(f"top: {payload['top']}")

    store_rows = payload["stores"]
    lines.append("stores:")
    store_headers = ["type"]
    for optional_header in ("name", "prolog", "support"):
        if any(optional_header in item for item in store_rows):
            store_headers.append(optional_header)
    store_headers.extend(("path", "resolved_path", "hash"))
    if any("error" in item for item in store_rows):
        store_headers.append("error")
    rows = []
    for item in store_rows:
        row = [str(item["type"])]
        for key in store_headers[1:]:
            value = item.get(key, "")
            if key == "hash" and value is None:
                value = "<error>"
            row.append(str(value))
        rows.append(row)
    lines.append(_format_table(store_headers, rows) if rows else "(none)")

    lines.append("aliases:")
    alias_rows = [
        [
            item["name"],
            item["hash"],
            "unknown" if item["owned"] is None else str(item["owned"]).lower(),
        ]
        for item in payload["aliases"]
    ]
    lines.append(
        _format_table(["name", "hash", "owned"], alias_rows)
        if alias_rows
        else "(none)"
    )
    lines.append("plugins:")
    plugins = payload["plugins"]
    lines.extend(f"  - {plugin}" for plugin in plugins)
    if not plugins:
        lines.append("  (none)")
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


def _format_state_json(
    projection: dict[str, Any],
    pretty_print: bool,
) -> str:
    """Return JSON serialization of a state projection.

    Args:
        projection: A state projection dict.
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
    tab-completion for the adjourn CLI.

    Examples:

        # Output to stdout
        adjourn complete

        # Save to file
        adjourn complete -o ~/.local/share/bash-completion/completions/adjourn

    After generating the script, source it in your shell configuration:

        # For bash, add to ~/.bashrc:
        source ~/.local/share/bash-completion/completions/adjourn

        # Or for immediate use:
        eval "$(adjourn complete)"
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
        return """# Bash completion script for adjourn CLI
#
# Installation:
#   1. Save this file to a completion directory, e.g.:
#      adjourn complete -o ~/.local/share/bash-completion/completions/adjourn
#
#   2. Source it in your ~/.bashrc:
#      source ~/.local/share/bash-completion/completions/adjourn
#
#   3. Or load it immediately:
#      eval "$(adjourn complete)"
#
# Usage:
#   After installation, type 'adjourn <TAB>' to see available commands."""
    elif shell == "zsh":
        return """# Zsh completion script for adjourn CLI
#
# Installation:
#   1. Save this file to a directory in your $fpath, e.g.:
#      adjourn complete --shell zsh -o ~/.zsh/completions/_adjourn
#
#   2. Add to your ~/.zshrc (if not already present):
#      fpath=(~/.zsh/completions $fpath)
#      autoload -Uz compinit && compinit
#
#   3. Or load it immediately:
#      eval "$(adjourn complete --shell zsh)"
#
# Usage:
#   After installation, type 'adjourn <TAB>' to see available commands."""
    elif shell == "fish":
        return """# Fish completion script for adjourn CLI
#
# Installation:
#   1. Save this file to Fish's completion directory:
#      adjourn complete --shell fish -o ~/.config/fish/completions/adjourn.fish
#
#   2. Or load it immediately:
#      adjourn complete --shell fish | source
#
# Usage:
#   After installation, type 'adjourn <TAB>' to see available commands."""
    else:
        return f"# Completion script for {shell}"


def generate_completion(shell: str) -> str:
    """Render the full completion script for SHELL.

    Renders Click's completion source in-process (equivalent to running
    ``_ADJOURN_COMPLETE=<shell>_source adjourn``, but with no dependency on an
    ``adjourn`` binary on PATH). Bash output is post-processed by
    ``fixup_bash_completion``.

    Args:
        shell: One of "bash", "zsh", or "fish".

    Returns:
        The completion script body as a string.
    """
    comp_cls = get_completion_class(shell)
    if comp_cls is None:
        raise RuntimeError(f"Unsupported shell for completion: {shell}")
    script = comp_cls(main, {}, "adjourn", "_ADJOURN_COMPLETE").source()
    if shell == "bash":
        script = fixup_bash_completion(script)
    return script


def fixup_bash_completion(script: str) -> str:
    """Rewrite Click's bash file/dir completion branches to fill COMPREPLY
    explicitly via compgen, instead of relying on bash's `-o default`/`-o
    dirnames` fallback (which fires inconsistently across bash versions and
    interacts badly with `complete -o nosort -F`).
    """
    replacements = {
        # file branch
        "            COMPREPLY=()\n            compopt -o default":
        '            COMPREPLY+=( $(compgen -f -- "${COMP_WORDS[COMP_CWORD]}") )\n            compopt -o filenames',
        # dir branch
        "            COMPREPLY=()\n            compopt -o dirnames":
        '            COMPREPLY+=( $(compgen -d -- "${COMP_WORDS[COMP_CWORD]}") )\n            compopt -o filenames',
    }

    for old, new in replacements.items():
        if old not in script:
            raise RuntimeError(
                "Completion fixup failed: expected branch not found. "
                "Click's bash template may have changed; re-inspect the "
                "generated script and update fixup_bash_completion."
            )
        script = script.replace(old, new)

    return script


if __name__ == "__main__":
    main()
