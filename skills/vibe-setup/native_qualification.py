"""Prepare one native probe and reconcile its real, read-only client evidence.

The caller observes native UI/discovery and invokes the returned tool packet.
This module never launches a model, edits trust, or calls a hook.
"""
import fcntl
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import runpy
import shlex
import time
from uuid import uuid4

PACKAGE = Path(__file__).resolve().parent
SETTINGS = ("model", "effort", "approval_policy", "sandbox_policy", "permission_profile", "active_permission_profile")
SPAWNS = {"spawn_agent", "collaboration.spawn_agent", "multi_agent_v1spawn_agent", "multi_agent_v2spawn_agent"}
MAX_LOG = 256 * 1024 * 1024


def strict_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate JSON field")
        value[key] = item
    return value


def reject_number(_):
    raise ValueError("Non-JSON number")


def loads(raw):
    return json.loads(raw, object_pairs_hook=strict_object, parse_constant=reject_number)


def fields(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) or set(value) - set(required) - set(optional):
        raise ValueError("Unsupported qualification fields")


def nonblank(value):
    return isinstance(value, str) and 0 < len(value.strip()) <= 4096


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_file(path, wf, limit=1024 * 1024):
    path = Path(path)
    wf["safe_file"](path)
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Qualification evidence exceeds the supported size")
    return raw


def artifact(path, wf):
    raw = read_file(path, wf)
    return loads(raw), {"path": str(path), "sha256": digest(raw)}


def log_rows(path, wf):
    raw = read_file(path, wf, MAX_LOG)
    if raw and not raw.endswith(b"\n"):
        # A live partial line is not a complete native event.
        raw = raw[:raw.rfind(b"\n") + 1]
    return raw, [loads(line) for line in raw.splitlines() if line.strip()]


def native_context(rows):
    metas = [row["payload"] for row in rows if row.get("type") == "session_meta"]
    turns = [row["payload"] for row in rows if row.get("type") == "turn_context"]
    if not metas or not turns:
        raise ValueError("Native session metadata and current turn settings are required")
    meta, turn = metas[0], turns[-1]
    if not all(nonblank(value) for value in (meta.get("id"), meta.get("cwd"), turn.get("turn_id"), turn.get("model"))):
        raise ValueError("Native identity or model is unavailable")
    if meta["cwd"] != turn.get("cwd"):
        raise ValueError("Native session and current turn roots differ")
    settings = {key: turn.get(key) for key in SETTINGS}
    settings["provider"] = meta.get("model_provider")
    if (any(not nonblank(settings[key]) for key in ("model", "effort", "approval_policy", "provider"))
            or not isinstance(settings["sandbox_policy"], dict) or not settings["sandbox_policy"].get("type")):
        raise ValueError("Native reasoning, provider and permission settings must be observed, not inferred")
    return meta, turn, settings


def settings_match(rows, expected):
    return all({**{key: row["payload"].get(key) for key in SETTINGS},
                "provider": expected["provider"]} == expected
               for row in rows if row.get("type") == "turn_context")


def validate_observation(observation, root, meta, wf):
    fields(observation, ("client", "thread_id", "runtime", "harness_root", "observed_via", "hook_sources"))
    if (observation["client"] not in ("app", "vscode") or observation["thread_id"] != meta["id"]
            or observation["harness_root"] != str(root) or meta["cwd"] != str(root)
            or not nonblank(observation["runtime"])
            or observation["observed_via"] not in ("native-ui", "native-app-tool")):
        raise ValueError("Client observation does not bind this native thread and harness root")
    if meta.get("originator") != {"app": "codex_work_desktop", "vscode": "codex_vscode"}[observation["client"]]:
        raise ValueError("Native originator does not identify the observed client; CLI evidence cannot substitute")
    sources = observation["hook_sources"]
    if not isinstance(sources, list) or len(sources) != 1:
        raise ValueError("Observe exactly one active project guard source; reconcile ambiguous guards")
    source = sources[0]
    fields(source, ("path", "sha256", "trusted", "scripts"))
    if source["path"] != str(root / ".codex/hooks.json") or source["trusted"] is not True:
        raise ValueError("The exact project guard source must be observed trusted in this client")
    if (digest(read_file(source["path"], wf)) != source["sha256"] or not isinstance(source["scripts"], dict)
            or str(root / ".codex/hooks/subagents.py") not in source["scripts"]):
        raise ValueError("Observed hook definition changed; refresh native discovery evidence")
    for path, sha in source["scripts"].items():
        if digest(read_file(path, wf)) != sha:
            raise ValueError("Reviewed hook script changed; review current source and discovery")
    hooks = loads(read_file(source["path"], wf)).get("hooks", {})
    for event in ("PreToolUse", "SubagentStart", "SubagentStop"):
        commands = [hook.get("command", "") for group in hooks.get(event, [])
                    for hook in group.get("hooks", []) if "subagents.py" in str(hook.get("command", ""))]
        relative = f'python3 "$(git rev-parse --show-toplevel)/.codex/hooks/subagents.py" {event}'
        absolute = ["python3", str(root / ".codex/hooks/subagents.py"), event]
        if len(commands) != 1 or (commands[0] != relative and shlex.split(commands[0]) != absolute):
            raise ValueError("Observed project definition does not uniquely reference the reviewed guard")


