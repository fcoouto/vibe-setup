#!/usr/bin/env python3
"""Install this reviewed project-local recipe without changing global trust/config."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tomllib

SOURCE = Path(__file__).resolve().parent


def plan_install(target: Path, non_git: bool = False) -> dict[str, bytes]:
    """Return the existing recipe changes without creating directories or writing files."""
    root = Path(target).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Target must be an existing project directory")
    if not non_git:
        result = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                                capture_output=True, text=True, timeout=5)
        if result.returncode or Path(result.stdout.strip()).resolve() != root:
            raise ValueError("Select the Git root, or explicitly use --non-git-workspace")

    def read(relative):
        path = root / relative
        for part in (path, *path.parents):
            if part == root:
                break
            if part.is_symlink():
                raise ValueError("Refusing a symlink at an installer-owned destination")
        if path.exists() and not path.is_file():
            raise ValueError("Expected a regular file at an installer-owned destination")
        return path.read_bytes() if path.exists() else None

    writes = {}
    for destination, source in ((".codex/hooks/subagents.py", ".codex/hooks/subagents.py"),
                                (".codex/delegation-brief.md", "delegation-brief.md")):
        payload = (SOURCE / source).read_bytes()
        current = read(destination)
        if current is not None and current != payload:
            raise ValueError(f"Preserve and review customized {destination} before replacing it")
        if current is None:
            writes[destination] = payload

    config_bytes = read(".codex/config.toml")
    if config_bytes is None:
        writes[".codex/config.toml"] = (SOURCE / ".codex/config.toml").read_bytes()
    else:
        config = tomllib.loads(config_bytes.decode())
        if "hooks" in config:
            raise ValueError("Reconcile existing inline hooks before adding a hooks.json source")
        agents = config.get("agents", {})
        if not isinstance(agents, dict) or agents.get("enabled", True) is not True:
            raise ValueError("Existing agent settings disable this recipe; review them explicitly")
        if "agents" not in config:
            writes[".codex/config.toml"] = config_bytes.rstrip() + (
                b"\n\n[agents]\nenabled = true\nmax_concurrent_threads_per_session = 3\n")
        else:
            limit = agents.get("max_concurrent_threads_per_session")
            if type(limit) is not int or limit < 1:
                raise ValueError("Set max_concurrent_threads_per_session to an integer >= 1")

    current_hooks = read(".codex/hooks.json")
    hooks = json.loads(current_hooks) if current_hooks is not None else {}
    if not isinstance(hooks, dict) or not isinstance(hooks.get("hooks", {}), dict):
        raise ValueError("Existing hooks.json has an incompatible shape")
    groups = hooks.setdefault("hooks", {})
    candidate = json.loads((SOURCE / ".codex/hooks.json").read_text())["hooks"]
    for event, additions in candidate.items():
        existing = groups.setdefault(event, [])
        if not isinstance(existing, list):
            raise ValueError("Existing hook event must be an array")
        for group in additions:
            if non_git:
                command = "python3 " + shlex.quote(str(root / ".codex/hooks/subagents.py"))
                group["hooks"][0]["command"] = command + " " + event
            if group in existing:
                continue
            for old in existing:
                if not isinstance(old, dict) or not isinstance(old.get("hooks"), list):
                    raise ValueError("Existing hook group has an incompatible shape")
                if any(isinstance(h, dict) and "subagents.py" in str(h.get("command", ""))
                       for h in old["hooks"]):
                    raise ValueError("Review an existing subagent hook instead of duplicating it")
            existing.append(group)
    payload = (json.dumps(hooks, indent=2) + "\n").encode()
    if hooks != (json.loads(current_hooks) if current_hooks is not None else {}):
        writes[".codex/hooks.json"] = payload

    for relative in (".gitignore", ".graphifyignore"):
        current = read(relative) or b""
        rule = b".codex-delegations/"
        payload = b"".join(line for line in current.splitlines(keepends=True)
                           if line.rstrip(b"\r\n") != rule)
        if payload and not payload.endswith(b"\n"):
            payload += b"\n"
        payload += rule + b"\n"
        if payload != current:
            writes[relative] = payload

    return writes


def install(target, check=False, non_git=False):
    # Validate all destinations before changing any file; collisions preserve the project.
    writes = plan_install(target, non_git=non_git)
    root = Path(target).resolve(strict=True)
    if not check:
        for relative, payload in writes.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
    return sorted(writes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="Existing Git root (not a nested app directory)")
    parser.add_argument("--check", action="store_true", help="Report missing changes without writing")
    parser.add_argument("--non-git-workspace", action="store_true",
                        help="Render machine-local absolute commands for an umbrella directory")
    args = parser.parse_args()
    try:
        changes = install(args.target, args.check, args.non_git_workspace)
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        print(f"Setup stopped: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"pending" if args.check else "changed": changes,
                      "trust": "Review exact project/hook definitions in the client; not changed here"}))
    return 1 if args.check and changes else 0


if __name__ == "__main__":
    raise SystemExit(main())
