#!/usr/bin/env python3
"""Verified worktrees, recoverable setup and PR lifecycle. Python 3.11+, macOS/Linux."""
import argparse
import contextlib
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
from urllib.parse import quote, urlsplit
from uuid import UUID, uuid4


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    # A caller's repository overrides must not redirect an explicit command root.
    env = os.environ.copy()
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
                "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                "GIT_NAMESPACE", "GIT_PREFIX", "GIT_CEILING_DIRECTORIES"):
        env.pop(key, None)
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0")
    try:
        result = subprocess.run(["git", "-C", str(root), *args], env=env,
                                capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("Git could not finish; inspect the repository before retrying") from error
    if check and result.returncode:
        # Raw Git errors can include credential-bearing URLs or config values.
        raise ValueError(f"Git {args[0]} failed; inspect the selected repository")
    return result


def canonical(path: Path) -> Path:
    path = Path(path)
    if not path.is_absolute() or path != path.resolve():
        raise ValueError("Use an absolute canonical path without symlinks or traversal")
    return path


def safe_file(path: Path) -> None:
    canonical(path)
    if path.exists() and not path.is_file():
        raise ValueError("Expected a regular file; preserve and review the existing path")


def repository(path: Path) -> dict:
    root = Path(git(path, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    common = Path(git(root, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()).resolve()
    git_dir = Path(git(root, "rev-parse", "--absolute-git-dir").stdout.strip()).resolve()
    branch = git(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False).stdout.strip()
    head = git(root, "rev-parse", "--verify", "HEAD", check=False).stdout.strip()
    return {"root": str(root), "common_dir": str(common), "git_dir": str(git_dir),
            "branch": branch or None, "head": head or None}


def worktrees(root: Path) -> list[dict]:
    records = []
    current = {}
    for field in git(root, "worktree", "list", "--porcelain", "-z").stdout.split("\0"):
        if not field:
            if current:
                records.append(current)
                current = {}
        else:
            key, _, value = field.partition(" ")
            current[key] = value
    if current:
        records.append(current)
    return records


def policy_values(root: Path) -> dict:
    path = Path(root) / ".codex/vibe-workflow.toml"
    safe_file(path)
    if not path.exists():
        return {"enabled": True, "auto_cleanup": True}
    try:
        policy = tomllib.loads(path.read_text())
    except (UnicodeError, tomllib.TOMLDecodeError) as error:
        raise ValueError("Review malformed vibe-workflow.toml; no settings were changed") from error
    version = policy.get("schema_version", 1)
    lifecycle = policy.get("task_lifecycle", {})
    if type(version) is not int or version != 1:
        raise ValueError("Unsupported workflow policy schema_version")
    if not isinstance(lifecycle, dict) or set(lifecycle) - {"enabled", "auto_cleanup"}:
        raise ValueError("Unknown or malformed task_lifecycle policy fields")
    values = {key: lifecycle.get(key, True) for key in ("enabled", "auto_cleanup")}
    if any(type(value) is not bool for value in values.values()):
        raise ValueError("Lifecycle preferences must be true or false")
    return values


def load_policy(root: Path) -> bool:
    return policy_values(root)["enabled"]


def load_cleanup_policy(root: Path) -> bool:
    return all(policy_values(root).values())


def result(operation: str, status: str, implementation: str, **fields) -> dict:
    return {"operation": operation, "status": status, "implementation": implementation,
            "delivery": "not_checked", "changes": [], "pending_user_actions": [],
            "evidence_ref": None, "next_action": None, **fields}


def remote_summary(name: str, url: str) -> dict:
    transport, host = "local", None
    try:
        if "://" in url:
            parsed = urlsplit(url)
            transport = parsed.scheme if parsed.scheme in {"https", "http", "ssh", "git", "file"} else "unknown"
            host = parsed.hostname
        elif re.match(r"(?:[^/@:]+@)?[^/:]+:.+", url):
            transport, host = "ssh", url.split(":", 1)[0].rsplit("@", 1)[-1]
    except ValueError:
        transport, host = "unknown", None
    return {"name": name, "transport": transport, "host": host}


def effective_identity(root: Path, kind: str) -> dict | None:
    value = git(root, "var", f"GIT_{kind}_IDENT", check=False)
    match = re.fullmatch(r"(.*) <([^<>]+)> \d+ [+-]\d{4}\n?", value.stdout)
    return {"name": match[1], "email": match[2]} if value.returncode == 0 and match else None


def inspect_project(root: Path, clients: list[str]) -> dict:
    if not isinstance(clients, list) or any(client not in ("app", "vscode") for client in clients):
        raise ValueError("Select supported clients: app and/or vscode")
    requested = Path(root).resolve(strict=True)
    if not requested.is_dir():
        raise ValueError("Select an existing project directory")
    probe = git(requested, "rev-parse", "--show-toplevel", check=False)
    if probe.returncode:
        candidates = sorted(str(p) for p in requested.iterdir()
                            if p.is_dir() and not p.is_symlink() and (p / ".git").exists())
        return result("inspect", "action_required", "not_started", repositories=candidates,
                      pending_user_actions=[{"code": "select_repository", "message":
                                             "Select one existing Git repository; sibling projects are not enrolled."}],
                      next_action="Inspect the selected repository explicitly")
    facts = repository(requested)
    project = Path(facts["root"])
    enabled = load_policy(project)
    identity = {key: git(project, "config", "--get", f"user.{key}", check=False).stdout.strip() or None
                for key in ("name", "email")}
    author = effective_identity(project, "AUTHOR")
    committer = effective_identity(project, "COMMITTER")
    remotes = [remote_summary(name, git(project, "remote", "get-url", name).stdout.strip())
               for name in git(project, "remote").stdout.splitlines()]
    actions = []
    if not all(identity.values()):
        actions.append({"code": "commit_identity", "message": "Confirm the missing commit identity before committing."})
    elif author != identity or committer != identity:
        actions.append({"code": "identity_override", "message": "Confirm the effective author/committer overrides before committing."})
    if len(remotes) != 1:
        actions.append({"code": "select_remote", "message": "Confirm the publication remote; none is selected automatically."})
    actions.append({"code": "publication_access", "message":
                    "Verify existing Git transport and PR write access when publishing; do not change credentials automatically."})
    instructions = []
    for directory in (requested, *requested.parents):
        for filename in ("AGENTS.md", "AGENTS.override.md"):
            if (directory / filename).is_file():
                instructions.append(str(directory / filename))
    facts.update(requested_root=str(requested), instructions=instructions,
                 changes=git(project, "status", "--porcelain=v1", "-z", "--untracked-files=normal").stdout.split("\0")[:-1],
                 settings_present=[name for name in (".codex/config.toml", ".codex/hooks.json")
                                   if (project / name).exists()])
    return result("inspect", "ok", "inspection_only", project=facts, enabled=enabled,
                  clients={client: "not_tested" for client in dict.fromkeys(clients)},
                  tools={"git": True, "python": sys.version.split()[0], "gh": shutil.which("gh") is not None},
                  access={"commit_identity": identity, "remotes": remotes, "pr_identity": "unverified",
                          "effective_author": author, "effective_committer": committer,
                          "git_write": "unverified", "pr_write": "unverified"},
                  pending_user_actions=actions,
                  next_action="Create or select a task worktree before implementation" if enabled else "Respect the explicit lifecycle opt-out")


def verify_worktree(source: Path, worktree: Path, branch: str) -> dict:
    target = canonical(worktree)
    source_facts = repository(Path(source).resolve(strict=True))
    facts = repository(target)
    if facts["root"] != str(target):
        raise ValueError("Select the exact registered worktree root, not a nested directory")
    if facts["common_dir"] != source_facts["common_dir"]:
        raise ValueError("Worktree belongs to another repository")
    if facts["git_dir"] == facts["common_dir"]:
        raise ValueError("Primary checkout is not a task worktree")
    if git(target, "rev-parse", "--show-superproject-working-tree").stdout.strip():
        raise ValueError("Select the owning repository rather than a submodule")
    matches = [item for item in worktrees(Path(source_facts["root"]))
               if item.get("worktree") == str(target)]
    if len(matches) != 1 or "prunable" in matches[0]:
        raise ValueError("Worktree is not uniquely registered and usable")
    if facts["branch"] != branch or matches[0].get("branch") != f"refs/heads/{branch}":
        raise ValueError("Worktree branch changed or HEAD is detached")
    return {**facts, "command_cwd": str(target), "worker_cwd": str(target)}


def read_record(path: Path) -> dict:
    safe_file(path)
    data = json.loads(path.read_text(), object_pairs_hook=unique_object)
    fields = {"schema_version", "task_id", "source", "common_dir", "worktree", "branch", "base", "base_commit", "state"}
    if not isinstance(data, dict) or set(data) != fields or type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("Review incompatible task state before continuing")
    if any(not isinstance(data[key], str) for key in fields - {"schema_version"}):
        raise ValueError("Review malformed task state before continuing")
    if data["state"] not in {"pending", "verified"}:
        raise ValueError("Review unknown task state before continuing")
    if str(UUID(data["task_id"])) != path.stem or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", data["base_commit"]):
        raise ValueError("Task identity or base commit is malformed")
    return data


def write_record(path: Path, data: dict) -> None:
    safe_file(path)
    descriptor, temporary = tempfile.mkstemp(prefix=".task-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(data, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def manual_start(source: Path, request: dict, base_commit: str) -> dict:
    branch_exists = git(source, "show-ref", "--verify", f"refs/heads/{request['branch']}", check=False).returncode == 0
    action = {"code": "create_worktree", "message":
              "Create or repair this task worktree, then rerun start with create=false and adopt_existing=true. Never force or reset existing work.",
              "worktree": request["worktree"], "branch": request["branch"], "base_commit": base_commit}
    if not Path(request["worktree"]).exists() and not branch_exists:
        action["command"] = shlex.join(["git", "-C", str(source), "worktree", "add", "-b",
                                        request["branch"], request["worktree"], base_commit])
    else:
        action["message"] = "Inspect the existing branch/path before any retry. Confirm ownership; do not force, reset or duplicate the worktree."
    return result("start", "action_required", "not_started", pending_user_actions=[action],
                  next_action="Complete the manual worktree action, then reverify")


def start_task(source: Path, request: dict) -> dict:
    try:
        return _start_task(source, request)
    except (ValueError, OSError) as error:
        message = str(error) if isinstance(error, ValueError) else "Filesystem operation failed; preserve progress and inspect permissions/paths"
        return result("start", "blocked", "not_started", next_action=message)


def _start_task(source: Path, request: dict) -> dict:
    required = {"task_id", "worktree", "branch", "base"}
    if not isinstance(request, dict) or not required <= request.keys() or request.keys() - required - {"create", "adopt_existing"}:
        raise ValueError("Provide task_id, worktree, branch, base and optional create/adopt_existing only")
    if any(not isinstance(request[key], str) or not request[key].strip() or "\0" in request[key] for key in required):
        raise ValueError("Required startup fields must be nonempty strings without NUL")
    if str(UUID(request["task_id"])) != request["task_id"]:
        raise ValueError("task_id must be a canonical UUID")
    if any(type(request.get(key, default)) is not bool for key, default in (("create", True), ("adopt_existing", False))):
        raise ValueError("create and adopt_existing must be booleans")
    facts = repository(Path(source).resolve(strict=True))
    source = Path(facts["root"])
    if not load_policy(source):
        return result("start", "ok", "disabled", next_action="Lifecycle explicitly disabled; existing project rules still apply")
    target = canonical(Path(request["worktree"]))
    branch = request["branch"]
    if branch.startswith("-") or git(source, "check-ref-format", f"refs/heads/{branch}", check=False).returncode:
        raise ValueError("Choose a valid explicit task branch")
    for entry in worktrees(source):
        existing = Path(entry["worktree"]).resolve()
        if target != existing and (target.is_relative_to(existing) or existing.is_relative_to(target)):
            raise ValueError("Keep task worktrees separate from every existing checkout")
    parent = next(path for path in target.parents if path.exists())
    if git(parent, "rev-parse", "--absolute-git-dir", check=False).returncode == 0:
        raise ValueError("Worktree destination is nested inside another checkout or its Git metadata")
    common = Path(facts["common_dir"])
    if target.is_relative_to(common) or common.is_relative_to(target):
        raise ValueError("Worktree destination must not contain or live inside Git metadata")
    state_dir = canonical(common / "vibe-setup")
    tasks = canonical(state_dir / "tasks")
    record_path = tasks / f"{request['task_id']}.json"
    safe_file(record_path)
    previous = read_record(record_path) if record_path.exists() else None
    if previous:
        expected = {"task_id": request["task_id"], "source": str(source), "common_dir": str(common),
                    "worktree": str(target), "branch": branch, "base": request["base"]}
        if any(previous[key] != value for key, value in expected.items()):
            raise ValueError("Task binding changed; reconcile the existing task before continuing")
        base_commit = previous["base_commit"]
    else:
        base_commit = git(source, "rev-parse", "--verify", "--end-of-options", f"{request['base']}^{{commit}}").stdout.strip()
    target_existed = target.exists()
    if target_existed:
        context = verify_worktree(source, target, branch)
        if git(target, "merge-base", "--is-ancestor", base_commit, "HEAD", check=False).returncode:
            raise ValueError("Worktree does not descend from the selected task base")
        if not previous and not request.get("adopt_existing", False):
            return result("start", "action_required", "not_started", pending_user_actions=[{
                "code": "confirm_worktree_owner", "message": "Confirm this existing worktree belongs to this task, then set adopt_existing=true."}],
                next_action="Confirm ownership before binding the existing worktree")
    elif not request.get("create", True):
        return manual_start(source, request, base_commit)
    elif previous and previous["state"] == "verified":
        raise ValueError("Previously verified worktree is missing; preserve and reconcile task progress")
    elif git(source, "show-ref", "--verify", f"refs/heads/{branch}", check=False).returncode == 0:
        return manual_start(source, request, base_commit)
    tasks.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = state_dir / "start.lock"
    safe_file(lock_path)
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return result("start", "action_required", "not_started", next_action="Another startup is running; reconcile after it finishes")
        # Recheck under the lock; records coordinate helpers, not arbitrary native tools.
        if not target_existed and target.exists() and previous is None:
            raise ValueError("Destination appeared during startup; confirm ownership before adoption")
        for path in tasks.glob("*.json"):
            binding = read_record(path)
            if path == record_path:
                if binding != previous:
                    raise ValueError("Task record changed during startup; rerun to reconcile")
            elif binding["worktree"] == str(target) or binding["branch"] == branch:
                raise ValueError("Another task already owns this worktree or branch")
        changes = []
        record = previous or {"schema_version": 1, "task_id": request["task_id"], "source": str(source),
                              "common_dir": str(common), "worktree": str(target), "branch": branch,
                              "base": request["base"], "base_commit": base_commit, "state": "pending"}
        if not target.exists():
            if previous is None:
                write_record(record_path, record)
            try:
                created = git(source, "worktree", "add", "-b", branch, str(target), base_commit, check=False)
                if created.returncode:
                    return manual_start(source, request, base_commit)
            except ValueError:
                return manual_start(source, request, base_commit)
            changes.append("worktree_created")
        context = verify_worktree(source, target, branch)
        if git(target, "merge-base", "--is-ancestor", base_commit, "HEAD", check=False).returncode:
            raise ValueError("Task base changed during startup; reconcile before editing")
        if record["state"] != "verified":
            record["state"] = "verified"
            write_record(record_path, record)
            changes.append("task_bound")
        return result("start", "ok", "worktree_verified", changes=changes, context=context,
                      evidence_ref=str(record_path), next_action="Use command_cwd and worker_cwd for every task write; reverify after context changes")


SETUP_FILES = (".codex/hooks/subagents.py", ".codex/delegation-brief.md",
               ".codex/config.toml", ".codex/hooks.json", ".gitignore", ".graphifyignore",
               ".codex/vibe-workflow.toml")
PACKAGE_FILES = ("workflow.py", "install.py", ".codex/hooks/subagents.py",
                 "delegation-brief.md", ".codex/config.toml", ".codex/hooks.json",
                 ".codex/vibe-workflow.toml")


def uuid_string(value) -> str:
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("Use a canonical UUID for the task or operation")
    return value


def setup_context(task: dict) -> tuple[dict, dict]:
    if not isinstance(task, dict) or set(task) != {"task_id", "worktree"} or not isinstance(task["worktree"], str):
        raise ValueError("Provide only task_id and the exact worktree path")
    task_id = uuid_string(task["task_id"])
    root = canonical(Path(task["worktree"]))
    common = Path(repository(root)["common_dir"])
    binding = read_record(common / "vibe-setup/tasks" / f"{task_id}.json")
    if binding["state"] != "verified" or binding["worktree"] != str(root) or binding["common_dir"] != str(common):
        raise ValueError("Reconcile the verified task binding before setup")
    facts = verify_worktree(Path(binding["source"]), root, binding["branch"])
    if git(root, "merge-base", "--is-ancestor", binding["base_commit"], "HEAD", check=False).returncode:
        raise ValueError("Worktree no longer descends from the task base")
    return binding, facts


def fingerprint(path: Path) -> dict | None:
    safe_file(path)
    if not path.exists():
        return None
    return {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "mode": stat.S_IMODE(path.stat().st_mode)}


def package_digest() -> str:
    digest = hashlib.sha256()
    for name in PACKAGE_FILES:
        payload = (Path(__file__).resolve().parent / name).read_bytes()
        digest.update(name.encode() + b"\0" + hashlib.sha256(payload).digest())
    return digest.hexdigest()


def setup_writes(root: Path) -> dict[str, bytes]:
    source = Path(__file__).resolve().parent
    installer = runpy.run_path(str(source / "install.py"))
    try:
        writes = installer["plan_install"](root)
        load_policy(root)
    except subprocess.TimeoutExpired as error:
        raise ValueError("Installer Git inspection timed out; check local Git and retry this operation") from error
    except ValueError as error:
        # Parser messages can contain custom configuration values; keep them local.
        raise ValueError("Setup conflict: review customized recipe files, policy and agent/hook settings locally") from error
    if not (root / SETUP_FILES[-1]).exists():
        writes[SETUP_FILES[-1]] = (source / SETUP_FILES[-1]).read_bytes()
    return writes


def plan_setup(task: dict, operation_id: str | None = None) -> dict:
    """Read-only recipe preview. Hashes bind reviewed input; configuration never enters state."""
    binding, facts = setup_context(task)
    root = Path(binding["worktree"])
    before = {name: fingerprint(root / name) for name in SETUP_FILES}
    writes = setup_writes(root)
    files = {}
    for name, current in before.items():
        after = {"sha256": hashlib.sha256(writes[name]).hexdigest(),
                 "mode": current["mode"] if current else 0o600} if name in writes else current
        files[name] = {"before": current, "after": after}
    if before != {name: fingerprint(root / name) for name in SETUP_FILES}:
        raise ValueError("Setup files changed during preview; inspect again")
    return {"schema_version": 1, "operation_id": uuid_string(operation_id or str(uuid4())),
            "binding": binding, "head": facts["head"], "package": package_digest(), "files": files}


def validate_plan(plan: dict) -> None:
    if (not isinstance(plan, dict) or set(plan) != {"schema_version", "operation_id", "binding", "head", "package", "files"}
            or type(plan["schema_version"]) is not int or plan["schema_version"] != 1):
        raise ValueError("Review an unsupported setup plan")
    uuid_string(plan["operation_id"])
    if not isinstance(plan["binding"], dict) or not isinstance(plan["head"], str) or not isinstance(plan["package"], str):
        raise ValueError("Malformed setup binding or package fingerprint")
    if not isinstance(plan["files"], dict) or set(plan["files"]) != set(SETUP_FILES):
        raise ValueError("Setup plan must contain exactly the owned recipe paths")
    for entry in plan["files"].values():
        if not isinstance(entry, dict) or set(entry) != {"before", "after"} or entry["after"] is None:
            raise ValueError("Malformed setup file state")
        for value in entry.values():
            if value is not None and (not isinstance(value, dict) or set(value) != {"sha256", "mode"}
                    or not isinstance(value["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"])
                    or type(value["mode"]) is not int or not 0 <= value["mode"] <= 0o7777):
                raise ValueError("Malformed setup file fingerprint")


def read_operation(path: Path) -> dict:
    safe_file(path)
    record = json.loads(path.read_text(), object_pairs_hook=unique_object)
    if (not isinstance(record, dict) or set(record) != {"schema_version", "plan", "done", "state"}
            or type(record["schema_version"]) is not int or record["schema_version"] != 1):
        raise ValueError("Review incompatible setup recovery state")
    validate_plan(record["plan"])
    if record["plan"]["operation_id"] != path.stem or record["state"] not in ("pending", "complete"):
        raise ValueError("Setup recovery identity or state changed")
    changed = {name for name, entry in record["plan"]["files"].items() if entry["before"] != entry["after"]}
    done = record["done"]
    if (not isinstance(done, list) or any(not isinstance(name, str) for name in done)
            or len(set(done)) != len(done) or not set(done) <= changed
            or (record["state"] == "complete" and set(done) != changed)):
        raise ValueError("Malformed setup recovery progress")
    return record


def sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def setup_directory(path: Path) -> None:
    canonical(path)
    missing = []
    parent = path
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
        sync_directory(directory.parent)


def setup_temporary(path: Path, operation_id: str) -> Path:
    return path.with_name(f".vibe-{operation_id}-{path.name}.tmp")


def replace_setup_file(path: Path, payload: bytes, before: dict | None, after: dict, operation_id: str) -> None:
    """Replace one owned file; a complete interrupted temporary file can be reused."""
    temporary = setup_temporary(path, operation_id)
    setup_directory(path.parent)
    if fingerprint(temporary) is None:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fchmod(stream.fileno(), after["mode"])
            os.fsync(stream.fileno())
    if fingerprint(temporary) != after:
        raise ValueError("Interrupted temporary file differs from the plan; preserve and inspect it before resuming")
    if fingerprint(path) != before:
        raise ValueError("Destination changed during setup; preserve the edit and reconcile")
    os.replace(temporary, path)
    sync_directory(path.parent)


def run_setup(plan: dict, task: dict, *, resume: bool) -> dict:
    validate_plan(plan)
    binding, facts = setup_context(task)
    if plan["binding"] != binding or plan["head"] != facts["head"] or plan["package"] != package_digest():
        raise ValueError("Task, HEAD or helper package changed; reconcile before applying this plan")
    root = Path(binding["worktree"])
    state = canonical(Path(binding["common_dir"]) / "vibe-setup")
    records = canonical(state / "operations")
    record_path = records / f"{plan['operation_id']}.json"
    safe_file(record_path)
    if not record_path.exists() and (resume or plan != plan_setup(task, plan["operation_id"])):
        raise ValueError("Setup plan is stale or recovery intent is missing; inspect again")
    lock_path = state / "setup.lock"
    safe_file(lock_path)
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for path in records.glob("*.json"):
            other = read_operation(path)
            if (path != record_path and other["state"] == "pending"
                    and other["plan"]["binding"].get("worktree") == str(root)):
                return result("apply", "action_required", "setup_pending", evidence_ref=str(path),
                              next_action=f"Resume pending operation {path.stem} before starting another setup")
        previous = read_operation(record_path) if record_path.exists() else None
        if previous and previous["plan"] != plan:
            raise ValueError("Operation already exists with another plan; preserve and reconcile it")
        record = previous or {"schema_version": 1, "plan": plan, "done": [], "state": "pending"}
        # Preflight every owned path before touching any one of them.
        current = {name: fingerprint(root / name) for name in SETUP_FILES}
        for name, entry in plan["files"].items():
            allowed = (entry["after"],) if name in record["done"] else (entry["before"], entry["after"])
            if current[name] not in allowed:
                raise ValueError("Owned files changed outside this operation; preserve and reconcile the edits")
            temporary = fingerprint(setup_temporary(root / name, plan["operation_id"]))
            if temporary is not None and (not previous or temporary != entry["after"] or current[name] == entry["after"]):
                raise ValueError("Unexpected setup temporary file; preserve and inspect it locally")
        if not previous and plan != plan_setup(task, plan["operation_id"]):
            raise ValueError("Setup plan changed while waiting for the lock; inspect again")
        writes = setup_writes(root)
        for name, payload in writes.items():
            if hashlib.sha256(payload).hexdigest() != plan["files"][name]["after"]["sha256"]:
                raise ValueError("Installer output changed; reconcile with the original plan")
        if record["state"] == "complete":
            return result("apply", "ok", "setup_configured", evidence_ref=str(record_path),
                          next_action="Recipe files verified; client trust and full onboarding remain separate")
        setup_directory(records)
        if not previous:
            write_record(record_path, record)
        changes = []
        for name in SETUP_FILES:
            entry = plan["files"][name]
            binding_now, facts_now = setup_context(task)
            if binding_now != binding or facts_now["head"] != plan["head"]:
                raise ValueError("Worktree context changed during setup; stop and reconcile")
            observed = fingerprint(root / name)
            if observed != entry["after"]:
                if observed != entry["before"] or name not in writes:
                    raise ValueError("Owned file changed during setup; stop and reconcile")
                replace_setup_file(root / name, writes[name], entry["before"], entry["after"], plan["operation_id"])
                changes.append(name)
            if entry["before"] != entry["after"] and name not in record["done"]:
                record["done"].append(name)
                write_record(record_path, record)
        if any(fingerprint(root / name) != entry["after"] for name, entry in plan["files"].items()):
            raise ValueError("Setup verification changed; preserve all edits before resuming")
        binding_now, facts_now = setup_context(task)
        if binding_now != binding or facts_now["head"] != plan["head"] or package_digest() != plan["package"]:
            raise ValueError("Setup context changed before final verification; stop and reconcile")
        record["state"] = "complete"
        write_record(record_path, record)
        return result("apply", "ok", "setup_configured", changes=changes, evidence_ref=str(record_path),
                      next_action="Recipe configured only; review project trust and hooks in each client before validation")


def setup_failure(operation: str, error: Exception, evidence: str | None = None) -> dict:
    if isinstance(error, BlockingIOError):
        message = "Another setup is running; retry after it finishes"
    elif isinstance(error, OSError):
        message = "Filesystem operation interrupted; preserve progress and resume the same operation if its record exists"
    else:
        message = str(error)
    return result(operation, "action_required" if isinstance(error, OSError) else "blocked", "setup_pending",
                  evidence_ref=evidence, next_action=message,
                  pending_user_actions=[{"code": "reconcile_setup", "message": message}])


def apply_setup(plan: dict, task: dict) -> dict:
    evidence = None
    try:
        validate_plan(plan)
        binding, _ = setup_context(task)
        evidence = str(Path(binding["common_dir"]) / "vibe-setup/operations" / f"{plan['operation_id']}.json")
        return run_setup(plan, task, resume=False)
    except (ValueError, OSError) as error:
        return setup_failure("apply", error, evidence)


def resume_operation(root: Path, operation_id: str, confirmation: dict | None = None, *, usage: dict | None = None) -> dict:
    evidence = None
    try:
        operation_id = uuid_string(operation_id)
        root = canonical(root)
        common = Path(repository(root)["common_dir"])
        path = common / "vibe-setup/operations" / f"{operation_id}.json"
        evidence = str(path)
        if not path.exists():
            return resume_lifecycle(root, operation_id, confirmation, usage=usage)
        if confirmation is not None:
            raise ValueError("Setup recovery accepts no confirmation overrides; reconcile changed files explicitly")
        record = read_operation(path)
        binding = record["plan"]["binding"]
        if binding.get("worktree") != str(root):
            raise ValueError("Resume from the operation's exact worktree root")
        response = run_setup(record["plan"], {"task_id": binding.get("task_id"), "worktree": str(root)}, resume=True)
        return {**response, "operation": "resume"}
    except (ValueError, OSError) as error:
        return setup_failure("resume", error, evidence)


def validate_schedule(mode: str, checkpoint_ids: list[str]) -> tuple[str, ...]:
    if mode not in ("checkpoints", "phases") or not isinstance(checkpoint_ids, list) or not checkpoint_ids:
        raise ValueError("Declare planned checkpoints or phases")
    if any(not isinstance(item, str) or not item.strip() or len(item) > 128 for item in checkpoint_ids):
        raise ValueError("Milestone IDs must be nonblank strings of at most 128 characters")
    if len(set(checkpoint_ids)) != len(checkpoint_ids) or (mode == "checkpoints" and len(checkpoint_ids) > 4):
        raise ValueError("Use unique milestones: at most four checkpoints, or one per phase")
    return tuple(checkpoint_ids)


def managed_section(body: str, task_id: str) -> str | None:
    start = f"<!-- vibe-task-lifecycle:begin task={uuid_string(task_id)} -->"
    end = "<!-- vibe-task-lifecycle:end -->"
    if "<!-- vibe-task-lifecycle" not in body:
        return None
    if body.count("<!-- vibe-task-lifecycle") != 2 or body.count(start) != 1 or body.count(end) != 1:
        raise ValueError("Reconcile malformed, duplicate or foreign lifecycle markers")
    before, tail = body.split(start)
    if end in before or end not in tail:
        raise ValueError("Reconcile reversed lifecycle markers")
    return tail.split(end)[0]


def render_pr(title: str, body: str, task_id: str, state: str, section: str) -> tuple[str, str]:
    if state not in ("BLOCKED", "READY") or not all(isinstance(value, str) for value in (title, body, section)):
        raise ValueError("PR state must be BLOCKED or READY with text content")
    if not title.strip() or not section.strip() or "<!-- vibe-task-lifecycle" in section:
        raise ValueError("Provide a title and an unambiguous managed section")
    inner = managed_section(body, task_id)
    suffix = re.sub(r"^\[(BLOCKED|READY)\] ", "", title, count=1)
    if suffix.startswith(("[BLOCKED]", "[READY]")):
        raise ValueError("Reconcile duplicate or malformed lifecycle title prefixes")
    start = f"<!-- vibe-task-lifecycle:begin task={task_id} -->"
    end = "<!-- vibe-task-lifecycle:end -->"
    if inner is None:
        body += ("\n" if body.endswith("\n") else "\n\n") if body else ""
        body += start + "\n" + section.rstrip() + "\n" + end
    else:
        prefix, tail = body.split(start)
        _, after = tail.split(end)
        body = prefix + start + "\n" + section.rstrip() + "\n" + end + after
    return f"[{state}] {suffix}", body


class RemoteFailure(Exception):
    def __init__(self, step: str, message: str):
        super().__init__(message)
        self.step = step


def gh_api(publication: dict, endpoint: str, method: str = "GET", payload=None, paginate: bool = False):
    command = ["gh", "api", "--hostname", publication["host"], endpoint, "--method", method]
    if paginate:
        command += ["--paginate", "--slurp"]
    if payload is not None:
        command += ["--input", "-"]
    try:
        completed = subprocess.run(command, input=json.dumps(payload) if payload is not None else None,
                                   capture_output=True, text=True, timeout=60)
        if completed.returncode:
            raise RemoteFailure("access", "GitHub access or mutation failed; reconcile before retrying")
        data = json.loads(completed.stdout, object_pairs_hook=unique_object)
        if isinstance(data, dict) and data.get("errors"):
            raise RemoteFailure("access", "GitHub could not establish the requested facts")
        if paginate:
            if not isinstance(data, list) or any(not isinstance(page, list) for page in data):
                raise RemoteFailure("inventory", "GitHub returned an incomplete or incompatible inventory")
            return [item for page in data for item in page]
        return data
    except (OSError, subprocess.TimeoutExpired, ValueError) as error:
        raise RemoteFailure("unknown", "GitHub outcome is unavailable; inspect before repeating a mutation") from error


def validate_usage(usage: dict) -> None:
    if not isinstance(usage, dict) or set(usage) != {"kind", "scope", "writers"}:
        raise ValueError("Report current worktree kind, ownership scope and owned writers")
    if usage["kind"] not in ("git", "managed") or usage["scope"] not in ("exclusive", "shared", "pinned"):
        raise ValueError("Unknown worktree ownership; reconcile with the native host")
    if not isinstance(usage["writers"], list):
        raise ValueError("Enumerate owned writers before snapshotting")
    for writer in usage["writers"]:
        if (not isinstance(writer, dict) or set(writer) != {"id", "state"}
                or not isinstance(writer["id"], str) or not writer["id"].strip()
                or writer["state"] not in ("stopped", "running", "unknown")):
            raise ValueError("Provide each writer's identity and observed state")
    if any(writer["state"] != "stopped" for writer in usage["writers"]):
        raise ValueError("Stop owned writers and confirm completion before snapshotting or cleanup")


def publish_paths(root: Path, files: list[str]) -> None:
    if (not isinstance(files, list) or not all(isinstance(name, str) for name in files)
            or len(set(files)) != len(files)):
        raise ValueError("Provide unique explicit publishable file paths")
    for name in files:
        if not isinstance(name, str) or not name or Path(name).is_absolute() or str(Path(name)) != name:
            raise ValueError("Publish paths must be explicit normalized relative file names")
        if any(part in ("..", ".git", ".codex-delegations", ".superpowers") for part in Path(name).parts):
            raise ValueError("Private task records and Git metadata are not publishable")
        if Path(name).name == "auth.json" or Path(name).name.startswith(".env"):
            raise ValueError("Credential-bearing files require separate manual review")
        safe_file(root / name)


def publication_snapshot(task: dict, files: list[str]) -> dict:
    binding, facts = setup_context(task)
    root = Path(binding["worktree"])
    publish_paths(root, files)
    payload = {"head": facts["head"], "files": {name: fingerprint(root / name) for name in files},
               "index": hashlib.sha256(git(root, "ls-files", "--stage", "-z").stdout.encode()).hexdigest()}
    return {**payload, "digest": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()}


def validate_publication(publication: dict) -> None:
    if not isinstance(publication, dict) or set(publication) != {"host", "repository", "remote", "base", "actor", "branches"}:
        raise ValueError("Specify publication host, repository, remote, base, actor and all task branches")
    patterns = {"host": r"[A-Za-z0-9][A-Za-z0-9.-]*", "repository": r"[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+",
                "remote": r"[A-Za-z0-9][A-Za-z0-9_.-]*", "actor": r"[A-Za-z0-9][A-Za-z0-9_-]*"}
    for key, pattern in patterns.items():
        if not isinstance(publication[key], str) or not re.fullmatch(pattern, publication[key]):
            raise ValueError("Use explicit non-secret GitHub publication identifiers")
    for branch in [publication["base"], *publication["branches"]] if isinstance(publication["branches"], list) else []:
        if not isinstance(branch, str) or not branch or branch.startswith("-") or any(c.isspace() for c in branch):
            raise ValueError("Use explicit branch names")
    if (not isinstance(publication["branches"], list) or not publication["branches"]
            or len(set(publication["branches"])) != len(publication["branches"])):
        raise ValueError("Declare every unique task-owned branch, including prior branches")


def validate_event(request: dict) -> None:
    fields = {"event_id", "kind", "milestone", "schedule", "publication", "usage", "files", "snapshot", "message",
              "title", "summary", "progress", "remaining", "blockers", "validation"}
    if not isinstance(request, dict) or set(request) != fields:
        raise ValueError("Provide exactly the documented lifecycle request fields")
    if len(json.dumps(request, allow_nan=False)) > 65536:
        raise ValueError("Lifecycle request exceeds 64 KiB")
    uuid_string(request["event_id"])
    if request["kind"] not in ("checkpoint", "blocker", "ready", "reopen"):
        raise ValueError("Choose checkpoint, blocker, ready or reopen")
    schedule = request["schedule"]
    if not isinstance(schedule, dict) or set(schedule) != {"mode", "ids"}:
        raise ValueError("Provide the planned milestone schedule")
    if request["milestone"] not in validate_schedule(schedule["mode"], schedule["ids"]):
        raise ValueError("Event must name a planned milestone")
    for key in ("message", "title", "summary", "progress", "remaining", "blockers"):
        if not isinstance(request[key], str) or len(request[key]) > 8192 or "\0" in request[key]:
            raise ValueError("Lifecycle content must be bounded text without NUL")
    if not all(request[key].strip() for key in ("message", "title", "summary")):
        raise ValueError("Provide a commit message, title and summary")
    if request["kind"] == "ready" and request["blockers"].strip():
        raise ValueError("Resolve implementation blockers before requesting readiness")
    if request["kind"] == "blocker" and not request["blockers"].strip():
        raise ValueError("Describe the blocker and resumption condition")
    validate_publication(request["publication"])
    validate_usage(request["usage"])
    if not isinstance(request["snapshot"], str) or not re.fullmatch(r"[0-9a-f]{64}", request["snapshot"]):
        raise ValueError("Provide the inspected publication snapshot digest")
    validation = request["validation"]
    if not isinstance(validation, dict) or set(validation) != {"snapshot", "checks", "review"}:
        raise ValueError("Provide checks and independent review evidence for this snapshot")
    if not isinstance(validation["checks"], list) or validation["snapshot"] != request["snapshot"]:
        raise ValueError("Local acceptance must refer to the exact publication snapshot")
    for entry in [*validation["checks"], validation["review"]]:
        if (not isinstance(entry, dict) or set(entry) != {"name", "outcome", "path", "sha256"}
                or not all(isinstance(entry[key], str) for key in entry)
                or entry["outcome"] not in ("passed", "failed", "not_run") or not entry["name"].strip()):
            raise ValueError("Provide named validation outcomes and local evidence fingerprints")
        observed = fingerprint(Path(entry["path"]))
        if observed is None or observed["sha256"] != entry["sha256"]:
            raise ValueError("Local validation evidence is missing or changed")
    if request["kind"] == "ready" and (not validation["checks"] or any(
            entry["outcome"] != "passed" for entry in [*validation["checks"], validation["review"]])):
        raise ValueError("Current local checks and independent review must pass before readiness")


def lifecycle_path(binding: dict) -> Path:
    return canonical(Path(binding["common_dir"]) / "vibe-setup/lifecycle") / f"{binding['task_id']}.json"


def read_lifecycle(path: Path) -> dict:
    safe_file(path)
    state = json.loads(path.read_text(), object_pairs_hook=unique_object)
    keys = {"schema_version", "binding", "publication", "schedule", "events", "prs", "sections", "last_ready", "cleanup"}
    if (not isinstance(state, dict) or set(state) != keys or type(state["schema_version"]) is not int
            or state["schema_version"] != 1 or not isinstance(state["binding"], dict)
            or state["binding"].get("task_id") != path.stem):
        raise ValueError("Reconcile incompatible lifecycle state")
    validate_publication(state["publication"])
    if any(not isinstance(state[key], dict) for key in ("events", "sections", "cleanup")) or not isinstance(state["prs"], list):
        raise ValueError("Reconcile malformed lifecycle records")
    return state


@contextlib.contextmanager
def lifecycle_lock(common: Path):
    directory = canonical(common / "vibe-setup")
    setup_directory(directory)
    path = directory / "lifecycle.lock"
    safe_file(path)
    with path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RemoteFailure("lock", "Another lifecycle operation is running; retry after it finishes") from error
        yield


def save_lifecycle(state: dict) -> None:
    path = lifecycle_path(state["binding"])
    setup_directory(path.parent)
    write_record(path, state)


def publication_access(root: Path, publication: dict) -> dict:
    validate_publication(publication)
    for branch in [publication["base"], *publication["branches"]]:
        if git(root, "check-ref-format", f"refs/heads/{branch}", check=False).returncode:
            raise ValueError("Invalid publication branch")
    expected = (publication["host"].lower(), publication["repository"].lower())
    for mode in ((), ("--push",)):
        urls = git(root, "remote", "get-url", *mode, "--all", publication["remote"]).stdout.splitlines()
        if len(urls) != 1:
            raise RemoteFailure("remote", "Select one unambiguous fetch/push destination")
        url = urls[0]
        match = re.fullmatch(r"git@([^:]+):(.+?)(?:\.git)?", url)
        if match:
            actual = (match[1].lower(), match[2].removesuffix(".git").lower())
        else:
            parsed = urlsplit(url)
            if parsed.scheme not in ("https", "ssh") or parsed.password or parsed.query or parsed.fragment:
                raise RemoteFailure("remote", "Verify the existing Git transport manually; credentials were not changed")
            if parsed.scheme == "https" and parsed.username:
                raise RemoteFailure("remote", "Credential-bearing remote requires manual reconciliation")
            actual = ((parsed.hostname or "").lower(), parsed.path.strip("/").removesuffix(".git").lower())
        if actual != expected:
            raise RemoteFailure("remote", "Git transport does not match the selected GitHub repository")
    if gh_api(publication, "user").get("login", "").lower() != publication["actor"].lower():
        raise RemoteFailure("actor", "Confirm the GitHub actor; no account was switched")
    repo = gh_api(publication, f"repos/{publication['repository']}")
    if not isinstance(repo, dict) or repo.get("full_name", "").lower() != publication["repository"].lower():
        raise RemoteFailure("repository", "GitHub resolved a different repository; reconcile its identity")
    if not isinstance(repo.get("default_branch"), str) or not repo["default_branch"]:
        raise RemoteFailure("repository", "Remote default branch is unknown; preserve resources")
    return repo


def inventory_prs(publication: dict) -> list[dict]:
    inventory = {}
    owner = publication["repository"].split("/")[0]
    for branch in publication["branches"]:
        endpoint = f"repos/{publication['repository']}/pulls?state=all&head={quote(owner + ':' + branch, safe='')}&per_page=100"
        matches = gh_api(publication, endpoint, paginate=True)
        if not isinstance(matches, list):
            raise RemoteFailure("inventory", "PR inventory is incomplete")
        for pr in matches:
            if (not isinstance(pr, dict) or type(pr.get("number")) is not int or pr["number"] <= 0
                    or pr.get("head", {}).get("ref") != branch
                    or (pr.get("head", {}).get("repo") or {}).get("full_name", "").lower() != publication["repository"].lower()):
                raise RemoteFailure("inventory", "PR inventory has missing or ambiguous identities")
            inventory[pr["number"]] = pr
    return list(inventory.values())


def remote_head(root: Path, publication: dict, branch: str) -> str | None:
    try:
        output = git(root, "ls-remote", "--heads", "--", publication["remote"], f"refs/heads/{branch}").stdout.strip()
    except ValueError as error:
        raise RemoteFailure("remote", "Remote branch could not be inspected") from error
    if not output:
        return None
    fields = output.split()
    if len(fields) != 2 or fields[1] != f"refs/heads/{branch}" or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", fields[0]):
        raise RemoteFailure("remote", "Remote branch identity is ambiguous")
    return fields[0]


def manual_actions(failure: dict, observed: dict) -> list[dict]:
    publication = observed["publication"]
    root, branch = observed["worktree"], observed["branch"]
    message = failure["message"] + ". Look up existing PRs before creation; preserve current credentials and permissions."
    if failure["step"] == "draft":
        message = "Use Ready for review on the existing PR, keep [BLOCKED], then resume this event."
    if failure["step"] == "demote":
        message = "Restore [BLOCKED] on the existing PR before changing its implementation, then resume."
    return [{"code": failure["step"], "message": message, "worktree": root, "branch": branch,
             "base": publication["base"], "remote": publication["remote"], "commit": observed.get("head"),
             "pr": observed.get("pr"), "event_id": observed.get("event_id"),
             "lookup_command": shlex.join(["gh", "pr", "list", "--repo", publication["host"] + "/" + publication["repository"],
                                             "--head", branch, "--state", "all"]),
             "push_command": shlex.join(["git", "-C", root, "push", publication["remote"], f"HEAD:refs/heads/{branch}"])}]


def event_section(event: dict) -> str:
    request = event["request"]
    validation = request["validation"]
    checks = "; ".join(f"{entry['name']}: {entry['outcome']}" for entry in [*validation["checks"], validation["review"]])
    return (f"### Summary\n{request['summary']}\n\n### Progress\n{request['progress']}\n"
            f"\nMilestone: {request['milestone']}\nEvent: {request['event_id']}\nCommit: {event['commit']}\n"
            f"\n### Validation\n{checks}\nLocal evidence supplied by the coordinator for the recorded snapshot.\n"
            f"\n### Remaining work\n{request['remaining']}\n\n### Blockers and resumption\n{request['blockers'] or 'None reported.'}")


def update_metadata(state: dict, event: dict, pr: dict, tag: str) -> dict:
    publication, task_id = state["publication"], state["binding"]["task_id"]
    endpoint = f"repos/{publication['repository']}/pulls/{pr['number']}"
    latest = gh_api(publication, endpoint)
    inner = managed_section(latest.get("body") or "", task_id)
    section = event_section(event)
    known = state["sections"].get(str(pr["number"]))
    if inner is not None and inner not in (known, "\n" + section + "\n"):
        raise RemoteFailure("metadata", "Managed PR content changed; reconcile the human edit before updating")
    if inner is None and known is not None:
        raise RemoteFailure("metadata", "Managed PR section was removed; reconcile before updating")
    title, body = render_pr(latest["title"], latest.get("body") or "", task_id, tag, section)
    if title != latest["title"] or body != (latest.get("body") or ""):
        event["metadata_intent"] = {"number": pr["number"], "title": title, "body": body}
        if tag == "READY":
            # A lost response may hide a live READY title; pause until withdrawal is established.
            state["last_ready"] = True
        save_lifecycle(state)
        gh_api(publication, endpoint, "PATCH", {"title": title, "body": body})
    observed = gh_api(publication, endpoint)
    if (observed.get("title") != title or (observed.get("body") or "") != body
            or observed.get("head", {}).get("sha") != event["commit"] or observed.get("state") != "open"):
        raise RemoteFailure("metadata", "PR readback differs from the intended update; reconcile before retrying")
    state["sections"][str(pr["number"])] = "\n" + section + "\n"
    state["last_ready"] = tag == "READY"
    save_lifecycle(state)
    return observed


def readiness(publication: dict, pr: dict) -> bool:
    endpoint = f"repos/{publication['repository']}"
    branch = gh_api(publication, endpoint + "/branches/" + quote(publication["base"], safe=""))
    rules = gh_api(publication, endpoint + "/rules/branches/" + quote(publication["base"], safe=""))
    if type(branch.get("protected")) is not bool or not isinstance(rules, list):
        raise RemoteFailure("readiness", "Remote requirements could not be established")
    owner, name = publication["repository"].split("/")
    query = """query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){pullRequest(number:$number){isDraft headRefOid mergeable mergeStateStatus reviewDecision commits(last:1){nodes{commit{statusCheckRollup{state}}}}}}}"""
    data = gh_api(publication, "graphql", "POST", {"query": query, "variables": {"owner": owner, "name": name, "number": pr["number"]}})
    try:
        current = data["data"]["repository"]["pullRequest"]
        rollup = current["commits"]["nodes"][0]["commit"]["statusCheckRollup"]
        return (current["isDraft"] is False and current["headRefOid"] == pr["head"]["sha"]
                and current["mergeable"] == "MERGEABLE" and current["mergeStateStatus"] == "CLEAN"
                and current["reviewDecision"] in ("", None, "APPROVED")
                and (rollup is None or rollup.get("state") == "SUCCESS"))
    except (KeyError, IndexError, TypeError) as error:
        raise RemoteFailure("readiness", "Remote readiness facts are incomplete") from error


def prepare_commit(state: dict, event: dict, task: dict) -> str | None:
    binding, facts = setup_context(task)
    root, request = Path(binding["worktree"]), event["request"]
    if event.get("commit"):
        if facts["head"] != event["commit"] or any(fingerprint(root / name) != value for name, value in event["snapshot"]["files"].items()):
            raise ValueError("Published snapshot changed; start a new planned event after withdrawing readiness")
        return None if event.get("no_diff") else event["commit"]
    current = publication_snapshot(task, request["files"])
    if event.get("commit_intent") and facts["head"] != event["snapshot"]["head"]:
        expected = event["commit_intent"]
        if (git(root, "rev-parse", "HEAD^").stdout.strip() != event["snapshot"]["head"]
                or git(root, "rev-parse", "HEAD^{tree}").stdout.strip() != expected
                or f"Vibe-Event: {request['event_id']}" not in git(root, "log", "-1", "--format=%B").stdout):
            raise ValueError("HEAD changed during an uncertain commit; inspect without making another commit")
        if current["files"] != event["snapshot"]["files"]:
            raise ValueError("Files changed during the interrupted commit; inspect before pushing")
        event["commit"] = facts["head"]
        save_lifecycle(state)
        return facts["head"]
    if current["files"] != event["snapshot"]["files"] or current["head"] != event["snapshot"]["head"]:
        raise ValueError("Publication snapshot changed; preserve current work and inspect again")
    staged = set(git(root, "diff", "--cached", "--name-only", "-z").stdout.rstrip("\0").split("\0")) - {""}
    if not staged <= set(request["files"]):
        raise ValueError("Unrelated staged work is present; preserve it before publication")
    if request["files"]:
        git(root, "add", "--", *(":(literal)" + name for name in request["files"]))
    if any(fingerprint(root / name) != value for name, value in event["snapshot"]["files"].items()):
        raise ValueError("Files changed while staging; stop moving writers and reconcile")
    if git(root, "diff", "--cached", "--quiet", check=False).returncode:
        author, committer = effective_identity(root, "AUTHOR"), effective_identity(root, "COMMITTER")
        configured = {key: git(root, "config", "--get", f"user.{key}", check=False).stdout.strip() for key in ("name", "email")}
        if not all(configured.values()) or author != configured or committer != configured:
            raise RemoteFailure("identity", "Confirm the effective commit identity; no Git setting was changed")
        event["commit_intent"] = git(root, "write-tree").stdout.strip()
        save_lifecycle(state)
        setup_context(task)
        git(root, "commit", "-m", request["message"], "-m", f"Vibe-Event: {request['event_id']}")
        if (git(root, "rev-parse", "HEAD^{tree}").stdout.strip() != event["commit_intent"]
                or git(root, "rev-parse", "HEAD^").stdout.strip() != event["snapshot"]["head"]
                or any(fingerprint(root / name) != value for name, value in event["snapshot"]["files"].items())):
            raise ValueError("Commit hooks changed the reviewed snapshot; inspect before pushing")
    head = git(root, "rev-parse", "HEAD").stdout.strip()
    event["commit"] = head
    event["no_diff"] = git(root, "diff", "--quiet", binding["base_commit"], head, check=False).returncode == 0
    save_lifecycle(state)
    return None if event["no_diff"] else head


def sync_event(request: dict, task: dict) -> dict:
    state, event, binding, head = None, None, None, None
    try:
        validate_event(request)
        binding, facts = setup_context(task)
        head = facts["head"]
        root = Path(binding["worktree"])
        if binding["branch"] not in request["publication"]["branches"]:
            raise ValueError("Register the task branch in the publication inventory")
        if not load_policy(root):
            return result("sync", "ok", "disabled", delivery="disabled", cleanup="disabled")
        path = lifecycle_path(binding)
        with lifecycle_lock(Path(binding["common_dir"])):
            state = read_lifecycle(path) if path.exists() else {
                "schema_version": 1, "binding": binding, "publication": request["publication"],
                "schedule": request["schedule"], "events": {}, "prs": [], "sections": {},
                "last_ready": False, "cleanup": {}}
            if state["binding"] != binding or state["publication"] != request["publication"] or state["schedule"] != request["schedule"]:
                raise ValueError("Task publication binding or schedule changed; reconcile existing state")
            event = state["events"].get(request["event_id"])
            if event and {key: value for key, value in event["request"].items() if key != "usage"} != {
                    key: value for key, value in request.items() if key != "usage"}:
                raise ValueError("Reuse an event ID only with its original request")
            if event:
                event["request"]["usage"] = copy.deepcopy(request["usage"])
            if not event:
                for previous in state["events"].values():
                    old = previous["request"]
                    if (request["kind"] in ("checkpoint", "ready") and old["kind"] in ("checkpoint", "ready")
                            and old["milestone"] == request["milestone"]):
                        raise ValueError("Reuse the existing milestone event rather than creating extra checkpoints")
                snapshot = publication_snapshot(task, request["files"])
                if snapshot["digest"] != request["snapshot"]:
                    raise ValueError("Publication preview is stale; inspect the exact snapshot again")
                event = {"request": copy.deepcopy(request), "snapshot": snapshot, "commit": None, "delivered": False}
                state["events"][request["event_id"]] = event
                save_lifecycle(state)
            publication_access(root, state["publication"])
            prs = inventory_prs(state["publication"])
            known = {pr["number"] for pr in state["prs"]}
            if not known <= {pr["number"] for pr in prs}:
                raise RemoteFailure("inventory", "A previously associated PR is missing; preserve resources")
            if prs and all(pr.get("merged_at") for pr in prs):
                return _cleanup_worktree(state, request["usage"])
            candidates = [pr for pr in prs if pr["head"]["ref"] == binding["branch"]]
            if len(candidates) > 1 or any(pr.get("state") != "open" for pr in candidates):
                raise RemoteFailure("inventory", "Closed, merged or multiple PR matches require reconciliation")
            pr = candidates[0] if candidates else None
            if pr and pr["base"].get("ref") != state["publication"]["base"]:
                raise RemoteFailure("inventory", "Existing PR targets another base")
            intent = event.get("metadata_intent", {})
            if (pr and request["kind"] == "ready" and pr["title"].startswith("[READY] ")
                    and intent == {"number": pr["number"], "title": pr["title"], "body": pr.get("body") or ""}
                    and pr["head"]["sha"] == event.get("commit")):
                # A lost update response must not repeat an already observed mutation.
                event["delivered"] = True
                state["sections"][str(pr["number"])] = "\n" + event_section(event) + "\n"
                state["last_ready"] = True
                save_lifecycle(state)
            # Withdraw an existing readiness claim before staging or pushing new work.
            if pr and pr["title"].startswith("[READY] ") and not event["delivered"]:
                try:
                    gh_api(state["publication"], f"repos/{state['publication']['repository']}/pulls/{pr['number']}",
                           "PATCH", {"title": "[BLOCKED] " + pr["title"][len("[READY] "):]})
                    pr = gh_api(state["publication"], f"repos/{state['publication']['repository']}/pulls/{pr['number']}")
                    if not pr["title"].startswith("[BLOCKED] "):
                        raise RemoteFailure("demote", "Readiness withdrawal was not observed")
                    state["last_ready"] = False
                    save_lifecycle(state)
                except RemoteFailure as error:
                    raise RemoteFailure("demote", "Restore [BLOCKED] before further implementation") from error
            if request["kind"] == "reopen":
                if not pr:
                    raise RemoteFailure("inventory", "Locate the existing PR before resuming changes")
                event["delivered"] = True
                save_lifecycle(state)
                return result("sync", "ok", "worktree_verified", delivery="synchronized", evidence_ref=str(path), pr=pr["html_url"])
            head = prepare_commit(state, event, task)
            if head is None:
                event["delivered"] = True
                save_lifecycle(state)
                return result("sync", "ok", "worktree_verified", delivery="not_needed", evidence_ref=str(path))
            current = remote_head(root, state["publication"], binding["branch"])
            if current != head:
                setup_context(task)
                try:
                    git(root, "push", state["publication"]["remote"], f"{head}:refs/heads/{binding['branch']}")
                except ValueError as error:
                    raise RemoteFailure("push", "Normal push failed; reconcile divergence or existing access without force") from error
                if remote_head(root, state["publication"], binding["branch"]) != head:
                    raise RemoteFailure("push", "Remote commit readback differs; publication remains pending")
            if pr is None:
                if event.get("create_attempted"):
                    raise RemoteFailure("create_unknown", "Creation outcome is uncertain; look up the existing PR before another attempt")
                title, body = render_pr(request["title"], "", binding["task_id"], "BLOCKED", event_section(event))
                event["create_attempted"] = True
                save_lifecycle(state)
                pr = gh_api(state["publication"], f"repos/{state['publication']['repository']}/pulls", "POST",
                            {"title": title, "body": body, "base": state["publication"]["base"],
                             "head": binding["branch"], "draft": True})
            if pr.get("head", {}).get("sha") != head:
                # GitHub may lag the push; a subsequent reconciliation rereads it.
                pr = gh_api(state["publication"], f"repos/{state['publication']['repository']}/pulls/{pr['number']}")
            if pr["head"]["sha"] != head:
                raise RemoteFailure("head", "PR head does not match the published commit")
            state["prs"] = [{"number": item["number"], "branch": item["head"]["ref"], "head": item["head"]["sha"]}
                            for item in {item["number"]: item for item in [*prs, pr]}.values()]
            save_lifecycle(state)
            if event["delivered"]:
                inner = managed_section(pr.get("body") or "", binding["task_id"])
                expected_tag = "[READY] " if request["kind"] == "ready" else "[BLOCKED] "
                if inner != state["sections"].get(str(pr["number"])) or not pr["title"].startswith(expected_tag):
                    raise RemoteFailure("metadata", "PR changed after synchronization; reconcile the observed edits")
                if request["kind"] == "ready" and not readiness(state["publication"], pr):
                    update_metadata(state, event, pr, "BLOCKED")
                    event["delivered"] = False
                    save_lifecycle(state)
                    raise RemoteFailure("readiness", "Remote readiness changed; [BLOCKED] restored")
            else:
                pr = update_metadata(state, event, pr, "BLOCKED")
                if request["kind"] == "ready":
                    if pr.get("draft"):
                        query = "mutation($id:ID!){markPullRequestReadyForReview(input:{pullRequestId:$id}){pullRequest{isDraft}}}"
                        try:
                            gh_api(state["publication"], "graphql", "POST", {"query": query, "variables": {"id": pr["node_id"]}})
                        except RemoteFailure as error:
                            raise RemoteFailure("draft", "Ready for review transition failed") from error
                        pr = gh_api(state["publication"], f"repos/{state['publication']['repository']}/pulls/{pr['number']}")
                    if pr.get("draft") or not readiness(state["publication"], pr):
                        raise RemoteFailure("readiness", "Remote checks, reviews or mergeability are not ready; retain [BLOCKED]")
                    pr = update_metadata(state, event, pr, "READY")
            event["delivered"] = True
            save_lifecycle(state)
            return result("sync", "ok", "ready" if request["kind"] == "ready" else "worktree_verified",
                          delivery="synchronized", pr=pr["html_url"], commit=head, event_id=request["event_id"],
                          evidence_ref=str(path), next_action="Attach this PR to the native task; merge remains a human decision")
    except RemoteFailure as error:
        observed = {**(binding or task), "publication": request["publication"], "head": head,
                    "event_id": request["event_id"], "pr": (state or {}).get("prs", [])}
        pause = error.step == "demote" or bool(state and state["last_ready"] and not (event and event["delivered"]))
        return result("sync", "blocked" if pause else "action_required",
                      "paused_for_pr" if pause else ("ready" if request["kind"] == "ready" else "worktree_verified"),
                      delivery="pending", evidence_ref=str(lifecycle_path(binding)) if binding else None,
                      failure_step=error.step,
                      pending_user_actions=manual_actions({"step": error.step, "message": str(error)}, observed),
                      next_action="PR synchronization pending; complete the named action and resume the same event")
    except (ValueError, OSError) as error:
        return result("sync", "blocked", "not_ready", delivery="pending",
                      next_action=str(error) if isinstance(error, ValueError) else "Filesystem operation interrupted; reconcile the same event")
    except (KeyError, TypeError, AttributeError, IndexError):
        return result("sync", "blocked", "not_ready", delivery="pending",
                      next_action="Malformed request, lifecycle record or remote response; preserve resources and reconcile")


def resume_lifecycle(root: Path, operation_id: str, confirmation: dict | None = None, *, usage: dict | None = None) -> dict:
    common = Path(repository(root)["common_dir"])
    matches = [read_lifecycle(path) for path in canonical(common / "vibe-setup/lifecycle").glob("*.json")]
    matches = [state for state in matches if operation_id in state["events"]]
    if not matches:
        raise FileNotFoundError("No existing setup or lifecycle operation")
    if len(matches) != 1:
        raise ValueError("Select one existing setup or lifecycle operation")
    validate_usage(usage)
    state = matches[0]
    event = state["events"][operation_id]
    request = {**event["request"], "usage": usage}
    task = {key: state["binding"][key] for key in ("task_id", "worktree")}
    if event["delivered"] or not Path(task["worktree"]).exists():
        return cleanup_worktree({**task, "source": str(root), "usage": usage})
    response = sync_event(request, task)
    if confirmation is not None:
        if (not isinstance(confirmation, dict) or set(confirmation) != {"actor", "head", "pr_number", "actions"}
                or not isinstance(confirmation["actor"], str) or not confirmation["actor"].strip()
                or type(confirmation["pr_number"]) is not int or confirmation["pr_number"] <= 0
                or not isinstance(confirmation["actions"], list)
                or not all(isinstance(action, str) for action in confirmation["actions"])
                or set(confirmation["actions"]) not in ({"publication", "metadata", "non_draft", "readiness"}, {"readiness_withdrawal"})):
            raise ValueError("Provide an attributed confirmation of full readiness or readiness withdrawal")
        _, facts = setup_context(task)
        if confirmation["head"] != facts["head"]:
            raise ValueError("User confirmation must name the current commit")
        if confirmation["actions"] == ["readiness_withdrawal"]:
            known = [pr for pr in state["prs"] if pr["number"] == confirmation["pr_number"]
                     and pr["branch"] == state["binding"]["branch"] and pr["head"] == facts["head"]]
            if not known:
                raise ValueError("Confirm withdrawal only for this task's known PR and current published head")
            if response["implementation"] == "paused_for_pr":
                with lifecycle_lock(common):
                    current = read_lifecycle(lifecycle_path(state["binding"]))
                    current["events"][operation_id]["readiness_withdrawal_confirmation"] = confirmation
                    current["last_ready"] = False
                    save_lifecycle(current)
                return result("resume", "ok", "worktree_verified", delivery="user_confirmed", cleanup="unverified",
                              confirmation_source=confirmation["actor"], evidence_ref=str(lifecycle_path(state["binding"])),
                              next_action="BLOCKED title is user-confirmed; local work may resume, remote publication remains unverified")
            return {**response, "operation": "resume"}
        if (response["status"] == "action_required" and request["kind"] == "ready"
                and response.get("failure_step") in ("access", "unknown", "remote", "actor", "identity", "create_unknown")):
            target = Path(task["worktree"])
            if (any(fingerprint(target / name) != value for name, value in event["snapshot"]["files"].items())
                    or git(target, "status", "--porcelain=v1", "--untracked-files=all", "--", *(":(literal)" + name for name in request["files"])).stdout
                    or facts["head"] == event["snapshot"]["head"] and not event.get("commit")):
                raise ValueError("Commit the reviewed snapshot before confirming manual publication")
            changed = set(git(target, "diff", "--name-only", "-z", event["snapshot"]["head"], facts["head"]).stdout.rstrip("\0").split("\0")) - {""}
            if not changed <= set(request["files"]):
                raise ValueError("Manual commit includes unrelated files; inspect before confirmation")
            with lifecycle_lock(common):
                current = read_lifecycle(lifecycle_path(state["binding"]))
                current["events"][operation_id]["user_confirmation"] = confirmation
                current["events"][operation_id]["commit"] = facts["head"]
                save_lifecycle(current)
            response = result("resume", "ok", "ready", delivery="user_confirmed", cleanup="unverified",
                              confirmation_source=confirmation["actor"], evidence_ref=str(lifecycle_path(state["binding"])),
                              next_action="Remote facts remain user-confirmed; automatic cleanup still requires observed merged PRs")
    return {**response, "operation": "resume"}


def cleanup_local_safety(state: dict, usage: dict) -> None:
    binding = state["binding"]
    root, source = Path(binding["worktree"]), Path(binding["source"])
    validate_usage(usage)
    if usage["kind"] != "git" or usage["scope"] != "exclusive":
        raise ValueError("Preserve shared/pinned worktrees; managed worktrees require their native lifecycle")
    if Path.cwd().resolve().is_relative_to(root):
        raise ValueError("Move coordinator and command context outside the worktree before cleanup")
    facts = verify_worktree(source, root, binding["branch"])
    entries = worktrees(source)
    if any(entry.get("worktree") == str(root) and "locked" in entry for entry in entries):
        raise ValueError("Worktree is locked; preserve it and inspect its owner")
    if git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignored").stdout:
        raise ValueError("Preserve dirty, untracked or ignored files before cleanup")
    if state["cleanup"].get("heads") and facts["head"] != state["cleanup"]["heads"].get(binding["branch"]):
        raise ValueError("Local commits extend beyond the confirmed merged PR head")
    branches = set(state["publication"]["branches"])
    for entry in entries:
        if entry.get("worktree") != str(root) and entry.get("branch", "").removeprefix("refs/heads/") in branches:
            raise ValueError("Another worktree uses an associated branch; preserve shared resources")
    for path in (Path(binding["common_dir"]) / "vibe-setup/tasks").glob("*.json"):
        other = read_record(path)
        if other["task_id"] != binding["task_id"] and (other["worktree"] == str(root) or other["branch"] in branches):
            raise ValueError("Another task owns this worktree or an associated branch")


def _cleanup_worktree(state: dict, usage: dict) -> dict:
    binding, publication = state["binding"], state["publication"]
    root, source = canonical(Path(binding["worktree"])), canonical(Path(binding["source"]))
    path = lifecycle_path(binding)
    merged_count = 0
    try:
        validate_usage(usage)
        if not load_cleanup_policy(source) or (root.exists() and not load_cleanup_policy(root)):
            return result("cleanup", "ok", "worktree_verified", cleanup="disabled", delivery="not_checked",
                          evidence_ref=str(path), next_action="Automatic cleanup opted out; resources retained")
        if state["cleanup"].get("state") == "complete":
            if root.exists() or any(entry.get("worktree") == str(root) for entry in worktrees(source)):
                raise ValueError("Removed worktree path or registration reappeared; preserve the new resource")
            return result("cleanup", "ok", "merged", delivery="merged", cleanup="complete", evidence_ref=str(path),
                          cleanup_checks=state["cleanup"]["checks"])
        repo = publication_access(source, publication)
        prs = inventory_prs(publication)
        known = {pr["number"]: pr for pr in state["prs"]}
        if not prs or not known or not set(known) <= {pr["number"] for pr in prs}:
            raise ValueError("Confirm the complete nonempty associated PR inventory before cleanup")
        for pr in prs:
            if pr.get("state") != "closed" or not pr.get("merged_at") or pr.get("draft") is not False:
                raise ValueError("Every associated PR must be observed merged and non-draft")
            if managed_section(pr.get("body") or "", binding["task_id"]) is None:
                raise ValueError("PR ownership is ambiguous; register/reconcile it before cleanup")
            old = known.get(pr["number"])
            if old and (old["branch"] != pr["head"]["ref"] or old["head"] != pr["head"]["sha"]):
                raise ValueError("An associated PR head changed after publication; reconcile its ownership")
        merged_count = len(prs)
        previous = state["cleanup"]
        if not root.exists():
            if previous.get("local") != "removing" or any(entry.get("worktree") == str(root) for entry in worktrees(source)):
                raise ValueError("Worktree disappeared without confirmed removal intent; reconcile registration")
        else:
            cleanup_local_safety(state, usage)
        heads = {}
        observed_remote = {}
        for branch in publication["branches"]:
            if branch == repo.get("default_branch"):
                raise ValueError("Never clean up the remote default branch")
            candidates = {pr["head"]["sha"] for pr in prs if pr["head"]["ref"] == branch}
            if not candidates:
                raise ValueError("An associated branch has no confirmed merged PR")
            local = git(source, "rev-parse", "--verify", f"refs/heads/{branch}", check=False).stdout.strip()
            expected = previous.get("heads", {}).get(branch) or (local if local in candidates else None)
            if expected is None and len(candidates) == 1:
                expected = next(iter(candidates))
            if expected not in candidates:
                raise ValueError("Merged branch head is ambiguous; preserve it for manual review")
            if local and local != expected:
                raise ValueError("Local branch has commits beyond its confirmed merged head")
            heads[branch] = expected
            observed_remote[branch] = remote_head(source, publication, branch)
            if branch in previous.get("deleted", []) and observed_remote[branch] is not None:
                raise ValueError("Previously deleted branch was recreated; preserve it")
            if observed_remote[branch] not in (None, expected):
                raise ValueError("Remote branch advanced or was reused; preserve it")
            if observed_remote[branch] is not None:
                info = gh_api(publication, f"repos/{publication['repository']}/branches/{quote(branch, safe='')}")
                rules = gh_api(publication, f"repos/{publication['repository']}/rules/branches/{quote(branch, safe='')}")
                if info.get("protected") is not False or not isinstance(rules, list) or rules:
                    raise ValueError("Protected or rule-governed branches require manual cleanup")
        if previous.get("heads") and previous["heads"] != heads:
            raise ValueError("Cleanup branch inventory changed; preserve resources")
        if not previous:
            state["cleanup"] = {"state": "pending", "heads": heads, "deleted": [], "local": "pending",
                                "prs": sorted(pr["number"] for pr in prs)}
            save_lifecycle(state)
        elif previous["prs"] != sorted(pr["number"] for pr in prs):
            raise ValueError("Cleanup PR inventory changed after intent; reconcile before deletion")
        cleanup = state["cleanup"]
        if root.exists():
            cleanup_local_safety(state, usage)
        for branch, expected in heads.items():
            if not load_cleanup_policy(source) or (root.exists() and not load_cleanup_policy(root)):
                raise ValueError("Cleanup preference changed; preserve remaining resources")
            current = remote_head(source, publication, branch)
            if branch in cleanup["deleted"] and current is not None:
                raise ValueError("Deleted branch was recreated; preserve it")
            if current not in (None, expected):
                raise ValueError("Remote branch changed before conditional deletion")
            if current is not None:
                if root.exists():
                    cleanup_local_safety(state, usage)
                try:
                    git(source, "push", f"--force-with-lease=refs/heads/{branch}:{expected}",
                        publication["remote"], f":refs/heads/{branch}")
                except ValueError as error:
                    if remote_head(source, publication, branch) is not None:
                        raise RemoteFailure("cleanup_branch", "Conditional branch deletion failed; preserve the worktree") from error
            if remote_head(source, publication, branch) is not None:
                raise RemoteFailure("cleanup_branch", "Remote absence was not confirmed; preserve the worktree")
            if branch not in cleanup["deleted"]:
                cleanup["deleted"].append(branch)
                save_lifecycle(state)
        if any(remote_head(source, publication, branch) is not None for branch in heads):
            raise ValueError("A remote branch reappeared; preserve the worktree")
        if root.exists():
            cleanup_local_safety(state, usage)
            if not load_cleanup_policy(source) or not load_cleanup_policy(root):
                raise ValueError("Cleanup opted out before local removal; preserve the worktree")
            cleanup["local"] = "removing"
            save_lifecycle(state)
            try:
                git(source, "worktree", "remove", str(root))
            except ValueError as error:
                if root.exists() or any(entry.get("worktree") == str(root) for entry in worktrees(source)):
                    raise RemoteFailure("cleanup_local", "Local removal failed; preserve the folder and resume from outside it") from error
        if root.exists() or any(entry.get("worktree") == str(root) for entry in worktrees(source)):
            raise ValueError("Worktree removal was not confirmed")
        cleanup.update(state="complete", local="removed", checks={"merged_prs": merged_count,
                       "branches_absent": len(heads), "worktree_removed": True})
        save_lifecycle(state)
        return result("cleanup", "ok", "merged", delivery="merged", cleanup="complete", evidence_ref=str(path),
                      cleanup_checks=cleanup["checks"], next_action="Remote branches and worktree removed; local branch refs retained")
    except (ValueError, OSError, RemoteFailure, KeyError, TypeError, AttributeError, IndexError) as error:
        message = str(error) if not isinstance(error, OSError) else "Cleanup filesystem action interrupted; preserve progress"
        if isinstance(error, (KeyError, TypeError, AttributeError, IndexError)):
            message = "Malformed cleanup record or remote response; preserve resources and reconcile"
        return result("cleanup", "action_required", "merged" if merged_count else "worktree_verified",
                      delivery="merged" if merged_count else "not_checked", cleanup="pending", evidence_ref=str(path),
                      pending_user_actions=[{"code": "cleanup", "message": message, "worktree": str(root),
                                             "resume_from": str(source), "task_id": binding["task_id"]}],
                      next_action="Cleanup pending: " + message)


def cleanup_worktree(task: dict) -> dict:
    try:
        if (not isinstance(task, dict) or not {"task_id", "worktree", "usage"} <= task.keys()
                or set(task) - {"task_id", "worktree", "usage", "source"}):
            raise ValueError("Provide task_id, worktree, current usage and an outside source for recovery")
        task_id = uuid_string(task["task_id"])
        root = canonical(Path(task["worktree"]))
        anchor = canonical(Path(task.get("source", str(root))))
        common = Path(repository(anchor)["common_dir"])
        binding = read_record(common / "vibe-setup/tasks" / f"{task_id}.json")
        if binding["worktree"] != str(root) or binding["common_dir"] != str(common) or binding["state"] != "verified":
            raise ValueError("Cleanup task binding does not match the selected worktree")
        with lifecycle_lock(common):
            state = read_lifecycle(lifecycle_path(binding))
            if state["binding"] != binding:
                raise ValueError("Lifecycle ownership changed; preserve the worktree")
            return _cleanup_worktree(state, task["usage"])
    except (ValueError, OSError, RemoteFailure) as error:
        return result("cleanup", "action_required", "not_ready", cleanup="pending",
                      next_action=str(error) if not isinstance(error, OSError) else "No usable cleanup inventory; preserve resources")


def unique_object(pairs: list[tuple]) -> dict:
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError("Duplicate JSON field; provide one unambiguous value")
        data[key] = value
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("inspect", "start", "apply", "sync", "resume"))
    parser.add_argument("root", type=Path, help="Selected project/source checkout")
    parser.add_argument("--client", action="append", choices=("app", "vscode"), default=[])
    parser.add_argument("--task-id", help="Include a read-only setup plan for a verified task worktree")
    parser.add_argument("--file", action="append", help="Inspect a publication snapshot of these explicit files")
    args = parser.parse_args(argv)
    try:
        if args.operation == "inspect":
            output = inspect_project(args.root, args.client)
            if args.task_id:
                task = {"task_id": args.task_id, "worktree": str(args.root)}
                if args.file is None:
                    output["setup_plan"] = plan_setup(task)
                else:
                    output["publication_snapshot"] = publication_snapshot(task, args.file)
        else:
            payload = sys.stdin.read(65537)
            if len(payload) > 65536:
                raise ValueError("Request exceeds 64 KiB")
            request = json.loads(payload, object_pairs_hook=unique_object)
            if args.operation == "start":
                output = start_task(args.root, request)
            elif args.operation == "apply":
                if not isinstance(request, dict) or set(request) != {"task_id", "plan"}:
                    raise ValueError("Provide task_id and the reviewed plan only")
                output = apply_setup(request["plan"], {"task_id": request["task_id"], "worktree": str(args.root)})
            elif args.operation == "sync":
                if not isinstance(request, dict) or set(request) != {"task_id", "event"}:
                    raise ValueError("Provide task_id and the lifecycle event")
                output = sync_event(request["event"], {"task_id": request["task_id"], "worktree": str(args.root)})
            else:
                if not isinstance(request, dict) or "operation_id" not in request or set(request) - {"operation_id", "confirmation", "usage"}:
                    raise ValueError("Provide operation_id, fresh lifecycle usage and optional attributed confirmation")
                output = resume_operation(args.root, request["operation_id"], request.get("confirmation"), usage=request.get("usage"))
    except (ValueError, OSError) as error:
        output = result(args.operation, "blocked", "not_started", next_action=
                        str(error) if isinstance(error, ValueError) else "Cannot inspect the selected files; verify paths and access")
    print(json.dumps(output, indent=2))
    return {"ok": 0, "action_required": 2, "blocked": 3}[output["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
