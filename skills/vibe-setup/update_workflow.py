"""Explicit, recoverable package updates; native clients supply their own evidence."""
from contextlib import ExitStack
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shlex
import tempfile


CLIENT_LAYERS = {"discovery", "execution", "protocol", "display", "exclusions"}
LAYERS = CLIENT_LAYERS | {"tests", "review", "installation", "activation", "publication", "remote_access", "cleanup", "release"}
STATES = {"pending", "passed", "blocked", "stale", "inapplicable"}
ASSETS = {".codex/hooks/subagents.py": ".codex/hooks/subagents.py",
          ".codex/hooks/native_display.py": ".codex/hooks/native_display.py",
          ".codex/delegation-brief.md": "delegation-brief.md", ".codex/native-display.md": "native-display.md"}
CONTEXT_FIELDS = {"runtime", "session", "hook_source", "settings_sha256"}
PLAN_FIELDS = {"schema_version", "root", "request", "package", "destinations", "outcomes"}


def exact(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError(f"Unsupported {label} fields")


def nonempty(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        raise ValueError(f"Invalid {label}")
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("Invalid SHA-256 fingerprint")
    return value


def relative(value):
    if (not isinstance(value, str) or not value or Path(value).is_absolute()
            or any(part in ("", ".", "..") for part in value.split("/")) or "\\" in value):
        raise ValueError("Unsafe owned relative path")
    return value


def fingerprint_map(value):
    if not isinstance(value, dict):
        raise ValueError("An explicit prior owned fingerprint map is required")
    for name, entry in value.items():
        relative(name)
        if entry is None:
            continue
        exact(entry, {"sha256", "mode"}, "fingerprint")
        sha(entry["sha256"])
        if type(entry["mode"]) is not int or not 0 <= entry["mode"] <= 0o777:
            raise ValueError("Unsafe owned file mode")


def path(value, workflow, *, directory=False):
    nonempty(value, "absolute path")
    result = workflow["canonical"](Path(value))
    if directory and not result.is_dir():
        raise ValueError("Select an existing directory")
    return result


def read_json(file, workflow):
    workflow["safe_file"](file)
    try:
        return json.loads(file.read_text(), object_pairs_hook=workflow["unique_object"],
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Invalid JSON constant")))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Review malformed private update JSON") from error


def file_reference(value, workflow):
    exact(value, {"path", "sha256"}, "evidence reference")
    sha(value["sha256"])
    file = path(value["path"], workflow)
    actual = workflow["fingerprint"](file)
    if actual is None or actual["sha256"] != value["sha256"]:
        raise ValueError("Evidence file changed or is unavailable")
    return file


def manifest(root, workflow):
    result = {}
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in {"__pycache__", ".pytest_cache"})
        for name in dirs:
            path(str(Path(current) / name), workflow, directory=True)
        for name in sorted(files):
            if name.endswith((".pyc", ".pyo")) or name == ".DS_Store":
                continue
            file = Path(current) / name
            relative_name = str(file.relative_to(root))
            result[relative_name] = workflow["fingerprint"](file)
    fingerprint_map(result)
    return result


def context(value, workflow):
    exact(value, CONTEXT_FIELDS, "client context")
    for key in ("runtime", "session"):
        nonempty(value[key], key)
    path(value["hook_source"], workflow)
    sha(value["settings_sha256"])


def validate_request(root, request, workflow, *, require_live=True):
    required = {"operation_id", "record_dir", "candidate_dir", "revision", "installed", "targets", "authorizations", "requirements"}
    if not isinstance(request, dict) or set(request) - (required | {"reuse_from"}) or not required <= set(request):
        raise ValueError("Unsupported update request fields")
    workflow["uuid_string"](request["operation_id"])
    record = path(request["record_dir"], workflow)
    if record.name != request["operation_id"]:
        raise ValueError("Private record directory must end with the operation UUID")
    candidate = path(request["candidate_dir"], workflow, directory=require_live)
    if not candidate.is_relative_to(root) or candidate == root:
        raise ValueError("Candidate must be a package directory in the selected source repository")
    if not isinstance(request["revision"], str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", request["revision"]):
        raise ValueError("Freeze an exact package commit revision")
    roots = [root]
    if request["installed"] is not None:
        installed = request["installed"]
        exact(installed, {"root", "baseline"}, "installed skill")
        roots.append(path(installed["root"], workflow, directory=require_live))
        fingerprint_map(installed["baseline"])
    if not isinstance(request["targets"], list):
        raise ValueError("Explicit target inventory is required")
    seen = set()
    for target in request["targets"]:
        exact(target, {"root", "kind", "baseline", "clients", "task", "activation_revision", "exclusions"}, "target")
        target_root = path(target["root"], workflow, directory=require_live)
        if request["installed"]:
            installed_root = Path(request["installed"]["root"])
            if installed_root.is_relative_to(target_root) or target_root.is_relative_to(installed_root):
                raise ValueError("Installed skill and selected target roots must not overlap")
        if target["root"] in seen or (request["installed"] and target["root"] == request["installed"]["root"]):
            raise ValueError("Duplicate target ownership")
        seen.add(target["root"])
        roots.append(target_root)
        if target["kind"] not in {"project", "umbrella", "source"}:
            raise ValueError("Unknown target kind")
        fingerprint_map(target["baseline"])
        if set(target["baseline"]) - set(workflow["SETUP_FILES"]):
            raise ValueError("Target baseline includes files outside component ownership")
        if not isinstance(target["clients"], dict) or set(target["clients"]) - {"app", "vscode"}:
            raise ValueError("Only explicit App and VS Code client contexts are supported")
        for client_context in target["clients"].values():
            context(client_context, workflow)
        if (not isinstance(target["exclusions"], list) or any(not isinstance(x, str) or not x.strip() for x in target["exclusions"])
                or len(set(target["exclusions"])) != len(target["exclusions"])):
            raise ValueError("List exact requested skill exclusions")
        revision = target["activation_revision"]
        if revision is not None and (not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision)):
            raise ValueError("Activation requires an exact reviewed commit revision")
        if target["task"] is not None:
            exact(target["task"], {"task_id", "worktree"}, "task binding")
    if any(record == r or record.is_relative_to(r) or r.is_relative_to(record) for r in roots):
        raise ValueError("Private update state must be outside source, installed skill and selected roots")
    if request["installed"] and (Path(request["installed"]["root"]).is_relative_to(root)
                                  or root.is_relative_to(Path(request["installed"]["root"]))):
        raise ValueError("Installed discovery directory must be separate from package source")
    if not isinstance(request["authorizations"], list):
        raise ValueError("Explicit authority records are required")
    allowed_roots = {str(r) for r in roots}
    for authorization in request["authorizations"]:
        exact(authorization, {"action", "roots", "provenance", "constraints"}, "authorization")
        if authorization["action"] not in {"install", "adopt", "publish", "release", "cleanup", "qualify"}:
            raise ValueError("Unknown authorization action; native trust cannot be granted here")
        if (not isinstance(authorization["roots"], list) or not authorization["roots"]
                or any(not isinstance(r, str) or r not in allowed_roots for r in authorization["roots"])):
            raise ValueError("Authorization exceeds selected update scope")
        nonempty(authorization["provenance"], "authorization provenance")
        if not isinstance(authorization["constraints"], list) or any(not isinstance(x, str) or not x.strip() for x in authorization["constraints"]):
            raise ValueError("Invalid authorization constraints")
    if not isinstance(request["requirements"], list):
        raise ValueError("List required update outcomes")
    for requirement in request["requirements"]:
        exact(requirement, {"root", "layer", "client"}, "required outcome")
        if requirement["root"] not in allowed_roots or requirement["layer"] not in LAYERS:
            raise ValueError("Unknown outcome or root")
        clients = next((t["clients"] for t in request["targets"] if t["root"] == requirement["root"]), {})
        if requirement["layer"] in CLIENT_LAYERS:
            if requirement["client"] not in clients:
                raise ValueError("Client outcome requires its selected target context")
        elif requirement["client"] is not None:
            raise ValueError("Non-client outcome must use client null")
    if "reuse_from" in request:
        previous = path(request["reuse_from"], workflow, directory=True)
        if previous == record:
            raise ValueError("Reuse must name a previous operation")
    return record, candidate


def committed_package(root, candidate, revision, workflow):
    facts = workflow["repository"](root)
    if facts["root"] != str(root) or facts["head"] != revision:
        raise ValueError("Package root or frozen revision changed")
    files = manifest(candidate, workflow)
    required = {"SKILL.md", "install.py", "workflow.py", *ASSETS.values(), ".codex/config.toml", ".codex/hooks.json", ".codex/vibe-workflow.toml"}
    if not required <= files.keys():
        raise ValueError("Candidate package is incomplete")
    prefix = str(candidate.relative_to(root)) + "/"
    tracked = workflow["git"](root, "ls-tree", "-rz", revision, "--", prefix).stdout.split("\0")
    objects = {}
    for entry in tracked:
        if entry:
            metadata, name = entry.split("\t", 1)
            mode, kind, object_id = metadata.split()
            if kind != "blob" or mode not in {"100644", "100755"}:
                raise ValueError("Candidate must contain regular committed files only")
            objects[name[len(prefix):]] = object_id
    if set(files) != set(objects):
        raise ValueError("Candidate includes uncommitted or missing package files")
    for name in files:
        observed = workflow["git"](root, "hash-object", "--no-filters", str(candidate / name)).stdout.strip()
        if observed != objects[name]:
            raise ValueError("Candidate differs from the frozen reviewed revision")
    return {"revision": revision, "manifest": files, "digest": digest(files)}


def verify_umbrella(root, workflow):
    for directory in (root, *root.parents):
        try:
            (directory / ".git").lstat()
        except FileNotFoundError:
            continue
        raise ValueError("A non-Git umbrella cannot contain or inherit Git metadata")
    result = workflow["git"](root, "rev-parse", "--git-dir", check=False)
    no_repository = "fatal: not a git repository (or any of the parent directories): .git"
    if result.returncode != 128 or (result.stderr or "").strip() != no_repository:
        raise ValueError("Cannot verify umbrella is outside every Git repository")


def project_plan(target, candidate, workflow):
    root = Path(target["root"])
    if target["kind"] == "umbrella":
        verify_umbrella(root, workflow)
    names = workflow["SETUP_FILES"]
    before = {name: workflow["fingerprint"](root / name) for name in names}
    after = copy.deepcopy(before)
    payloads = {}
    conflicts = []
    policy = workflow["policy_values"](root)
    if target["kind"] == "source":
        return {"kind": "source", "files": {}, "conflicts": [], "policy": policy, "binding": None, "head": None}, payloads
    with tempfile.TemporaryDirectory(prefix="vibe-update-preview-") as temporary:
        virtual = Path(temporary).resolve()
        workflow["git"](virtual, "init", "-q")
        for name, old in before.items():
            if old is not None:
                (virtual / name).parent.mkdir(parents=True, exist_ok=True)
                (virtual / name).write_bytes((root / name).read_bytes())
        for destination, source in ASSETS.items():
            proposed = (candidate / source).read_bytes()
            current = before[destination]
            proposed_fp = {"sha256": hashlib.sha256(proposed).hexdigest(), "mode": current["mode"] if current else 0o600}
            if current not in (target["baseline"].get(destination), proposed_fp):
                conflicts.append(destination)
                continue
            (virtual / destination).parent.mkdir(parents=True, exist_ok=True)
            (virtual / destination).write_bytes(proposed)
            after[destination] = proposed_fp
            payloads[destination] = proposed
        if not conflicts:
            # The real installer keeps its collision semantics; only this private preview substitutes reviewed assets.
            installer = runpy.run_path(str(candidate / "install.py"))
            hook_file = virtual / ".codex/hooks.json"
            if hook_file.exists() and before[".codex/hooks.json"] == target["baseline"].get(".codex/hooks.json"):
                hooks = json.loads(hook_file.read_text())
                candidate_hooks = json.loads((candidate / ".codex/hooks.json").read_text())
                if isinstance(hooks, dict) and isinstance(hooks.get("hooks"), dict):
                    for event, additions in candidate_hooks["hooks"].items():
                        groups = hooks["hooks"].get(event, [])
                        commands = {f'python3 "$(git rev-parse --show-toplevel)/.codex/hooks/subagents.py" {event}',
                                    "python3 " + shlex.quote(str(root / ".codex/hooks/subagents.py")) + " " + event}
                        owned = [index for index, group in enumerate(groups) if isinstance(group, dict)
                                 and isinstance(group.get("hooks"), list) and len(group["hooks"]) == 1
                                 and isinstance(group["hooks"][0], dict)
                                 and group["hooks"][0].get("type") == "command"
                                 and group["hooks"][0].get("command") in commands]
                        if len(owned) == 1 and len(additions) == 1:
                            groups[owned[0]] = copy.deepcopy(additions[0])
                    if hooks != json.loads(hook_file.read_text()):
                        hook_file.write_text(json.dumps(hooks, indent=2) + "\n")
            if target["kind"] == "umbrella":
                hook_file = virtual / ".codex/hooks.json"
                if hook_file.exists():
                    hooks = json.loads(hook_file.read_text())
                    candidate_hooks = json.loads((candidate / ".codex/hooks.json").read_text())
                    for event, groups in candidate_hooks["hooks"].items():
                        real = copy.deepcopy(groups)
                        for group in real:
                            group["hooks"][0]["command"] = "python3 " + shlex.quote(str(root / ".codex/hooks/subagents.py")) + " " + event
                        hooks["hooks"][event] = [groups[real.index(group)] if group in real else group
                                                 for group in hooks.get("hooks", {}).get(event, [])]
                    hook_file.write_text(json.dumps(hooks))
            try:
                writes = installer["plan_install"](virtual)
            except (ValueError, UnicodeError, json.JSONDecodeError):
                conflicts.extend([".codex/config.toml", ".codex/hooks.json"])
                writes = {}
            for name, data in writes.items():
                (virtual / name).parent.mkdir(parents=True, exist_ok=True)
                (virtual / name).write_bytes(data)
            if not (virtual / ".codex/vibe-workflow.toml").exists():
                (virtual / ".codex/vibe-workflow.toml").write_bytes((candidate / ".codex/vibe-workflow.toml").read_bytes())
            if target["kind"] == "umbrella":
                hook_file = virtual / ".codex/hooks.json"
                hooks = json.loads(hook_file.read_text())
                candidate_hooks = json.loads((candidate / ".codex/hooks.json").read_text())
                for event, groups in candidate_hooks["hooks"].items():
                    for group in hooks["hooks"].get(event, []):
                        if group in groups:
                            group["hooks"][0]["command"] = "python3 " + shlex.quote(str(root / ".codex/hooks/subagents.py")) + " " + event
                hook_file.write_text(json.dumps(hooks, indent=2) + "\n")
                original = root / ".codex/hooks.json"
                if original.exists() and hooks == json.loads(original.read_text()):
                    hook_file.write_bytes(original.read_bytes())
            for name in names:
                if not (virtual / name).exists():
                    continue
                data = (virtual / name).read_bytes()
                after[name] = {"sha256": hashlib.sha256(data).hexdigest(), "mode": before[name]["mode"] if before[name] else 0o600}
                payloads[name] = data
    files = {name: {"before": before[name], "after": after[name]} for name in names}
    binding = None
    head = None
    if target["kind"] == "project":
        facts = workflow["repository"](root)
        if facts["root"] != str(root):
            raise ValueError("Select the exact owning repository root")
        head = facts["head"]
        if target["task"] is not None:
            binding, _ = workflow["setup_context"](target["task"])
            if binding["worktree"] != str(root):
                raise ValueError("Target differs from verified worktree binding")
        if policy["enabled"] and not conflicts and binding is None and any(v["before"] != v["after"] for v in files.values()):
            if target["activation_revision"] == head:
                tracked = set(workflow["git"](root, "ls-files", "--", *names).stdout.splitlines())
                for name in tracked:
                    if files[name]["before"] != files[name]["after"]:
                        raise ValueError("Primary activation cannot modify tracked files; publish the reviewed revision first")
                    committed = workflow["git"](root, "show", f"{head}:{name}").stdout.encode()
                    if hashlib.sha256(committed).hexdigest() != before[name]["sha256"]:
                        raise ValueError("Primary tracked setup differs from the reviewed revision")
            else:
                raise ValueError("Lifecycle edits require a verified task worktree or exact reviewed activation revision")
    elif target["task"] is not None or target["activation_revision"] is not None:
        raise ValueError("Umbrella roots do not have Git task bindings or revisions")
    return {"kind": target["kind"], "files": files, "conflicts": conflicts, "policy": policy,
            "binding": binding, "head": head}, payloads


def build_plan(root, request, candidate, workflow):
    package = committed_package(root, candidate, request["revision"], workflow)
    destinations, payloads = {}, {}
    installed = request["installed"]
    if installed:
        files, conflicts, data = {}, [], {}
        installed_root = Path(installed["root"])
        for name in sorted(set(package["manifest"]) | set(installed["baseline"])):
            before = workflow["fingerprint"](installed_root / name)
            after = package["manifest"].get(name)
            if before not in (installed["baseline"].get(name), after):
                conflicts.append(name)
            files[name] = {"before": before, "after": after}
            if after is not None:
                data[name] = (candidate / name).read_bytes()
        destinations[installed["root"]] = {"kind": "installed", "files": files, "conflicts": conflicts,
                                            "policy": None, "binding": None, "head": None}
        payloads[installed["root"]] = data
    for target in request["targets"]:
        destinations[target["root"]], payloads[target["root"]] = project_plan(target, candidate, workflow)
    required = copy.deepcopy(request["requirements"])
    for destination, entry in destinations.items():
        if entry["kind"] != "source":
            required.append({"root": destination, "layer": "installation", "client": None})
            if entry["kind"] != "installed":
                required.append({"root": destination, "layer": "activation", "client": None})
    for target in request["targets"]:
        if target["exclusions"]:
            required.extend({"root": target["root"], "layer": "exclusions", "client": client} for client in target["clients"])
    required.extend({"root": item["root"], "layer": "remote_access", "client": None}
                    for item in list(required) if item["layer"] == "publication")
    outcomes = []
    seen = set()
    for requirement in required:
        identity = (requirement["root"], requirement["layer"], requirement["client"])
        if identity in seen:
            continue
        seen.add(identity)
        target = next((t for t in request["targets"] if t["root"] == requirement["root"]), None)
        files = {name: value["after"] for name, value in destinations.get(requirement["root"], {}).get("files", {}).items()}
        if requirement["layer"] in CLIENT_LAYERS:
            inputs = {"files": {name: value for name, value in files.items() if name.startswith(".codex/")},
                      "instructions": {name: value for name, value in package["manifest"].items()
                                       if name in {"SKILL.md", "delegation-brief.md", "task-lifecycle.md",
                                                   "security-validation.md", "native_qualification.py"}},
                      "context": target["clients"][requirement["client"]], "exclusions": target["exclusions"]}
        else:
            inputs = {"package": package["digest"], "files": files}
        outcomes.append({**requirement, "fingerprint": digest({**requirement, "inputs": inputs})})
    return {"schema_version": 1, "root": str(root), "request": copy.deepcopy(request), "package": package,
            "destinations": destinations, "outcomes": outcomes}, payloads


def load_plan(record, root, workflow, *, require_live=True):
    plan = read_json(record / "plan.json", workflow)
    exact(plan, PLAN_FIELDS, "update plan")
    if type(plan["schema_version"]) is not int or plan["schema_version"] != 1 or plan["root"] != str(root):
        raise ValueError("Update plan version or source root mismatch")
    validate_request(root, plan["request"], workflow, require_live=require_live)
    if plan["request"]["record_dir"] != str(record):
        raise ValueError("Update plan location changed")
    exact(plan["package"], {"revision", "manifest", "digest"}, "package manifest")
    fingerprint_map(plan["package"]["manifest"])
    if digest(plan["package"]["manifest"]) != plan["package"]["digest"]:
        raise ValueError("Package manifest changed")
    expected_roots = {t["root"] for t in plan["request"]["targets"]}
    if plan["request"]["installed"]:
        expected_roots.add(plan["request"]["installed"]["root"])
    if not isinstance(plan["destinations"], dict) or set(plan["destinations"]) != expected_roots:
        raise ValueError("Update destination scope changed")
    for root_name, entry in plan["destinations"].items():
        exact(entry, {"kind", "files", "conflicts", "policy", "binding", "head"}, "destination plan")
        if not isinstance(entry["files"], dict) or not isinstance(entry["conflicts"], list):
            raise ValueError("Malformed destination plan")
        allowed = set(plan["package"]["manifest"]) | set(plan["request"]["installed"]["baseline"]) if entry["kind"] == "installed" else set(workflow["SETUP_FILES"])
        if set(entry["files"]) - allowed or set(entry["conflicts"]) - set(entry["files"]):
            raise ValueError("Destination plan exceeds owned paths")
        for name, values in entry["files"].items():
            exact(values, {"before", "after"}, "owned change")
            fingerprint_map({name: values["before"]})
            fingerprint_map({name: values["after"]})
    if not isinstance(plan["outcomes"], list):
        raise ValueError("Malformed completion requirements")
    for row in plan["outcomes"]:
        exact(row, {"root", "layer", "client", "fingerprint"}, "completion outcome")
        sha(row["fingerprint"])
        if row["layer"] not in LAYERS or row["root"] not in expected_roots | {str(root)}:
            raise ValueError("Completion outcome exceeds scope")
    state = read_json(record / "state.json", workflow)
    exact(state, {"schema_version", "plan_sha256", "transaction", "started", "done", "evidence"}, "update state")
    if (type(state["schema_version"]) is not int or state["schema_version"] != 1 or state["plan_sha256"] != digest(plan)
            or state["transaction"] not in {"planned", "applying", "applied", "rolling_back", "rolled_back"}
            or not isinstance(state["done"], list) or not isinstance(state["started"], list) or not isinstance(state["evidence"], dict)):
        raise ValueError("Update recovery state changed")
    changed = {file_id(r, name) for r, entry in plan["destinations"].items() for name, value in entry["files"].items()
               if value["before"] != value["after"]}
    if (any(not isinstance(item, str) or item not in changed for item in state["started"] + state["done"])
            or len(set(state["done"])) != len(state["done"]) or len(set(state["started"])) != len(state["started"])
            or not set(state["done"]) <= set(state["started"])):
        raise ValueError("Unknown update recovery write")
    if set(state["evidence"]) - {row_id(row) for row in plan["outcomes"]}:
        raise ValueError("Unknown evidence requirement")
    return plan, state


def row_id(row):
    return digest({key: row[key] for key in ("root", "layer", "client")})


def file_id(root, name):
    return digest([root, name])


def evidence_state(row, reference, plan, workflow):
    evidence = read_json(file_reference(reference, workflow), workflow)
    fields = {"schema_version", "root", "layer", "client", "fingerprint", "state", "reason", "next_action", "source", "outcome", "references"}
    exact(evidence, fields, "outcome evidence")
    if type(evidence["schema_version"]) is not int or evidence["schema_version"] != 1:
        raise ValueError("Unsupported evidence version")
    if any(evidence[key] != row[key] for key in ("root", "layer", "client", "fingerprint")):
        raise ValueError("Evidence does not match the frozen root, client or source fingerprint")
    if evidence["state"] not in STATES:
        raise ValueError("Unknown evidence state")
    nonempty(evidence["reason"], "evidence reason")
    nonempty(evidence["next_action"], "evidence next action")
    nonempty(evidence["outcome"], "observed outcome")
    if row["client"]:
        target = next(t for t in plan["request"]["targets"] if t["root"] == row["root"])
        if evidence["source"] != {"client": row["client"], **target["clients"][row["client"]]}:
            raise ValueError("Evidence belongs to another client, session, runtime, source or settings")
    elif evidence["source"] is not None:
        raise ValueError("Non-client evidence cannot substitute a client execution surface")
    if not isinstance(evidence["references"], list):
        raise ValueError("Evidence references must be immutable file hashes")
    for ref in evidence["references"]:
        file_reference(ref, workflow)
    state = evidence["state"]
    if state == "passed" and row["layer"] in {"execution", "protocol", "display"}:
        if evidence["outcome"] != "native_probe" or len(evidence["references"]) != 1:
            raise ValueError("Native client outcomes require one evaluated native probe receipt")
        probe_path = file_reference(evidence["references"][0], workflow)
        probe = read_json(probe_path, workflow)
        if not isinstance(probe, dict):
            raise ValueError("Malformed native probe receipt")
        native = runpy.run_path(str(Path(__file__).resolve().parent / "native_qualification.py"))
        try:
            result = native["handle"]("status-probe", Path(row["root"]), {"record_path": str(probe_path)}, workflow)
        except (KeyError, TypeError, IndexError, AttributeError, RecursionError) as error:
            raise ValueError("Malformed native qualification evidence; preserve and inspect the receipt") from error
        file_reference(evidence["references"][0], workflow)
        if result.get("status") != "ok":
            raise ValueError("Native qualification could not revalidate its captured evidence")
        observation = probe.get("context", {})
        if not isinstance(observation, dict):
            raise ValueError("Malformed native probe context")
        expected = evidence["source"]
        sources = observation.get("hook_sources", [])
        if (not isinstance(sources, list) or len(sources) != 1 or not isinstance(sources[0], dict)
                or probe.get("schema_version") != 1 or probe.get("root") != row["root"]
                or probe.get("client") != row["client"] or probe.get("parent_thread_id") != expected["session"]
                or probe.get("attempts") != 1 or not isinstance(result, dict)
                or result.get("native_calls") != 1 or result.get("attempts") != 1
                or result.get("settings_preserved") is not True or not result.get("child_thread_id")
                or observation.get("client") != row["client"] or observation.get("runtime") != expected["runtime"]
                or observation.get("thread_id") != expected["session"] or observation.get("harness_root") != row["root"]
                or observation.get("observed_via") not in {"native-ui", "native-app-tool"}
                or sources[0].get("path") != expected["hook_source"]
                or digest(probe.get("settings")) != expected["settings_sha256"]
                or result.get({"execution": "execution_passed", "protocol": "protocol_passed", "display": "display_passed"}[row["layer"]]) is not True):
            raise ValueError("Native probe does not prove this client outcome with preserved settings")
        if row["layer"] == "protocol" and (result.get("first_report_valid") is not True or result.get("recovery_observed") is not False):
            raise ValueError("A corrected report cannot prove first-pass protocol")
    if state == "passed":
        required_outcome = {"cleanup": "archived", "exclusions": "effective", "remote_access": "accessible"}.get(row["layer"])
        if required_outcome and evidence["outcome"] != required_outcome:
            state = "blocked" if evidence["outcome"] in {"inaccessible", "compatibility_gap"} else "pending"
    return {"state": state, "reason": evidence["reason"], "next_action": evidence["next_action"], "evidence": reference}


def status(plan, state, record, workflow, changes=None, contexts=None):
    outcomes = []
    roots = {root: "present" if Path(root).is_dir() else "unavailable"
             for root in sorted({plan["root"], *plan["destinations"]})}
    for row in plan["outcomes"]:
        entry = plan["destinations"].get(row["root"])
        details = {"state": "pending", "reason": "Required evidence has not been recorded", "next_action": "Record this outcome in the selected surface"}
        if row["layer"] in {"installation", "activation"} and entry:
            verified = not entry["conflicts"] and all(workflow["fingerprint"](Path(row["root"]) / name) == item["after"] for name, item in entry["files"].items())
            details = {"state": "passed" if verified and state["transaction"] != "rolled_back" else "pending",
                       "reason": "Owned destination hashes verified" if verified else "Owned destinations need update or reconciliation",
                       "next_action": "No action required" if verified else "Apply or resume the reviewed update"}
        reference = state["evidence"].get(row_id(row))
        if reference:
            try:
                details = evidence_state(row, reference, plan, workflow)
            except (ValueError, OSError):
                details = {"state": "stale", "reason": "Evidence changed, is unavailable or no longer matches", "next_action": "Reconcile the original evidence; do not silently rerun native work"}
        if details["state"] in {"passed", "inapplicable"} and row["client"] and entry:
            if any(workflow["fingerprint"](Path(row["root"]) / name) != item["after"] for name, item in entry["files"].items() if name.startswith(".codex/")):
                details = {"state": "stale", "reason": "Client-owned inputs changed", "next_action": "Review changed inputs and requalify affected client outcomes"}
            if contexts is not None:
                supplied = contexts.get(row["root"], {}).get(row["client"])
                original = next(t for t in plan["request"]["targets"] if t["root"] == row["root"])["clients"][row["client"]]
                if supplied is not None and supplied != original:
                    details = {"state": "stale", "reason": "Current client context changed", "next_action": "Plan qualification for the current client context"}
        if roots[row["root"]] == "unavailable" and row["layer"] in CLIENT_LAYERS | {"installation", "activation"}:
            details = {"state": "stale", "reason": "Selected root is unavailable; retained activity is historical, not a current deployment",
                       "next_action": "Preserve the record and reconcile the missing target; do not recreate it through this update",
                       "historical_transaction": state["transaction"]}
            if reference:
                details["historical_evidence"] = reference
        outcomes.append({**row, **details})
    for row in outcomes:
        if row["layer"] == "cleanup" and row["state"] == "passed" and roots[row["root"]] == "unavailable":
            roots[row["root"]] = "archived"
    for target in plan["request"]["targets"]:
        root = target["root"]
        entry = plan["destinations"][root]
        binding, task = entry["binding"], target["task"]
        changed = {file_id(root, name) for name, item in entry["files"].items() if item["before"] != item["after"]}
        if (roots[root] != "archived" or entry["kind"] != "project" or entry["conflicts"]
                or state["transaction"] != "applied" or not changed <= set(state["done"])
                or not isinstance(binding, dict) or not isinstance(task, dict)
                or binding.get("state") != "verified" or binding.get("worktree") != root
                or task.get("worktree") != root or binding.get("task_id") != task.get("task_id")
                or not binding.get("source") or binding["source"] == root
                or not any(a["action"] == "cleanup" and root in a["roots"] for a in plan["request"]["authorizations"])):
            continue
        for row in outcomes:
            if row["root"] == root and row["layer"] in {"installation", "activation"}:
                row.update(state="passed", basis="historical", deployment="inactive",
                           reason="Owned update completed in the verified task worktree before observed archival; no live deployment remains",
                           next_action="Retain the completed task and archive evidence")
    conflicts = [{"root": r, "files": entry["conflicts"]} for r, entry in plan["destinations"].items() if entry["conflicts"]]
    complete = (bool(outcomes) and not conflicts and "unavailable" not in roots.values()
                and state["transaction"] != "rolled_back" and all(row["state"] in {"passed", "inapplicable"} for row in outcomes))
    return {"schema_version": 1, "operation_id": plan["request"]["operation_id"], "record_dir": str(record),
            "transaction": state["transaction"], "complete": complete, "status": "ok" if complete else "action_required",
            "outcomes": outcomes, "conflicts": conflicts, "changes": changes or [], "roots": roots,
            "authorizations": plan["request"]["authorizations"],
            "next_action": ("Update requirements are complete" if complete else
                            "Reconcile unavailable roots; disappearance does not prove archival" if "unavailable" in roots.values() else
                            "Resolve the listed pending, stale or blocked outcomes")}


def write_state(record, state, workflow, previous=None):
    if state != previous:
        workflow["write_record"](record / "state.json", state)


def save_payload(file, payload, workflow, mode=0o600):
    after = {"sha256": hashlib.sha256(payload).hexdigest(), "mode": mode}
    existing = workflow["fingerprint"](file)
    if existing is not None:
        if existing != after:
            raise ValueError("Private stage or original backup changed; preserve and inspect it")
        return
    workflow["replace_setup_file"](file, payload, None, after, "update-stage")


def target_gate(root, entry, plan, workflow):
    if entry["kind"] in {"installed", "source"}:
        return
    if entry["kind"] == "umbrella":
        verify_umbrella(Path(root), workflow)
    if workflow["policy_values"](Path(root)) != entry["policy"]:
        raise ValueError("Lifecycle policy changed after planning")
    if entry["kind"] == "project":
        if workflow["repository"](Path(root))["head"] != entry["head"]:
            raise ValueError("Target revision changed after planning")
        if entry["binding"]:
            target = next(t for t in plan["request"]["targets"] if t["root"] == root)
            binding, _ = workflow["setup_context"](target["task"])
            if binding != entry["binding"]:
                raise ValueError("Verified worktree binding changed")


def apply(plan, state, record, workflow, rollback=False):
    if state["transaction"] == "rolled_back" and not rollback:
        raise ValueError("Rolled-back operations require a new reviewed update identity")
    if state["transaction"] == "rolling_back" and not rollback:
        raise ValueError("Finish rollback before another apply")
    before_state = copy.deepcopy(state)
    current_status = status(plan, state, record, workflow)
    access = {r["root"]: r for r in current_status["outcomes"] if r["layer"] == "remote_access"}
    checks = {r["root"] for r in current_status["outcomes"] if r["layer"] in {"tests", "review"}
              and r["state"] not in {"passed", "inapplicable"}}
    eligible = []
    blocked = []
    for root, entry in plan["destinations"].items():
        if entry["kind"] == "source":
            continue
        action = "install" if entry["kind"] == "installed" else "adopt"
        authorized = any(a["action"] == action and root in a["roots"] for a in plan["request"]["authorizations"])
        if not rollback and (entry["conflicts"] or not authorized or (root in access and access[root]["state"] != "passed")
                             or root in checks or plan["root"] in checks):
            blocked.append({"root": root, "reason": "Review preservation conflicts or missing authorization/access/check evidence"})
            continue
        target_gate(root, entry, plan, workflow)
        for name, item in entry["files"].items():
            current = workflow["fingerprint"](Path(root) / name)
            if current not in (item["before"], item["after"]):
                raise ValueError("Owned destination changed; preserve the later edit before apply or rollback")
            if not rollback and file_id(root, name) in state["done"] and current != item["after"]:
                raise ValueError("An applied file changed; preserve the edit before resuming")
            if (not rollback and item["before"] != item["after"] and current == item["after"]
                    and file_id(root, name) not in state["started"]):
                raise ValueError("Destination changed outside this operation; preserve its ownership")
        eligible.append((root, entry))
    if not rollback and manifest(record / "stage", workflow) != plan["package"]["manifest"]:
        raise ValueError("Staged package changed")
    changed = []
    if rollback:
        eligible.reverse()
    for root, entry in eligible:
        names = list(entry["files"])
        if rollback:
            names.reverse()
        for name in names:
            item = entry["files"][name]
            if item["before"] == item["after"]:
                continue
            destination = Path(root) / name
            identity = file_id(root, name)
            if rollback and identity not in state["started"]:
                continue
            backup = record / "backup" / identity
            current = workflow["fingerprint"](destination)
            expected, desired = (item["after"], item["before"]) if rollback else (item["before"], item["after"])
            if rollback and current == desired:
                continue
            if not rollback and item["before"] is not None:
                if backup.exists():
                    saved = workflow["fingerprint"](backup)
                    if saved != {**item["before"], "mode": 0o600}:
                        raise ValueError("Original rollback backup changed")
                elif current == item["before"]:
                    save_payload(backup, destination.read_bytes(), workflow)
                else:
                    raise ValueError("Applied file has no original backup; preserve and reconcile")
            if current != desired:
                if rollback:
                    if desired is not None:
                        saved = workflow["fingerprint"](backup)
                        if saved != {**desired, "mode": 0o600}:
                            raise ValueError("Original rollback backup is missing or changed")
                        payload = backup.read_bytes()
                elif desired is not None:
                    staged = record / "payloads" / identity
                    if workflow["fingerprint"](staged) != {**desired, "mode": 0o600}:
                        raise ValueError("Reviewed destination payload changed")
                    payload = staged.read_bytes()
                target_gate(root, entry, plan, workflow)
                state["transaction"] = "rolling_back" if rollback else "applying"
                if not rollback and identity not in state["started"]:
                    state["started"].append(identity)
                write_state(record, state, workflow, before_state)
                before_state = copy.deepcopy(state)
                if desired is None:
                    if workflow["fingerprint"](destination) != expected:
                        raise ValueError("Destination changed before owned removal")
                    destination.unlink()
                    workflow["sync_directory"](destination.parent)
                else:
                    workflow["replace_setup_file"](destination, payload, expected, desired, plan["request"]["operation_id"])
                changed.append(str(destination))
            if not rollback and identity not in state["done"]:
                state["done"].append(identity)
                write_state(record, state, workflow, before_state)
                before_state = copy.deepcopy(state)
    state["transaction"] = "rolled_back" if rollback else ("applied" if not blocked else state["transaction"])
    write_state(record, state, workflow, before_state)
    result = status(plan, state, record, workflow, changed)
    if blocked:
        result["blocked_destinations"] = blocked
    return result


def handle(operation: str, root: Path, request: dict, workflow: dict) -> dict:
    """JSON boundary used by workflow.py; all active native work stays outside Python."""
    retained = operation in {"record-update", "status-update"}
    root = path(str(root), workflow, directory=not retained)
    if operation == "plan-update":
        record, candidate = validate_request(root, request, workflow)
        if (record / "plan.json").exists():
            plan, state = load_plan(record, root, workflow)
            if plan["request"] != request:
                raise ValueError("Operation identity already owns a different update scope")
            return status(plan, state, record, workflow)
        plan, payloads = build_plan(root, request, candidate, workflow)
        workflow["setup_directory"](record)
        lock_file = record / "update.lock"
        workflow["safe_file"](lock_file)
        with lock_file.open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if (record / "plan.json").exists():
                raise ValueError("Update was planned concurrently; resume the existing operation")
            for name, fingerprint in plan["package"]["manifest"].items():
                save_payload(record / "stage" / name, (candidate / name).read_bytes(), workflow, fingerprint["mode"])
            if manifest(record / "stage", workflow) != plan["package"]["manifest"]:
                raise ValueError("Candidate changed while staging")
            for destination, files in payloads.items():
                for name, data in files.items():
                    save_payload(record / "payloads" / file_id(destination, name), data, workflow)
            state = {"schema_version": 1, "plan_sha256": digest(plan), "transaction": "planned", "started": [], "done": [], "evidence": {}}
            if request.get("reuse_from"):
                old_plan, old_state = load_plan(Path(request["reuse_from"]), root, workflow, require_live=False)
                for row in plan["outcomes"]:
                    reference = old_state["evidence"].get(row_id(row))
                    if reference:
                        try:
                            evidence_state(row, reference, plan, workflow)
                        except (ValueError, OSError):
                            continue
                        state["evidence"][row_id(row)] = reference
            workflow["write_record"](record / "state.json", state)
            workflow["write_record"](record / "plan.json", plan)
        return status(plan, state, record, workflow)
    allowed = {"record_dir", "evidence"} if operation == "record-update" else {"record_dir", "contexts"} if operation == "status-update" else {"record_dir"}
    if not isinstance(request, dict) or "record_dir" not in request or set(request) - allowed:
        raise ValueError("Unsupported update operation request fields")
    if operation not in {"apply-update", "resume-update", "rollback-update", "record-update", "status-update"}:
        raise ValueError("Unsupported update operation")
    record = path(request["record_dir"], workflow, directory=True)
    plan, state = load_plan(record, root, workflow, require_live=not retained)
    if operation == "status-update":
        contexts = request.get("contexts")
        if contexts is not None:
            if not isinstance(contexts, dict):
                raise ValueError("Current client contexts must map selected roots")
            targets = {t["root"]: t for t in plan["request"]["targets"]}
            for target_root, clients in contexts.items():
                if target_root not in targets or not isinstance(clients, dict) or set(clients) - set(targets[target_root]["clients"]):
                    raise ValueError("Current client context exceeds selected scope")
                for value in clients.values():
                    context(value, workflow)
        return status(plan, state, record, workflow, contexts=contexts)
    with ExitStack() as stack:
        lock_file = record / "update.lock"
        workflow["safe_file"](lock_file)
        lock = stack.enter_context(lock_file.open("r"))
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if not retained:
            for destination in sorted({str(root), *plan["destinations"]}):
                descriptor = os.open(destination, os.O_RDONLY)
                stack.callback(os.close, descriptor)
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan, state = load_plan(record, root, workflow, require_live=not retained)
        if operation == "record-update":
            exact(request, {"record_dir", "evidence"}, "record outcome request")
            evidence = read_json(file_reference(request["evidence"], workflow), workflow)
            row = next((row for row in plan["outcomes"] if all(evidence.get(key) == row[key] for key in ("root", "layer", "client"))), None)
            if row is None or row["layer"] in {"installation", "activation"}:
                raise ValueError("Unknown or automatically verified evidence outcome")
            evidence_state(row, request["evidence"], plan, workflow)
            previous = copy.deepcopy(state)
            state["evidence"][row_id(row)] = request["evidence"]
            write_state(record, state, workflow, previous)
            return status(plan, state, record, workflow)
        return apply(plan, state, record, workflow, rollback=operation == "rollback-update")