def protected_snapshot(paths, wf):
    if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths) or len(set(paths)) != len(paths):
        raise ValueError("Supply unique explicit protected file paths")
    return {path: wf["fingerprint"](Path(path)) for path in paths}


def workspace_snapshot(root, wf):
    paths = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part in (".git", ".codex-delegations") for part in relative.parts):
            continue
        if path.is_symlink():
            paths.append((str(relative), {"symlink": str(path.readlink())}))
        elif path.is_file():
            if len(paths) >= 10000 or path.stat().st_size > 16 * 1024 * 1024:
                raise ValueError("Probe workspace is too large for bounded preservation evidence; select a smaller canary root")
            paths.append((str(relative), wf["fingerprint"](path)))
    return dict(paths)


def guard():
    return runpy.run_path(str(PACKAGE / ".codex/hooks/subagents.py"))


def worker_selection(request):
    selection = request.get("worker_selection")
    if "worker_selection" not in request:
        return None
    fields(selection, ("model", "reasoning_effort", "authorization", "supported_pairs"))
    if (not all(nonblank(selection[key]) for key in ("model", "reasoning_effort", "authorization"))
            or not {"model", "reasoning_effort", "fork_turns"} <= set(request["tool"]["fields"])):
        raise ValueError("Explicit worker selection requires authorization and supported native controls")
    pairs = selection["supported_pairs"]
    if not isinstance(pairs, list) or not 1 <= len(pairs) <= 128:
        raise ValueError("Supply bounded model/effort pairs observed from this native host")
    for pair in pairs:
        fields(pair, ("model", "reasoning_effort"))
        if not all(nonblank(value) for value in pair.values()):
            raise ValueError("Observed model/effort pairs must be nonblank")
    if {key: selection[key] for key in ("model", "reasoning_effort")} not in pairs:
        raise ValueError("Requested worker model/effort pair is not supported by this host observation")
    return selection


def packet(root, name, tool, selection=None):
    skeleton = {"status": "done", "summary": "Describe the observed role, specialty, root and result.",
                "changed_files": [], "checks": ["List actual read results."], "risks": [], "blockers": [],
                "next_action": "Coordinator verifies native evidence and display."}
    settings_instruction = ("preserve inherited model, reasoning, provider, authentication and permissions. "
        if selection is None else
        f"use the explicitly selected worker model {selection['model']} and reasoning {selection['reasoning_effort']}; "
        "preserve provider, authentication and permissions. Do not change Coordinator settings. ")
    args = {"task_name": name, "message": (
        f"Harness root: {root}. Read .codex-delegations/{name}.json before work. Software and command root: {root}. "
        "Read only the declared files; " + settings_instruction +
        "Do not delegate, write, install, run tests, invoke hooks or retry. Return exactly one delegation-report JSON fence "
        "with these seven fields only; replace example text with actual findings: " + json.dumps(skeleton))}
    if "fork_turns" in tool["fields"]:
        args["fork_turns"] = "all"
    if selection is not None:
        args.update(model=selection["model"], reasoning_effort=selection["reasoning_effort"], fork_turns="none")
    return args, skeleton


