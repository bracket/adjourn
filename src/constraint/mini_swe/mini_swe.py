"""mini-swe-agent foreign callout for the constraint meta-interpreter.

Registers ``run_mini_swe`` in the ``constraint_foreign`` registry so the Prolog
meta-interpreter can invoke it via::

    foreign(run_mini_swe, [RepoRoot, IssueFile], Out)

where ``RepoRoot`` and ``IssueFile`` are host-side absolute path atoms.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from constraint.constraint_foreign import register

# Vendored compose file bundled as package data, referenced relative to this module.
_COMPOSE_FILE = Path(__file__).parent / "data" / "docker-compose.yml"

# Hardcoded MVP defaults.
_DEFAULT_IMAGE_VERSION = "2.3.0"
_DEFAULT_ARBITER_PORT = "27248"
_DEFAULT_MODEL_ALIAS = "mini-swe-coding"
_FALLBACK_UID = "501"
_FALLBACK_GID = "20"

# Topology defaults. These reproduce the HOST-dispatch behaviour (driver runs on
# the docker host), so an un-parameterized call behaves exactly as before. The
# in-container driver overrides them via its own environment (arbiter/devpi host
# -> its shared-net alias; network -> the external shared net it owns).
_DEFAULT_ARBITER_HOST = "host.docker.internal"
_DEFAULT_DEVPI_HOST = "host.docker.internal"
_DEFAULT_DEVPI_PORT = "7974"
_DEFAULT_NETWORK = "mini_swe_agent_default"
_DEFAULT_NETWORK_EXTERNAL = "false"


@register("run_mini_swe")
def _run_mini_swe(arg: Any) -> str:
    """Dispatch mini-swe-agent in a Docker container against a host repo checkout.

    Invoked from Prolog via::

        foreign(run_mini_swe, [RepoRoot, IssueFile], Out)

    The callout copies the issue file into a fresh temporary directory, builds
    the required compose environment, runs ``docker compose ... run mini``
    synchronously, then captures the resulting git revision via
    ``git rev-parse HEAD`` in the repo root.

    The temporary task directory is created under ``<repo_root>.parent/tmp``
    (i.e. ``HOST_WORKSPACE/work/tmp``), NOT the container-local ``/tmp``. This
    matters when the driver is itself a container running docker against the host
    daemon: the sibling mini-swe container's ``/work/task`` bind-mount *source*
    is resolved by the HOST daemon, so it must be a real host path. The ticket
    dir is identity-bound into the driver (``-v WORKDIR:WORKDIR``), so a task dir
    created under it is valid on both sides. On host dispatch the same path is
    simply the host's own filesystem, so behaviour is unchanged.

    Args:
        arg: A two-element ``list[str]`` of the form ``[repo_root, issue_file]``,
             both host-side absolute paths marshalled by janus from a Prolog list
             of atoms.

    Returns:
        The stripped stdout of ``git rev-parse HEAD`` in *repo_root* after the
        agent run completes; marshalled back to a Prolog atom by janus.

    Raises:
        ValueError: If *arg* is not a two-element sequence, or if *repo_root* is
            not an existing directory, or if *issue_file* is not an existing file.
        subprocess.CalledProcessError: If ``docker compose`` or ``git rev-parse``
            exits with a non-zero status.
    """
    # Unpack the 2-element list argument.
    try:
        items = list(arg)
    except TypeError:
        raise ValueError(
            f"run_mini_swe: expected an iterable 2-element sequence, got {arg!r}"
        )
    if len(items) != 2:
        raise ValueError(
            f"run_mini_swe: expected exactly 2 arguments [repo_root, issue_file],"
            f" got {len(items)}"
        )

    repo_root = Path(items[0]).resolve()
    issue_file = Path(items[1]).resolve()

    # Validate paths.
    if not repo_root.is_dir():
        raise ValueError(
            f"run_mini_swe: repo_root is not an existing directory: {repo_root}"
        )
    if not issue_file.is_file():
        raise ValueError(
            f"run_mini_swe: issue_file is not an existing file: {issue_file}"
        )

    # Determine HOST_UID / HOST_GID.  os.getuid/os.getgid are unavailable on
    # Windows; the fallback values (501/20) are macOS default user/staff IDs,
    # chosen as a reasonable convention for developer workstations.
    uid = str(os.getuid()) if hasattr(os, "getuid") else _FALLBACK_UID
    gid = str(os.getgid()) if hasattr(os, "getgid") else _FALLBACK_GID

    # Task-dir base: <ticket_dir>/tmp, where ticket_dir == repo_root.parent
    # (the repo checkout always lives at HOST_WORKSPACE/work/<repo>, so its
    # parent is the ticket dir HOST_WORKSPACE/work). Kept on a host-visible path
    # for the docker-out-of-docker case; see the docstring.
    task_base = repo_root.parent / "tmp"
    task_base.mkdir(parents=True, exist_ok=True)
    task_dir = Path(tempfile.mkdtemp(prefix="mini_swe_task_", dir=str(task_base)))
    try:
        # Copy the issue file into the temporary task directory.
        shutil.copy2(str(issue_file), str(task_dir))
        issue_basename = issue_file.name
        container_issue_path = f"/work/task/{issue_basename}"

        # Build the compose variable substitution mapping (only the vars referenced
        # in the vendored compose file, so we control every value written to the
        # env file and avoid escaping issues with arbitrary env values).
        #
        # The *_HOST / MSWEA_NETWORK* vars select dispatch topology. They default
        # to the host-dispatch values, and are overridden from this process's
        # environment when the driver runs in-container (it exports
        # MSWEA_ARBITER_HOST / MSWEA_DEVPI_HOST=<its alias>, MSWEA_NETWORK=the
        # external shared net, MSWEA_NETWORK_EXTERNAL=true).
        compose_vars: dict[str, str] = {
            "HOST_UID": uid,
            "HOST_GID": gid,
            "MSWEA_REPO_ROOT": str(repo_root),
            "MSWEA_TASK_DIR": str(task_dir),
            "MSWEA_ISSUE_FILE": container_issue_path,
            "MSWEA_IMAGE_VERSION": _DEFAULT_IMAGE_VERSION,
            "MSWEA_ARBITER_HOST": os.environ.get(
                "MSWEA_ARBITER_HOST", _DEFAULT_ARBITER_HOST
            ),
            "MSWEA_ARBITER_PORT": os.environ.get(
                "MSWEA_ARBITER_PORT", _DEFAULT_ARBITER_PORT
            ),
            "MSWEA_DEVPI_HOST": os.environ.get(
                "MSWEA_DEVPI_HOST", _DEFAULT_DEVPI_HOST
            ),
            "MSWEA_DEVPI_PORT": os.environ.get(
                "MSWEA_DEVPI_PORT", _DEFAULT_DEVPI_PORT
            ),
            "MSWEA_MODEL_ALIAS": _DEFAULT_MODEL_ALIAS,
            "MSWEA_NETWORK": os.environ.get("MSWEA_NETWORK", _DEFAULT_NETWORK),
            "MSWEA_NETWORK_EXTERNAL": os.environ.get(
                "MSWEA_NETWORK_EXTERNAL", _DEFAULT_NETWORK_EXTERNAL
            ),
        }

        # Write the environment to a temporary env file.
        # mkstemp creates files with mode 0600 (readable/writable by owner only).
        env_fd, env_file_path = tempfile.mkstemp(prefix="mini_swe_env_", suffix=".env")
        try:
            with os.fdopen(env_fd, "w") as env_fp:
                for key, value in compose_vars.items():
                    env_fp.write(f"{key}={value}\n")

            # Run docker compose.
            subprocess.run(
                [
                    "docker",
                    "compose",
                    "--file",
                    str(_COMPOSE_FILE),
                    "--env-file",
                    env_file_path,
                    "run",
                    "mini",
                ],
                check=True,
            )
        finally:
            # Remove the env file even if docker compose raised.
            try:
                Path(env_file_path).unlink()
            except FileNotFoundError:
                pass
    finally:
        # Always clean up the per-invocation task directory. The task_base
        # (<ticket_dir>/tmp) itself is intentionally left in place.
        shutil.rmtree(str(task_dir), ignore_errors=True)

    # Capture the resulting revision.
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(repo_root),
    )
    return result.stdout.strip()
