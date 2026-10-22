#!/usr/bin/env python3
"""Verified worktrees and recoverable project setup. Python 3.11+, macOS/Linux."""
import argparse
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
from urllib.parse import urlsplit
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


def load_policy(root: Path) -> bool:
    path = Path(root) / ".codex/vibe-workflow.toml"
    safe_file(path)
    if not path.exists():
        return True
    try:
        policy = tomllib.loads(path.read_text())
    except (UnicodeError, tomllib.TOMLDecodeError) as error:
        raise ValueError("Review malformed vibe-workflow.toml; no settings were changed") from error
    version = policy.get("schema_version", 1)
    lifecycle = policy.get("task_lifecycle", {})
    if type(version) is not int or version != 1:
        raise ValueError("Unsupported workflow policy schema_version")
    if not isinstance(lifecycle, dict) or set(lifecycle) - {"enabled"}:
        raise ValueError("Unknown or malformed task_lifecycle policy fields")
    enabled = lifecycle.get("enabled", True)
    if type(enabled) is not bool:
        raise ValueError("task_lifecycle.enabled must be true or false")
    return enabled


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


def resume_operation(root: Path, operation_id: str, confirmation: dict | None = None) -> dict:
    evidence = None
    try:
        if confirmation is not None:
            raise ValueError("Setup recovery accepts no confirmation overrides; reconcile changed files explicitly")
        operation_id = uuid_string(operation_id)
        root = canonical(root)
        common = Path(repository(root)["common_dir"])
        path = common / "vibe-setup/operations" / f"{operation_id}.json"
        evidence = str(path)
        record = read_operation(path)
        binding = record["plan"]["binding"]
        if binding.get("worktree") != str(root):
            raise ValueError("Resume from the operation's exact worktree root")
        response = run_setup(record["plan"], {"task_id": binding.get("task_id"), "worktree": str(root)}, resume=True)
        return {**response, "operation": "resume"}
    except (ValueError, OSError) as error:
        return setup_failure("resume", error, evidence)


def unique_object(pairs: list[tuple]) -> dict:
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError("Duplicate JSON field; provide one unambiguous value")
        data[key] = value
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("inspect", "start", "apply", "resume"))
    parser.add_argument("root", type=Path, help="Selected project/source checkout")
    parser.add_argument("--client", action="append", choices=("app", "vscode"), default=[])
    parser.add_argument("--task-id", help="Include a read-only setup plan for a verified task worktree")
    args = parser.parse_args(argv)
    try:
        if args.operation == "inspect":
            output = inspect_project(args.root, args.client)
            if args.task_id:
                output["setup_plan"] = plan_setup({"task_id": args.task_id, "worktree": str(args.root)})
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
            else:
                if not isinstance(request, dict) or set(request) != {"operation_id"}:
                    raise ValueError("Provide operation_id only")
                output = resume_operation(args.root, request["operation_id"])
    except (ValueError, OSError) as error:
        output = result(args.operation, "blocked", "not_started", next_action=
                        str(error) if isinstance(error, ValueError) else "Cannot inspect the selected files; verify paths and access")
    print(json.dumps(output, indent=2))
    return {"ok": 0, "action_required": 2, "blocked": 3}[output["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