def prepare(root, request, wf):
    fields(request, ("record_path", "task_name", "parent_log", "client_context", "tool", "read_paths",
                     "protected_files", "display_required"), ("worker_selection",))
    if type(request["display_required"]) is not bool:
        raise ValueError("display_required must be boolean")
    name = request["task_name"]
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9_]{1,64}", name):
        raise ValueError("A supported top-level task_name is required")
    tool = request["tool"]
    fields(tool, ("name", "fields"))
    if (tool["name"] not in SPAWNS or not isinstance(tool["fields"], list)
            or not all(isinstance(item, str) for item in tool["fields"])
            or not {"task_name", "message"} <= set(tool["fields"])):
        raise ValueError("The current native tool schema cannot carry the required dispatch packet")
    selection = worker_selection(request)
    _, rows = log_rows(request["parent_log"], wf)
    meta, turn, settings = native_context(rows)
    observation, observation_ref = artifact(request["client_context"], wf)
    validate_observation(observation, root, meta, wf)
    contract = guard()
    brief = contract["read_brief"](name, root)
    if (not contract["valid_brief"](brief) or brief.get("role") not in contract["ROLES"]
            or not contract["text"](brief.get("specialty")) or brief["read_only"] is not True
            or brief["budget"]["attempts"] != 1):
        raise ValueError("Qualification requires a valid explicit role/specialty and read-only, one-attempt declaration")
    pointer = f".codex-delegations/{name}.json"
    declaration = root / pointer
    reads = request["read_paths"]
    if not isinstance(reads, list) or not reads or len(reads) > 16:
        raise ValueError("Supply bounded explicit files to read")
    expected_reads = [{"path": str(declaration), "max_lines": None, "sha256": digest(read_file(declaration, wf))}]
    for item in reads:
        fields(item, ("path", "max_lines"))
        path = wf["canonical"](Path(item["path"]))
        if not path.is_relative_to(root):
            raise ValueError("Probe reads must stay within the declared harness")
        lines = item["max_lines"]
        if lines is not None and (type(lines) is not int or not 1 <= lines <= 200):
            raise ValueError("max_lines must be null or an integer from 1 to 200")
        raw = read_file(path, wf)
        expected_reads.append({**item, "sha256": digest(raw)})
    if len({item["path"] for item in expected_reads}) != len(expected_reads):
        raise ValueError("Do not duplicate probe read paths")
    args, skeleton = packet(root, name, tool, selection)
    return {"schema_version": 1, "run_id": str(uuid4()), "root": str(root), "state": "prepared",
            "request": request, "native_arguments": args, "report_skeleton": skeleton,
            "specialty_assessment": "Not assessed", "role": brief["role"], "settings": settings,
            "parent_thread_id": meta["id"], "parent_turn_id": turn["turn_id"], "client": observation["client"],
            "context": observation, "context_ref": observation_ref, "reads": expected_reads,
            "protected": protected_snapshot(request["protected_files"], wf), "attempts": 0,
            "workspace": workspace_snapshot(root, wf),
            "prepared_at": time.time(), "result": None,
            **({"worker_selection": loads(json.dumps(selection))} if selection is not None else {})}


