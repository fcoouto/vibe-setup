"""Pure routing plans and evidence reports; never dispatch, approve or activate models.

Evidence files are Coordinator observations, not host attestations. Planning does
not reserve attempts or local capacity: the executor owns durable accounting and
must recheck the installed local plugin before submission.
"""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import runpy
import tomllib

LIMIT = 1024 * 1024
DIMENSIONS = {"reasoning", "ambiguity", "coupling", "context"}
STATES = {"not_assessed", "pilot_only", "qualified", "suspended"}


def fields(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) or set(value) - set(required) - set(optional):
        raise ValueError("Unknown or missing delegation policy fields")


def text(value):
    if not isinstance(value, str) or not 0 < len(value.strip()) <= 4096:
        raise ValueError("Expected nonempty bounded text")
    return value


def integer(value, minimum=0, maximum=10000000):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("Expected a bounded integer")
    return value


def boolean(value):
    if type(value) is not bool:
        raise ValueError("Expected a boolean")
    return value


def strings(value, nonempty=False):
    if not isinstance(value, list) or len(value) > 1000 or (nonempty and not value):
        raise ValueError("Expected a bounded list")
    for item in value:
        text(item)
    if len(set(value)) != len(value):
        raise ValueError("Duplicate list item")
    return value


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(text(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Expected an ISO8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError("Timestamp needs an explicit timezone")
    return parsed


def canonical(value):
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    except (TypeError, ValueError, RecursionError) as error:
        raise ValueError("Expected finite JSON data") from error
    if len(raw) > LIMIT:
        raise ValueError("Delegation policy input exceeds 1 MiB")
    return raw


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def evidence(path, wf, refs, parse=False):
    path = Path(text(path))
    wf["safe_file"](path)
    try:
        with path.open("rb") as stream:
            raw = stream.read(LIMIT + 1)
    except OSError as error:
        raise ValueError("Evidence file is unavailable") from error
    if len(raw) > LIMIT:
        raise ValueError("Evidence exceeds 1 MiB")
    reference = {"path": str(path), "sha256": sha(raw)}
    if reference not in refs:
        refs.append(reference)
    if parse:
        try:
            value = json.loads(raw, object_pairs_hook=unique_object)
            canonical(value)
            return value
        except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
            raise ValueError("Malformed evidence JSON") from error
    return raw


def settings(value):
    fields(value, ("model", "effort", "provider", "permissions", "session_id"))
    for key in value:
        if key == "permissions" and isinstance(value[key], dict) and value[key]:
            canonical(value[key])
        else:
            text(value[key])


def scope_matches(scope, task, difficulty):
    fields(scope, ("role", "specialty", "domain", "language", "tiers", "risks", "context_tokens", "output_tokens", "tools"))
    for key in ("role", "specialty", "domain", "language"):
        text(scope[key])
    if not isinstance(scope["tiers"], list) or not scope["tiers"]:
        raise ValueError("Qualification must list assessed difficulty tiers")
    for tier in scope["tiers"]:
        integer(tier, 0, 3)
    strings(scope["risks"], True)
    if set(scope["risks"]) - {"R0", "R1", "R2"}:
        raise ValueError("Unknown risk")
    strings(scope["tools"])
    integer(scope["context_tokens"], 1)
    integer(scope["output_tokens"], 1)
    return (all(scope[key] == task[key] for key in ("role", "specialty", "domain", "language"))
            and difficulty in scope["tiers"] and task["risk"] in scope["risks"]
            and task["context_tokens"] <= scope["context_tokens"] and task["output_tokens"] <= scope["output_tokens"]
            and set(task["tools"]) <= set(scope["tools"]))


def pilot_passed(rows, wf, refs):
    if not isinstance(rows, list) or not 12 <= len(rows) <= 1000:
        return False
    seen, hashes, categories = set(), set(), {key: 0 for key in ("ordinary", "boundary", "failure")}
    for row in rows:
        fields(row, ("case_id", "case_hash", "category", "baseline", "candidate", "rescued", "critical_failure", "evidence_ref"))
        identity = text(row["case_id"])
        if not re.fullmatch(r"[a-f0-9]{64}", text(row["case_hash"])):
            raise ValueError("Frozen case hash is invalid")
        if identity in seen or row["case_hash"] in hashes or row["category"] not in categories:
            return False
        seen.add(identity)
        hashes.add(row["case_hash"])
        categories[row["category"]] += 1
        evidence(row["evidence_ref"], wf, refs)
        if row["baseline"] != "passed" or row["candidate"] != "passed" or row["rescued"] is not False or row["critical_failure"] is not False:
            return False
    return all(count >= 4 for count in categories.values())


def canary_passed(rows, wf, refs):
    if not isinstance(rows, list) or len(rows) != 10:
        return False
    seen = set()
    for row in rows:
        fields(row, ("task_id", "outcome", "rescued", "critical_failure", "evidence_ref"))
        identity = text(row["task_id"])
        if identity in seen:
            return False
        seen.add(identity)
        evidence(row["evidence_ref"], wf, refs)
        if row["outcome"] != "accepted" or row["rescued"] is not False or row["critical_failure"] is not False:
            return False
    return True


def candidate_reason(candidate, request, difficulty, now, wf, refs):
    task, client, mode = request["task"], request["client"], request["mode"]
    fields(candidate, ("id", "route", "model", "effort", "provider", "version", "authorization_ref", "qualification_ref",
                       "tools", "context_limit", "output_limit"),
           ("expected_cost", "expected_seconds", "timing_ref", "local_status_ref", "avoid_local_ref"))
    for key in ("id", "model", "effort", "provider", "version"):
        text(candidate[key])
    if candidate["route"] not in ("native", "local"):
        raise ValueError("Unknown candidate route")
    strings(candidate["tools"])
    integer(candidate["context_limit"], 1)
    integer(candidate["output_limit"], 1)
    evidence(candidate["authorization_ref"], wf, refs)
    if candidate["route"] == "native" and candidate["provider"] != request["coordinator"]["provider"]:
        return "Native provider changes are not authorized"
    if (not set(task["tools"]) <= set(candidate["tools"]) or candidate["context_limit"] < task["context_tokens"]
            or candidate["output_limit"] < task["output_tokens"]):
        return "Context, output or tools do not fit the complete task"
    if candidate["route"] == "native" and (not client["selection_supported"] or not client["observation_supported"]
            or {"model": candidate["model"], "effort": candidate["effort"]} not in client["pairs"]):
        return "Exact native selection and observation are unsupported"
    if "expected_cost" in candidate:
        cost = candidate["expected_cost"]
        fields(cost, ("unit", "total", "evidence_ref"))
        text(cost["unit"])
        number(cost["total"])
        evidence(cost["evidence_ref"], wf, refs)
    if "expected_seconds" in candidate:
        number(candidate["expected_seconds"])
        evidence(candidate.get("timing_ref"), wf, refs)
        if candidate["expected_seconds"] > (timestamp(request["budget"]["deadline"]) - now).total_seconds():
            return "Observed expected duration exceeds the explicit deadline"
    q = evidence(candidate["qualification_ref"], wf, refs, True)
    fields(q, ("state", "binding", "scope", "expires_at", "review_ref", "pilot", "canary"))
    if q["state"] not in STATES:
        raise ValueError("Unknown qualification state")
    if not isinstance(q["pilot"], list) or not isinstance(q["canary"], list):
        raise ValueError("Qualification cohorts must retain their case records")
    binding = {key: candidate[key] for key in ("route", "model", "effort", "provider", "version")}
    binding.update(client=client["name"], client_version=client["version"], tool=client["tool"])
    if candidate["route"] == "local":
        local = evidence(candidate.get("local_status_ref"), wf, refs, True)
        fields(local, ("routing_enabled", "approved", "assessment_passed", "admitted", "expires_at", "runtime_digest",
                       "approval_ref", "assessment_ref", "admission_ref", "evaluation_path"))
        for key in ("routing_enabled", "approved", "assessment_passed", "admitted", "evaluation_path"):
            boolean(local[key])
        if not re.fullmatch(r"[a-f0-9]{64}", text(local["runtime_digest"])):
            raise ValueError("Local runtime digest is invalid")
        binding["runtime_digest"] = local["runtime_digest"]
        for key in ("approval_ref", "assessment_ref", "admission_ref"):
            evidence(local[key], wf, refs)
        if not all(local[key] for key in ("routing_enabled", "approved", "assessment_passed", "admitted")) or timestamp(local["expires_at"]) <= now:
            return "Local plugin approval, assessment or current admission is unavailable"
        if mode == "evaluation" and not local["evaluation_path"]:
            return "Local evaluations must use the plugin's authorized assessment path"
        if candidate.get("avoid_local_ref"):
            avoid = evidence(candidate["avoid_local_ref"], wf, refs, True)
            fields(avoid, ("reason", "qualification_ref", "evidence_ref", "expires_at"))
            evidence(avoid["evidence_ref"], wf, refs)
            if avoid["reason"] != "measured_harm" or avoid["qualification_ref"] != candidate["qualification_ref"]:
                raise ValueError("Local bypass needs measured harm in the exact qualification scope")
            if timestamp(avoid["expires_at"]) > now:
                return "Measured harmful local outcome; use recorded bounded bypass"
    if q["binding"] != binding or timestamp(q["expires_at"]) <= now or not scope_matches(q["scope"], task, difficulty):
        return "Qualification is stale, mismatched or outside task scope"
    if mode == "ordinary":
        if q["state"] != "qualified" or not pilot_passed(q["pilot"], wf, refs) or not canary_passed(q["canary"], wf, refs):
            return "Ordinary selection needs an intact paired pilot and unrescued ten-task canary"
        evidence(q["review_ref"], wf, refs)
    else:
        if "manifest" not in request:
            return "Evaluation or canary authority is absent"
        manifest = evidence(request["manifest"], wf, refs, True)
        fields(manifest, ("mode", "candidate_bindings", "authorization_ref", "expires_at", "max_calls", "used_calls", "scope",
                          "case_refs", "rubric_ref", "stop_conditions", "disposable"), ("diagnosis_ref",))
        bindings = manifest["candidate_bindings"]
        if not isinstance(bindings, dict) or not 1 <= len(bindings) <= 64:
            raise ValueError("Manifest must freeze a bounded candidate binding map")
        for identity, authorized in bindings.items():
            text(identity)
            fields(authorized, ("route", "model", "effort", "provider", "version", "client", "client_version", "tool"), ("runtime_digest",))
            for value in authorized.values():
                text(value)
            if authorized["route"] not in ("local", "native") or (("runtime_digest" in authorized) != (authorized["route"] == "local")):
                raise ValueError("Manifest must bind the exact route and local runtime when applicable")
            if "runtime_digest" in authorized and not re.fullmatch(r"[a-f0-9]{64}", authorized["runtime_digest"]):
                raise ValueError("Manifest local runtime digest is invalid")
        if bindings.get(candidate["id"]) != binding:
            return "Manifest candidate binding changed; obtain a new bounded authorization"
        strings(manifest["case_refs"], True)
        strings(manifest["stop_conditions"], True)
        boolean(manifest["disposable"])
        integer(manifest["max_calls"], 1, 1000)
        integer(manifest["used_calls"], 0, 1000)
        for ref in (manifest["authorization_ref"], manifest["rubric_ref"], *manifest["case_refs"]):
            evidence(ref, wf, refs)
        if (manifest["mode"] != mode or timestamp(manifest["expires_at"]) <= now
                or manifest["used_calls"] >= manifest["max_calls"] or not scope_matches(manifest["scope"], task, difficulty)):
            return "Bounded manifest does not authorize another matching call"
        if mode == "canary":
            if (q["state"] != "pilot_only" or not pilot_passed(q["pilot"], wf, refs) or manifest["max_calls"] > 10 or len(q["canary"]) >= 10
                    or any(not isinstance(row, dict) for row in q["canary"])
                    or any(row.get("outcome") != "accepted" or row.get("rescued") is not False or row.get("critical_failure") is not False for row in q["canary"])
                    or (task["risk"] == "R2" and not manifest["disposable"])):
                return "Canary gate, cohort or disposable high-impact scope is not satisfied"
            evidence(q["review_ref"], wf, refs)
        elif q["state"] == "suspended":
            if not manifest.get("diagnosis_ref"):
                return "Suspended scope requires diagnosis and authorized reassessment"
            evidence(manifest["diagnosis_ref"], wf, refs)
    return None


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("Expected a finite nonnegative measurement")
    return value


def plan(root, request, wf):
    fields(request, ("task", "coordinator", "client", "candidates", "budget", "attempts", "mode"), ("manifest", "recovery"))
    refs, now = [], datetime.now(timezone.utc)
    task = request["task"]
    fields(task, ("task_id", "role", "specialty", "domain", "language", "dimensions", "risk", "checks", "independent_review",
                  "delegation_reason", "context_tokens", "output_tokens", "tools", "source_ref", "contract_ref", "checks_ref"))
    for key in ("task_id", "role", "specialty", "domain", "language"):
        text(task[key])
    roles = runpy.run_path(str(Path(__file__).resolve().parent / ".codex/hooks/subagents.py"))["ROLES"]
    if task["role"] not in roles:
        raise ValueError("Unknown delegation role")
    fields(task["dimensions"], DIMENSIONS)
    for rating in task["dimensions"].values():
        fields(rating, ("rating", "reason"))
        integer(rating["rating"], 0, 3)
        text(rating["reason"])
    if task["risk"] not in ("R0", "R1", "R2") or request["mode"] not in ("ordinary", "evaluation", "canary"):
        raise ValueError("Unknown risk or execution mode")
    difficulty = max(max(row["rating"] for row in task["dimensions"].values()), 2 if task["risk"] == "R2" else 0)
    strings(task["checks"])
    strings(task["tools"])
    boolean(task["independent_review"])
    integer(task["context_tokens"], 1)
    integer(task["output_tokens"], 1)
    if not isinstance(task["delegation_reason"], str) or len(task["delegation_reason"]) > 4096:
        raise ValueError("Delegation reason must be bounded text")
    for key in ("source_ref", "contract_ref", "checks_ref"):
        evidence(task[key], wf, refs)
    source_refs = list(refs)
    settings(request["coordinator"])
    client = request["client"]
    fields(client, ("name", "version", "tool", "pairs", "selection_supported", "observation_supported", "evidence_ref"))
    if client["name"] not in ("app", "vscode"):
        raise ValueError("Client must be app or vscode")
    text(client["version"])
    text(client["tool"])
    boolean(client["selection_supported"])
    boolean(client["observation_supported"])
    if not isinstance(client["pairs"], list) or len(client["pairs"]) > 256:
        raise ValueError("Use a bounded supported pair catalog")
    for pair in client["pairs"]:
        fields(pair, ("model", "effort"))
        text(pair["model"])
        text(pair["effort"])
    evidence(client["evidence_ref"], wf, refs)
    budget = request["budget"]
    fields(budget, ("attempt_limit", "deadline", "output_tokens"))
    integer(budget["attempt_limit"], 1, 2)
    integer(budget["output_tokens"], 1)
    deadline = timestamp(budget["deadline"])
    if not isinstance(request["attempts"], list) or len(request["attempts"]) > 100:
        raise ValueError("Use a bounded attempt history")
    identities = set()
    for attempt in request["attempts"]:
        fields(attempt, ("attempt_id", "state", "request_hash"))
        text(attempt["attempt_id"])
        if attempt["attempt_id"] in identities or attempt["state"] not in {"failed", "denied", "canceled", "running", "uncertain", "completed", "accepted"}:
            raise ValueError("Duplicate attempt or unsupported state")
        if not re.fullmatch(r"[a-f0-9]{64}", text(attempt["request_hash"])):
            raise ValueError("Attempt request hash is invalid")
        identities.add(attempt["attempt_id"])
    if "recovery" in request:
        fields(request["recovery"], ("diagnosis", "changed_variable", "reason"))
        for value in request["recovery"].values():
            text(value)
    if not isinstance(request["candidates"], list) or len(request["candidates"]) > 64:
        raise ValueError("Use a bounded candidate list")
    ids = [text(row.get("id")) for row in request["candidates"] if isinstance(row, dict)]
    if len(ids) != len(request["candidates"]) or len(ids) != len(set(ids)):
        raise ValueError("Candidate identities must be unique")
    policy_path = root / ".codex/vibe-workflow.toml"
    wf["safe_file"](policy_path)
    policy = {}
    if policy_path.exists():
        try:
            policy = tomllib.loads(evidence(str(policy_path), wf, refs).decode()).get("worker_selection", {})
        except (UnicodeError, tomllib.TOMLDecodeError) as error:
            raise ValueError("Malformed worker selection policy") from error
    fields(policy, (), ("enabled", "authorization_ref"))
    enabled = boolean(policy.get("enabled", False))
    if enabled:
        text(policy.get("authorization_ref"))
    reason, route = "Worker selection is not adopted; preserve inheritance", "inherited"
    if not task["checks"] or not task["delegation_reason"].strip() or (task["risk"] == "R2" and not task["independent_review"]):
        reason, route = "Narrow the task or establish verification and independent review", "coordinator"
    elif (deadline <= now or task["output_tokens"] > budget["output_tokens"] or len(request["attempts"]) >= budget["attempt_limit"]):
        reason, route = "Dispatch budget exhausted; retain the Coordinator within the existing task budget", "coordinator"
    elif any(row["state"] in {"uncertain", "running", "completed", "accepted"} for row in request["attempts"]):
        reason, route = "Reconcile existing worker and checks before any replacement", "coordinator"
    elif request["attempts"] and "recovery" not in request:
        reason, route = "Recovery needs a diagnosis and one justified changed variable", "coordinator"
    eligible, rejections = [], []
    if enabled and route != "coordinator":
        for candidate in request["candidates"]:
            try:
                rejection = candidate_reason(candidate, request, difficulty, now, wf, refs)
            except (ValueError, OSError) as error:
                rejection = str(error)
            request_hash = None
            if rejection is None:
                request_hash = sha(canonical({"task": task, "candidate": {key: candidate[key] for key in ("route", "model", "effort", "provider", "version")}, "source": source_refs}))
                if request_hash in {row["request_hash"] for row in request["attempts"]}:
                    rejection = "Identical request already attempted; no replay"
            if rejection:
                rejections.append({"candidate_id": candidate["id"], "reason": rejection})
            else:
                eligible.append((candidate, request_hash))
        reason = "No matching eligible pair; preserve the authorized inherited route"
    ranking, decision = "provisional", {"route": route, "candidate_id": None, "reason": reason, "overrides": {}}
    if eligible:
        pool = [item for item in eligible if item[0]["route"] == "local"] or eligible
        costs = [item[0].get("expected_cost") for item in pool]
        if all(cost is not None for cost in costs) and len({cost["unit"] for cost in costs}) == 1:
            pool.sort(key=lambda item: item[0]["expected_cost"]["total"])
            ranking = "observed_cost_estimate"
        chosen, request_hash = pool[0]
        decision = {"route": chosen["route"], "candidate_id": chosen["id"], "model": chosen["model"], "effort": chosen["effort"],
                    "provider": chosen["provider"], "request_hash": request_hash, "qualification_ref": chosen["qualification_ref"],
                    "reason": "Qualified local preference" if chosen["route"] == "local" else "Eligible supported native pair",
                    "overrides": {"model": chosen["model"], "reasoning_effort": chosen["effort"], "fork_turns": "none"} if chosen["route"] == "native" else {}}
        for candidate, _ in eligible:
            if candidate["id"] != chosen["id"]:
                rejections.append({"candidate_id": candidate["id"], "reason": "Eligible alternative ranked after selected route"})
    result = wf["result"]("plan-delegation", "ok", "planning_only", project_root=str(root), task_id=task["task_id"], mode=request["mode"],
        policy_version=1, difficulty=difficulty, risk=task["risk"], coordinator=request["coordinator"],
        task=task, client=client, budget=budget, attempts=request["attempts"],
        authorization_ref=policy.get("authorization_ref"),
        decision=decision, ranking=ranking, rejections=rejections, evidence=refs, request_hash=sha(canonical(request)),
        next_action="Record the immutable attempt, recheck local admission if applicable, then execute through supported controls",
        limits=["External observations are not host attestation", "No model calls, approvals, capacity reservations or durable attempt transitions"])
    result["plan_hash"] = sha(canonical(result))
    return result


def accounting(measurements, mode, accepted, wf, refs):
    unknown = {"unit": None, "operating_difference": None, "experiment_investment": None,
               "delivered_net_estimate": None, "net_percent": None, "observed_spend": None,
               "coverage": "unknown", "savings_claim": "unknown"}
    if measurements is None:
        return unknown
    fields(measurements, ("unit", "matched", "match_ref", "expected_owners", "spans"))
    if measurements["unit"] not in ("token_proxy", "actual_currency", "price_estimate", "runtime_seconds"):
        raise ValueError("Unsupported measurement unit; never infer subscription savings")
    boolean(measurements["matched"])
    strings(measurements["expected_owners"], True)
    if set(measurements["expected_owners"]) != {"baseline", "candidate", "investment"}:
        raise ValueError("Explicit baseline, candidate and investment accounting is required")
    evidence(measurements["match_ref"], wf, refs)
    if not isinstance(measurements["spans"], list) or len(measurements["spans"]) > 10000:
        raise ValueError("Use a bounded span list")
    spans, groups, totals = {}, {}, {key: 0 for key in measurements["expected_owners"]}
    complete, owners = True, set()
    for span in measurements["spans"]:
        fields(span, ("source", "run", "span", "owner", "amount", "complete", "exclusive", "overhead_complete", "evidence_ref"), ("kind",))
        identity = tuple(text(span[key]) for key in ("source", "run", "span"))
        if identity in spans:
            if spans[identity] != span:
                raise ValueError("Conflicting usage identity or charge owner")
            continue
        spans[identity] = span
        if span["owner"] not in totals:
            raise ValueError("Unknown usage owner")
        evidence(span["evidence_ref"], wf, refs)
        for key in ("complete", "exclusive", "overhead_complete"):
            boolean(span[key])
        if span.get("kind", "total") not in ("total", "component"):
            raise ValueError("Unknown usage span kind")
        group = groups.setdefault(identity[:2], {"owner": span["owner"], "total": None})
        if group["owner"] != span["owner"]:
            raise ValueError("One usage run cannot have multiple charge owners")
        if span.get("kind", "total") == "total":
            if group["total"] is not None:
                raise ValueError("Multiple whole-task totals from the same source/run")
            group["total"] = span
    for group in groups.values():
        span = group["total"]
        if span is None:
            complete = False
            continue
        owners.add(span["owner"])
        if span["amount"] is not None:
            totals[span["owner"]] += number(span["amount"])
        complete = complete and span["amount"] is not None and all(span[key] for key in ("complete", "exclusive", "overhead_complete"))
    unknown["unit"] = measurements["unit"]
    if not complete or owners != set(totals):
        unknown["coverage"] = "incomplete"
        return unknown
    baseline, candidate, investment = (totals[key] for key in ("baseline", "candidate", "investment"))
    unknown.update(observed_spend=baseline + candidate + investment, experiment_investment=investment + (baseline + candidate if mode == "evaluation" else 0), coverage="complete")
    if not measurements["matched"] or not accepted:
        return unknown
    difference = baseline - candidate
    net = 0 if mode == "evaluation" else difference - investment
    unknown.update(operating_difference=difference, delivered_net_estimate=net,
                   net_percent=100 * net / baseline if baseline and mode != "evaluation" else None,
                   savings_claim="paired operating comparison only" if mode == "evaluation" else "baseline-referenced estimate; no subscription or causal savings claim")
    return unknown


def report(root, request, wf):
    fields(request, ("plan", "observation", "measurements"))
    refs = []
    saved = evidence(request["plan"], wf, refs, True)
    if not isinstance(saved, dict) or saved.get("operation") != "plan-delegation" or "plan_hash" not in saved:
        raise ValueError("Expected a saved delegation plan")
    plan_hash = saved.pop("plan_hash")
    if sha(canonical(saved)) != plan_hash:
        raise ValueError("Saved plan changed; preserve the original attempt")
    if saved.get("project_root") != str(root):
        raise ValueError("Plan root does not match the selected project root")
    for reference in saved["evidence"]:
        if sha(evidence(reference["path"], wf, refs)) != reference["sha256"]:
            raise ValueError("Plan evidence changed; reconcile without overwriting the attempt")
    observation = request["observation"]
    fields(observation, ("candidate_id", "worker_id", "model", "effort", "provider", "permissions", "coordinator_after",
                         "outcome", "rescued", "evidence_ref", "checks_ref"))
    for key in ("candidate_id", "worker_id"):
        text(observation[key])
    boolean(observation["rescued"])
    settings(observation["coordinator_after"])
    if observation["outcome"] not in ("accepted", "failed", "denied", "canceled", "uncertain"):
        raise ValueError("Unknown observed outcome")
    for key in ("evidence_ref", "checks_ref"):
        evidence(observation[key], wf, refs)
    chosen = saved["decision"]
    if chosen["route"] not in ("native", "local"):
        raise ValueError("No selected worker exists in this plan")
    failures = []
    if any(observation[key] != chosen[key] for key in ("candidate_id", "model", "effort", "provider")):
        failures.append("Requested and observed worker settings differ or are unknown")
    if observation["coordinator_after"] != saved["coordinator"]:
        failures.append("Coordinator settings changed or are unknown")
    if observation["permissions"] != saved["coordinator"]["permissions"]:
        failures.append("Worker permissions differ or are unknown")
    accepted = not failures and observation["outcome"] == "accepted" and not observation["rescued"]
    return wf["result"]("report-delegation", "blocked" if failures else "ok", "observation_only",
        task_id=saved["task_id"], mode=saved["mode"], plan_hash=plan_hash, evidence=refs,
        candidate_accepted=accepted, delivered=observation["outcome"] == "accepted", rescued=observation["rescued"],
        routing_failures=failures, accounting=accounting(request["measurements"], saved["mode"], not failures and observation["outcome"] == "accepted", wf, refs),
        next_action="Stop/reconcile the worker and partial effects before replacement" if failures else "Coordinator independently verifies integration; qualification is unchanged",
        limits=["External observations are not host attestation", "Complete authoritative whole-task totals take precedence over components from the same source/run; components alone leave usage unknown", "No automatic qualification promotion or repeatable-savings certification"])


def handle(operation, root, request, workflow):
    canonical(request)
    root = workflow["canonical"](Path(root))
    if not root.is_dir():
        raise ValueError("Select an existing project root")
    if operation == "plan-delegation":
        return plan(root, request, workflow)
    if operation == "report-delegation":
        return report(root, request, workflow)
    raise ValueError("Unknown delegation policy operation")
