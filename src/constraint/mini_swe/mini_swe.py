"""mini-swe-agent foreign callout for the constraint meta-interpreter.

Registers ``run_mini_swe`` in the ``constraint_foreign`` registry so the Prolog
meta-interpreter can invoke it via::

    foreign(run_mini_swe, [RepoRoot, IssueFile], Out)

where ``RepoRoot`` and ``IssueFile`` are absolute path atoms AS THE CALLING
RUNTIME SEES THEM (see the dispatch-topology note below).
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

# Container-side mount constants. When the driver runs docker-out-of-docker
# (DooD), the scrubber compose binds the host repo and ticket dirs to these
# FIXED targets inside the driver (see runner-enbug-github/docker-compose.yml).
# The harness therefore always resolves paths against these constants inside the
# driver, while the HOST paths the sibling daemon needs come from the env vars
# below. On host dispatch these constants are irrelevant (the env vars are unset
# and the incoming args are already real host paths).
_CONTAINER_REPO_ROOT = "/work/repo"
_CONTAINER_TICKET_DIR = "/work/ticket"

# DooD host-path env vars. When BOTH are set, run_mini_swe is executing inside a
# driver container and these carry the HOST-side paths the host daemon must use
# as bind-mount SOURCES for the sibling mini-swe container. When unset, dispatch
# is host-local and only the incoming path args are used.
_ENV_HOST_REPO_ROOT = "ENBUG_HOST_REPO_ROOT"
_ENV_HOST_TICKET_DIR = "ENBUG_HOST_TICKET_DIR"


@register("run_mini_swe")
def _run_mini_swe(arg: Any) -> str:
    """Dispatch mini-swe-agent in a Docker container against a repo checkout.

    Invoked from Prolog via::

        foreign(run_mini_swe, [RepoRoot, IssueFile], Out)

    ``RepoRoot`` and ``IssueFile`` are absolute paths AS THE CALLING RUNTIME
    SEES THEM: real host paths on host dispatch, or the fixed container mount
    targets (``/work/repo`` and ``/work/ticket/<name>``) when the driver runs
    in-container. They are used ONLY for driver-local work -- validation, the
    issue-file copy, and the final ``git rev-parse`` -- and are NEVER written
    into the compose env file.

    Dispatch topology (host vs. docker-out-of-docker) is selected purely by the
    presence of ``ENBUG_HOST_REPO_ROOT`` + ``ENBUG_HOST_TICKET_DIR``:

    * **Both set (DooD):** the driver is a container driving the HOST daemon to
      launch a SIBLING mini-swe container. The sibling's ``/work/repo`` and
      ``/work/task`` bind-mount *sources* are resolved by the HOST daemon, so
      they MUST be host paths. ``MSWEA_REPO_ROOT`` is taken straight from
      ``ENBUG_HOST_REPO_ROOT``; the per-run task dir is created driver-side under
      ``/work/ticket/tmp`` (writable, driver-visible) and its HOST equivalent --
      obtained by swapping the ``/work/ticket`` prefix for
      ``ENBUG_HOST_TICKET_DIR`` -- is written to ``MSWEA_TASK_DIR``.

    * **Neither set (host):** dispatch is host-local. The task dir is created in
      the system temp dir (no DooD, so no host/container translation is needed),
      and ``MSWEA_REPO_ROOT`` / ``MSWEA_TASK_DIR`` are just those real paths.

    Args:
        arg: A two-element ``list[str]`` of the form ``[repo_root, issue_file]``,
             both absolute paths as the calling runtime sees them, marshalled by
             janus from a Prolog list of atoms.

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

    # Validate paths AS THE CALLING RUNTIME SEES THEM. In DooD these are the
    # container mount targets (/work/repo, /work/ticket/<name>); on host they are
    # real host paths. Either way the check is meaningful against the runtime the
    # callout is executing in.
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

    # Select dispatch topology from the env. DooD requires BOTH host-path vars;
    # host dispatch is the default when they are absent.
    host_repo_root = os.environ.get(_ENV_HOST_REPO_ROOT)
    host_ticket_dir = os.environ.get(_ENV_HOST_TICKET_DIR)
    dood = bool(host_repo_root) and bool(host_ticket_dir)

    if dood:
        # Container/DooD dispatch. Create the per-run task dir driver-side under
        # the FIXED container ticket mount (/work/ticket/tmp) -- the only path
        # writable by the driver whose HOST equivalent we can compute -- then
        # derive the host-visible task dir by prefix-swapping /work/ticket ->
        # ENBUG_HOST_TICKET_DIR. The sibling's /work/task bind SOURCE is that
        # host path; MSWEA_REPO_ROOT is the host repo root straight from env.
        task_base = Path(_CONTAINER_TICKET_DIR) / "tmp"
        task_base.mkdir(parents=True, exist_ok=True)
        task_dir = Path(tempfile.mkdtemp(prefix="mini_swe_task_", dir=str(task_base)))
        host_task_dir = str(task_dir).replace(
            _CONTAINER_TICKET_DIR, str(Path(host_ticket_dir)), 1
        )
        mswea_repo_root = str(Path(host_repo_root))
        mswea_task_dir = host_task_dir
    else:
        # Host-local dispatch. No host/container translation; put the task dir in
        # the system temp dir and use those real paths directly.
        task_dir = Path(tempfile.mkdtemp(prefix="mini_swe_task_"))
        mswea_repo_root = str(repo_root)
        mswea_task_dir = str(task_dir)

    try:
        # Copy the issue file into the (driver-visible) temporary task directory.
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
        #
        # MSWEA_REPO_ROOT / MSWEA_TASK_DIR are the HOST bind-mount SOURCES for the
        # sibling container: in DooD they come from the ENBUG_HOST_* env; on host
        # dispatch they are the real local paths computed above.
        compose_vars: dict[str, str] = {
            "HOST_UID": uid,
            "HOST_GID": gid,
            "MSWEA_REPO_ROOT": mswea_repo_root,
            "MSWEA_TASK_DIR": mswea_task_dir,
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
        # Always clean up the per-invocation task directory. In DooD the task_base
        # (/work/ticket/tmp) itself is intentionally left in place.
        shutil.rmtree(str(task_dir), ignore_errors=True)

    # Capture the resulting revision from the runtime-visible repo root.
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(repo_root),
    )
    return result.stdout.strip()