def revalidate(record, root, wf, *, before_dispatch=False):
    required = {"schema_version", "run_id", "root", "state", "request", "native_arguments", "report_skeleton",
                "specialty_assessment", "role", "settings", "parent_thread_id", "parent_turn_id", "client", "context",
                "context_ref", "reads", "protected", "attempts", "workspace", "prepared_at", "result"}
    consumed = {"begun_at", "parent_offset", "parent_prefix_sha256"}
    fields(record, required, consumed | {"worker_selection"})
    if record.get("schema_version") != 1 or record.get("root") != str(root):
        raise ValueError("Unsupported or foreign probe receipt")
    if record.get("state") not in ("prepared", "begun", "denied", "uncertain", "observed"):
        raise ValueError("Unknown probe state")
    wf["uuid_string"](record["run_id"])
    prepared = record["state"] == "prepared"
    if (type(record["attempts"]) is not int or record["attempts"] != (0 if prepared else 1)
            or (not prepared and not consumed <= set(record)) or (prepared and consumed & set(record))):
        raise ValueError("Malformed qualification attempt state")
    if not prepared and (type(record["parent_offset"]) is not int or record["parent_offset"] < 0
                         or type(record["begun_at"]) not in (int, float)
                         or not re.fullmatch(r"[0-9a-f]{64}", str(record["parent_prefix_sha256"]))):
        raise ValueError("Malformed consumed-attempt evidence")
    request = record["request"]
    fields(request, ("record_path", "task_name", "parent_log", "client_context", "tool", "read_paths",
                     "protected_files", "display_required"), ("worker_selection",))
    if (not isinstance(request["task_name"], str) or not re.fullmatch(r"[a-z0-9_]{1,64}", request["task_name"])
            or type(request["display_required"]) is not bool):
        raise ValueError("Malformed qualification request")
    fields(request["tool"], ("name", "fields"))
    if (request["tool"]["name"] not in SPAWNS or not isinstance(request["tool"]["fields"], list)
            or not all(isinstance(item, str) for item in request["tool"]["fields"])
            or not {"task_name", "message"} <= set(request["tool"]["fields"])):
        raise ValueError("Unsupported native tool packet")
    selection = worker_selection(request)
    if selection != record.get("worker_selection"):
        raise ValueError("Prepared worker selection, authorization or host inventory changed")
    args, skeleton = packet(root, request["task_name"], request["tool"], selection)
    if record["native_arguments"] != args or record["report_skeleton"] != skeleton:
        raise ValueError("Prepared native arguments changed; never dispatch overrides or a rebuilt message")
    contract = guard()
    brief = contract["read_brief"](request["task_name"], root)
    if (not contract["valid_brief"](brief) or brief.get("role") != record["role"]
            or not brief["read_only"] or brief["budget"]["attempts"] != 1):
        raise ValueError("Qualification declaration is no longer valid")
    if not isinstance(record["reads"], list) or not record["reads"] or not isinstance(record["protected"], dict):
        raise ValueError("Malformed qualification input fingerprints")
    for item in record["reads"]:
        if digest(read_file(item["path"], wf)) != item["sha256"]:
            raise ValueError("Declaration or probe input changed; preserve the consumed attempt")
    if protected_snapshot(list(record["protected"]), wf) != record["protected"]:
        raise ValueError("Protected configuration changed; reconcile without retrying")
    context, ref = artifact(record["context_ref"]["path"], wf)
    if ref != record["context_ref"] or context != record["context"] or context["client"] != record["client"]:
        raise ValueError("Client observation changed; retain the original evidence")
    raw, rows = log_rows(record["request"]["parent_log"], wf)
    meta, turn, settings = native_context(rows)
    validate_observation(context, root, meta, wf)
    if (meta["id"] != record["parent_thread_id"] or (before_dispatch and turn["turn_id"] != record["parent_turn_id"])
            or settings != record["settings"]):
        raise ValueError("Native parent context changed; the prepared packet is stale")
    if record["result"] and record["result"].get("coordinator_settings_preserved"):
        later = [loads(line) for line in raw[record["parent_offset"]:].splitlines() if line.strip()]
        if not settings_match(later, record["settings"]):
            raise ValueError("Coordinator settings changed after dispatch; invalidate cached preservation evidence")
    return raw, rows


def verify_artifacts(refs, wf):
    for ref in refs:
        raw = read_file(ref["path"], wf, MAX_LOG if "bytes" in ref else 16 * 1024 * 1024)
        if "bytes" in ref:
            raw = raw[:ref["bytes"]]
        if digest(raw) != ref["sha256"]:
            raise ValueError("Recorded native or display evidence changed; invalidate this qualification")


def output_strings(value):
    """Unwrap native tool output JSON without executing or interpreting its text."""
    if isinstance(value, str):
        yield value
        try:
            decoded = loads(value)
        except (ValueError, TypeError, RecursionError):
            return
        if not isinstance(decoded, str):
            yield from output_strings(decoded)
    elif isinstance(value, list):
        for item in value:
            yield from output_strings(item)
    elif isinstance(value, dict):
        for key in ("output", "text", "content"):
            if key in value:
                yield from output_strings(value[key])


