#!/usr/bin/env python3
"""Read-only inspection and verified task worktrees. Python 3.11+, macOS/Linux."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib
from urllib.parse import urlsplit
from uuid import UUID


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


def unique_object(pairs: list[tuple]) -> dict:
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError("Duplicate JSON field; provide one unambiguous value")
        data[key] = value
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("inspect", "start"))
    parser.add_argument("root", type=Path, help="Selected project/source checkout")
    parser.add_argument("--client", action="append", choices=("app", "vscode"), default=[])
    args = parser.parse_args(argv)
    try:
        if args.operation == "inspect":
            output = inspect_project(args.root, args.client)
        else:
            payload = sys.stdin.read(65537)
            if len(payload) > 65536:
                raise ValueError("Startup request exceeds 64 KiB")
            output = start_task(args.root, json.loads(payload, object_pairs_hook=unique_object))
    except (ValueError, OSError) as error:
        output = result(args.operation, "blocked", "not_started", next_action=
                        str(error) if isinstance(error, ValueError) else "Cannot inspect the selected files; verify paths and access")
    print(json.dumps(output, indent=2))
    return {"ok": 0, "action_required": 2, "blocked": 3}[output["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