def successful_spawn(outputs, child_id, name):
    for output in outputs:
        for text in output_strings(output):
            try:
                value = loads(text)
            except (ValueError, TypeError):
                continue
            if not isinstance(value, dict):
                continue
            if set(value) == {"task_name"} and value["task_name"] == "/root/" + name:
                return True
            if ("agent_id" in value and set(value) <= {"agent_id", "nickname", "agent_nickname"}
                    and value["agent_id"] == child_id):
                return True
    return False


def evaluate(record, request, wf):
    raw, parent_rows = revalidate(record, Path(record["root"]), wf)
    offset = record["parent_offset"]
    if digest(raw[:offset]) != record["parent_prefix_sha256"]:
        raise ValueError("Parent native history changed; preserve and inspect evidence")
    new_rows = [loads(line) for line in raw[offset:].splitlines() if line.strip()]
    events = [row.get("payload", {}) for row in new_rows]
    coordinator_ok = settings_match(new_rows, record["settings"])
    selection = record.get("worker_selection")
    expected_settings = dict(record["settings"])
    if selection is not None:
        expected_settings.update(model=selection["model"], effort=selection["reasoning_effort"])
    calls = [item for item in events if item.get("type") in ("function_call", "custom_tool_call")
             and item.get("name") in SPAWNS]
    observed_args = []
    for call in calls:
        try:
            observed_args.append(loads(call.get("arguments", call.get("input", "{}"))))
        except (ValueError, TypeError):
            observed_args.append({})
    argument_match = len(calls) == 1 and observed_args[0] == record["native_arguments"]
    dispatch_refs = []
    if "dispatch_evidence" in request:
        capture, ref = artifact(request["dispatch_evidence"], wf)
        fields(capture, ("call_id", "tool", "arguments", "observed_via", "source_ref"))
        if (len(calls) != 1 or capture["call_id"] != calls[0].get("call_id")
                or capture["tool"] != record["request"]["tool"]["name"]
                or capture["observed_via"] != "native-tool-call" or not nonblank(capture["source_ref"])
                or capture["arguments"] != record["native_arguments"]):
            raise ValueError("Native dispatch capture must bind the exact prepared packet and call ID")
        # Some hosts encrypt only message text in disk logs. The attributed tool
        # capture supplies that missing observation; every visible field must match.
        visible = observed_args[0]
        encrypted = isinstance(visible, dict) and isinstance(visible.get("message"), str) and visible["message"].startswith("gAAAA")
        if not argument_match and encrypted:
            argument_match = ({**visible, "message": capture["arguments"]["message"]} == record["native_arguments"])
        dispatch_refs.append(ref)
    outputs = [item for item in events if item.get("call_id") in {call.get("call_id") for call in calls}
               and item.get("type") in ("function_call_output", "custom_tool_call_output")]
    denied = any("dispatch denied" in text.lower() for item in outputs for text in output_strings(item))
    result = {"attempts": 1, "native_calls": len(calls), "execution_passed": False,
              "protocol_passed": False, "recovery_observed": False, "settings_preserved": False,
              "selection_verified": False, "coordinator_settings_preserved": coordinator_ok,
              "requested_worker_settings": expected_settings, "observed_worker_settings": [],
              "display_passed": False, "complete": False, "authentication": "not_exposed",
              "state": "denied" if denied else "uncertain", "child_thread_id": None,
              "evidence": dispatch_refs, "next_action": "Reconcile this consumed attempt; never dispatch it again."}
    if denied or "child_log" not in request:
        return result
    child_raw, child_rows = log_rows(request["child_log"], wf)
    meta, _, _ = native_context(child_rows)
    spawn = meta.get("source", {})
    spawn = spawn.get("subagent", {}).get("thread_spawn", {}) if isinstance(spawn, dict) else {}
    parent = meta.get("parent_thread_id", spawn.get("parent_thread_id"))
    name = record["native_arguments"]["task_name"]
    if (parent != record["parent_thread_id"] or meta["id"] == parent
            or spawn.get("agent_path", meta.get("agent_path", "")).split("/")[-1] != name
            or meta["cwd"] != record["root"]):
        raise ValueError("Child identity does not bind the dispatched native task")
    try:
        created_at = datetime.fromisoformat(meta["timestamp"].replace("Z", "+00:00")).timestamp()
    except (ValueError, KeyError, AttributeError) as error:
        raise ValueError("Child creation timestamp is required to bind this attempt") from error
    result_bound = created_at >= record["begun_at"] and successful_spawn(outputs, meta["id"], name)
    # Forked logs contain parent history. Start at the first child-owned turn.
    starts = [index for index, row in enumerate(child_rows) if row.get("type") == "turn_context"
              and row["payload"].get("root_turn_id") == record["parent_turn_id"]
              and row["payload"].get("turn_id") != record["parent_turn_id"]]
    if selection is not None:
        # A fresh worker has no inherited root turn. Bind its first turn to the
        # native task-start event, excluding every observed parent turn identity.
        parent_turns = {row["payload"].get("turn_id") for row in parent_rows if row.get("type") == "turn_context"}
        turns = [(index, row["payload"]) for index, row in enumerate(child_rows) if row.get("type") == "turn_context"]
        starts = []
        if turns:
            index, turn = turns[0]
            started = any(row.get("type") == "event_msg" and row.get("payload", {}).get("type") == "task_started"
                          and row["payload"].get("turn_id") == turn.get("turn_id") for row in child_rows[:index])
            if started and all(nonblank(item.get("turn_id")) and item["turn_id"] not in parent_turns for _, item in turns):
                starts = [index]
    if not starts:
        raise ValueError("Cannot distinguish child execution from inherited history")
    own = child_rows[starts[0]:]
    child_settings = [{**{key: row["payload"].get(key) for key in SETTINGS}, "provider": meta.get("model_provider")}
                      for row in own if row.get("type") == "turn_context"]
    settings_ok = bool(child_settings) and all(item == expected_settings for item in child_settings)
    items = [row.get("payload", {}) for row in own if row.get("type") == "response_item"]
    reports = []
    for item in items:
        if item.get("type") != "message" or item.get("role") != "assistant":
            continue
        text = "".join(part.get("text", "") for part in item.get("content", []) if isinstance(part, dict))
        if "phase" not in item and ("```delegation-report" in text or "```json" in text):
            raise ValueError("Unphased native reports cannot establish first-report validity; preserve this attempt as unqualified")
        if item.get("phase") in ("final", "final_answer"):
            reports.append(text)
    contract = guard()
    parsed = []
    for text in reports:
        try:
            report = contract["fenced_object"](text, ("delegation-report", "json"))
            parsed.append(report if contract["valid_report"](report) else None)
        except (ValueError, TypeError, KeyError, RecursionError):
            parsed.append(None)
    read_results = {}
    for item in record["reads"]:
        content = read_file(item["path"], wf).decode("utf-8")
        if item["max_lines"] is not None:
            content = "".join(content.splitlines(keepends=True)[:item["max_lines"]])
        matching = {event.get("call_id") for event in items
                    if event.get("type") in ("function_call", "custom_tool_call")
                    and (item["path"] in str(event) or str(Path(item["path"]).relative_to(record["root"])) in str(event))}
        read_results[item["path"]] = bool(content.strip()) and any(
            content.strip() in text for event in items if event.get("call_id") in matching
            and event.get("type") in ("function_call_output", "custom_tool_call_output")
            for text in output_strings(event))
    final = parsed[-1] if parsed else None
    mutation_tools = {"apply_patch", "write_file", "edit_file", "Write", "Edit"} | SPAWNS
    unexpected_actions = any(item.get("type") in ("function_call", "custom_tool_call")
                             and item.get("name") in mutation_tools for item in items)
    workspace_ok = workspace_snapshot(Path(record["root"]), wf) == record["workspace"]
    execution = bool(argument_match and result_bound and settings_ok and coordinator_ok and workspace_ok and not unexpected_actions
                     and all(read_results.values()) and final
                     and final["status"] == "done" and not final["changed_files"] and not final["blockers"])
    protocol = bool(argument_match and result_bound and len(reports) == 1 and parsed[0] and not unexpected_actions)
    result.update(state="observed", execution_passed=execution, protocol_passed=protocol,
                  recovery_observed=len(reports) > 1 and parsed[0] is None and final is not None,
                  settings_preserved=settings_ok, child_thread_id=meta["id"], read_results=read_results,
                  selection_verified=bool(selection is not None and argument_match and result_bound and settings_ok and coordinator_ok),
                  observed_worker_settings=child_settings,
                  first_report_valid=bool(parsed and parsed[0]), final_reports=len(reports),
                  workspace_preserved=workspace_ok, arguments_verified=argument_match,
                  evidence=dispatch_refs + [{"path": request["child_log"], "sha256": digest(child_raw), "bytes": len(child_raw)},
                            {"path": record["request"]["parent_log"], "sha256": digest(raw), "bytes": len(raw)}])
    if "display_evidence" in request:
        display, ref = artifact(request["display_evidence"], wf)
        fields(display, ("client", "parent_thread_id", "child_thread_id", "role", "observed_label",
                         "observer_started_at", "observed_at", "source"), ("snapshot",))
        if (display["client"] != record["client"] or display["parent_thread_id"] != record["parent_thread_id"]
                or display["child_thread_id"] != meta["id"] or display["role"] != record["role"]
                or display["source"] != "habblaud"
                or any(type(display[key]) not in (int, float) for key in ("observer_started_at", "observed_at"))
                or not display["observer_started_at"] <= record["begun_at"] <= display["observed_at"]):
            raise ValueError("Display observation must bind this child and an observer armed before dispatch")
        result["display_passed"] = display["observed_label"] == record["role"]
        result["evidence"].append(ref)
        if "snapshot" in display:
            snapshot = read_file(display["snapshot"], wf, 16 * 1024 * 1024)
            result["evidence"].append({"path": display["snapshot"], "sha256": digest(snapshot)})
    result["complete"] = execution and protocol and (result["display_passed"] or not record["request"]["display_required"])
    result["next_action"] = ("Qualification passed; retain client-bound evidence." if result["complete"] else
                             "Review unmet execution, first-report or display outcomes; this attempt is consumed.")
    return result


def handle(operation, root, request, workflow):
    wf = workflow
    root = wf["canonical"](Path(root))
    if not isinstance(request, dict) or "record_path" not in request:
        raise ValueError("Supply the explicit private probe record_path")
    path = wf["canonical"](Path(request["record_path"]))
    if path.is_relative_to(root) or path.is_relative_to(PACKAGE) or path.suffix != ".json":
        raise ValueError("Keep probe records outside source and discovery directories")
    wf["safe_file"](path)
    if operation != "prepare-probe":
        fields(request, ("record_path",), ("child_log", "display_evidence", "dispatch_evidence") if operation == "record-probe" else ())
    if operation == "status-probe":
        record, _ = artifact(path, wf)
        revalidate(record, root, wf)
        if record["result"]:
            verify_artifacts(record["result"]["evidence"], wf)
        return {"status": "ok", "operation": operation, **(record["result"] or {
            "state": record["state"], "attempts": record["attempts"], "complete": False}), "evidence_ref": str(path)}
    if not path.parent.is_dir():
        raise ValueError("Create the explicit private evidence directory before preparing a probe")
    lock_path = path.with_suffix(".lock")
    wf["safe_file"](lock_path)
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if operation == "prepare-probe":
            if path.exists():
                raise ValueError("Probe identity already exists; inspect or reconcile it without repeating dispatch")
            record = prepare(root, request, wf)
        else:
            record, _ = artifact(path, wf)
            raw, _ = revalidate(record, root, wf, before_dispatch=operation == "begin-probe")
            if operation == "begin-probe":
                if record["state"] != "prepared" or record["attempts"] != 0:
                    raise ValueError("This attempt is consumed; a denial or uncertain response never permits a retry")
                record.update(state="begun", attempts=1, begun_at=time.time(), parent_offset=len(raw),
                              parent_prefix_sha256=digest(raw))
            elif operation == "record-probe":
                if record["attempts"] != 1 or record["state"] == "prepared":
                    raise ValueError("Persist begin-probe before invoking the native tool")
                record["result"] = evaluate(record, request, wf)
                record["state"] = record["result"]["state"]
            else:
                raise ValueError("Unsupported native qualification operation")
        wf["write_record"](path, record)
    result = {"status": "ok", "operation": operation, "evidence_ref": str(path)}
    if operation == "record-probe":
        result.update(record["result"])
    else:
        result.update({key: record[key] for key in ("state", "attempts", "native_arguments", "report_skeleton", "specialty_assessment")})
    return result
