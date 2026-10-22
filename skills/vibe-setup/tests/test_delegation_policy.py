"""Difficulty routing and complete-cost accounting use recorded observations, no models."""
import copy
import hashlib
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parents[1]


class DelegationPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.root = self.home / "project"
        (self.root / ".codex").mkdir(parents=True)
        self.wf = runpy.run_path(str(PACKAGE / "workflow.py"))
        module = PACKAGE / "delegation_policy.py"
        self.handle = runpy.run_path(str(module))["handle"] if module.exists() else None
        self.future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        self.receipt = self.save("receipt", {"observation": "Fixture observation; not live qualification"})
        self.policy(True)
        self.request = {
            "task": {"task_id": "task-1", "role": "Builder", "specialty": "Implementation",
                "domain": "parsing", "language": "python",
                "dimensions": {key: {"rating": 1, "reason": "One bounded contract"}
                               for key in ("reasoning", "ambiguity", "coupling", "context")},
                "risk": "R1", "checks": ["Run isolated parser tests"], "independent_review": True,
                "delegation_reason": "Independent bounded implementation", "context_tokens": 2000,
                "output_tokens": 1000, "tools": ["python"], "source_ref": self.receipt,
                "contract_ref": self.receipt, "checks_ref": self.receipt},
            "coordinator": {"model": "parent", "effort": "high", "provider": "existing",
                            "permissions": "workspace", "session_id": "parent-session"},
            "client": {"name": "app", "version": "1", "tool": "collaboration.spawn_agent",
                "pairs": [{"model": "small", "effort": "medium"}], "selection_supported": True,
                "observation_supported": True, "evidence_ref": self.receipt},
            "budget": {"attempt_limit": 2, "deadline": self.future, "output_tokens": 1000},
            "attempts": [], "mode": "ordinary", "candidates": []}
        self.request["candidates"] = [self.candidate("native", "native"), self.candidate("local", "local")]

    def save(self, name, value):
        path = self.home / (name + ".json")
        path.write_text(json.dumps(value))
        return str(path)

    def policy(self, enabled):
        (self.root / ".codex/vibe-workflow.toml").write_text(
            "schema_version = 1\n[task_lifecycle]\nenabled = false\n[worker_selection]\n"
            f"enabled = {'true' if enabled else 'false'}\nauthorization_ref = {json.dumps(self.receipt)}\n")

    def candidate(self, name, route):
        binding = {"route": route, "model": "small", "effort": "medium", "provider": "existing",
                   "version": "v1", "client": "app", "client_version": "1", "tool": "collaboration.spawn_agent"}
        scope = {key: self.request["task"][key] for key in ("role", "specialty", "domain", "language")}
        scope.update(tiers=[0, 1], risks=["R0", "R1"], context_tokens=8000, output_tokens=2000, tools=["python"])
        qualification = {"state": "qualified", "binding": binding, "scope": scope,
            "expires_at": self.future, "review_ref": self.receipt,
            "pilot": [{"case_id": f"{kind}-{n}", "case_hash": hashlib.sha256(f"{kind}-{n}".encode()).hexdigest(),
                       "category": kind, "baseline": "passed", "candidate": "passed",
                       "rescued": False, "critical_failure": False, "evidence_ref": self.receipt}
                      for kind in ("ordinary", "boundary", "failure") for n in range(4)],
            "canary": [{"task_id": f"canary-{n}", "outcome": "accepted", "rescued": False,
                        "critical_failure": False, "evidence_ref": self.receipt} for n in range(10)]}
        result = {"id": name, "route": route, "model": "small", "effort": "medium", "provider": "existing",
                  "version": "v1", "authorization_ref": self.receipt, "qualification_ref": self.save(name + "-q", qualification),
                  "tools": ["python"], "context_limit": 8000, "output_limit": 2000}
        if route == "local":
            qualification["binding"]["runtime_digest"] = "a" * 64
            qualification["binding"]["permissions"] = "workspace"
            self.save(name + "-q", qualification)
            result["local_status_ref"] = self.save(name + "-status", {"routing_enabled": True, "approved": True,
                "assessment_passed": True, "admitted": True, "expires_at": self.future,
                "runtime_digest": "a" * 64, "approval_ref": self.receipt, "assessment_ref": self.receipt,
                "admission_ref": self.receipt, "evaluation_path": False, "permissions": "workspace"})
        return result

    def call(self, operation="plan-delegation", request=None):
        self.assertIsNotNone(self.handle, "Difficulty policy helper not implemented")
        return self.handle(operation, self.root, request or self.request, self.wf)

    def edit_evidence(self, path, change):
        value = json.loads(Path(path).read_text())
        change(value)
        Path(path).write_text(json.dumps(value))

    def test_qualified_local_wins_without_cost_data_and_does_not_mutate_settings(self):
        before = copy.deepcopy(self.request)
        result = self.call()
        self.assertEqual(result["decision"]["route"], "local")
        self.assertEqual(result["decision"]["candidate_id"], "local")
        self.assertEqual(result["ranking"], "provisional")
        self.assertEqual(self.request, before)
        self.assertEqual(result["coordinator"], before["coordinator"])

    def test_disabled_or_absent_policy_preserves_inheritance(self):
        for present in (True, False):
            self.policy(False)
            if not present:
                (self.root / ".codex/vibe-workflow.toml").unlink()
            self.assertEqual(self.call()["decision"]["route"], "inherited")

    def test_max_dimension_and_risk_floor_prevent_toy_qualification(self):
        self.request["task"]["dimensions"]["ambiguity"]["rating"] = 3
        result = self.call()
        self.assertEqual(result["difficulty"], 3)
        self.assertEqual(result["decision"]["route"], "inherited")
        self.request["task"]["dimensions"]["ambiguity"]["rating"] = 0
        self.request["task"]["risk"] = "R2"
        self.assertEqual(self.call()["difficulty"], 2)
        self.request["task"]["independent_review"] = False
        self.assertEqual(self.call()["decision"]["route"], "coordinator")

    def test_local_capacity_and_scope_failures_choose_exact_native_pair(self):
        self.edit_evidence(self.request["candidates"][1]["local_status_ref"], lambda x: x.update(admitted=False))
        result = self.call()
        self.assertEqual(result["decision"]["route"], "native")
        self.assertEqual(result["decision"]["overrides"], {"model": "small", "reasoning_effort": "medium", "fork_turns": "none"})
        self.assertTrue(any("admission" in row["reason"] for row in result["rejections"]))
        self.request["client"]["pairs"][0]["effort"] = "low"
        self.assertEqual(self.call()["decision"]["route"], "inherited")

    def test_unsupported_selection_keeps_inheritance(self):
        self.request["client"]["observation_supported"] = False
        self.request["candidates"] = self.request["candidates"][:1]
        self.assertEqual(self.call()["decision"]["route"], "inherited")

    def test_failed_stale_rescued_and_mismatched_evidence_never_qualifies(self):
        self.request["candidates"] = self.request["candidates"][:1]
        path = self.request["candidates"][0]["qualification_ref"]
        initial = Path(path).read_text()
        changes = [lambda q: q.update(expires_at="2000-01-01T00:00:00+00:00"),
                   lambda q: q["canary"][0].update(rescued=True),
                   lambda q: q["pilot"][0].update(baseline="failed"),
                   lambda q: q["binding"].update(effort="low"),
                   lambda q: q["scope"].update(specialty="Security"),
                   lambda q: q["pilot"].append(dict(q["pilot"][0]))]
        for change in changes:
            Path(path).write_text(initial)
            self.edit_evidence(path, change)
            self.assertEqual(self.call()["decision"]["route"], "inherited")

    def test_cold_start_needs_bounded_evaluation_authority(self):
        self.request["candidates"] = self.request["candidates"][:1]
        self.edit_evidence(self.request["candidates"][0]["qualification_ref"],
                           lambda q: q.update(state="not_assessed", pilot=[], canary=[]))
        self.assertEqual(self.call()["decision"]["route"], "inherited")
        self.request["mode"] = "evaluation"
        self.request["manifest"] = self.save("evaluation", {"mode": "evaluation", "candidate_bindings": {
            "native": json.loads(Path(self.request["candidates"][0]["qualification_ref"]).read_text())["binding"]},
            "authorization_ref": self.receipt, "expires_at": self.future, "max_calls": 1, "used_calls": 0,
            "scope": json.loads(Path(self.request["candidates"][0]["qualification_ref"]).read_text())["scope"],
            "case_refs": [self.receipt], "rubric_ref": self.receipt, "stop_conditions": ["Stop after one call"],
            "disposable": True})
        self.assertEqual(self.call()["decision"]["route"], "native")
        self.edit_evidence(self.request["manifest"], lambda m: m.update(used_calls=1))
        self.assertEqual(self.call()["decision"]["route"], "inherited")

    def test_unknown_worker_or_exhausted_attempts_never_dispatches_again(self):
        self.request["attempts"] = [{"attempt_id": "first", "state": "uncertain", "request_hash": "a" * 64}]
        self.assertEqual(self.call()["decision"]["route"], "coordinator")
        self.request["attempts"][0]["state"] = "denied"
        self.request["attempts"].append({"attempt_id": "second", "state": "failed", "request_hash": "b" * 64})
        self.assertEqual(self.call()["decision"]["route"], "coordinator")

    def test_invalid_input_fails_closed(self):
        for change in (lambda r: r.update(unexpected=True),
                       lambda r: r["budget"].update(attempt_limit=True),
                       lambda r: r["task"]["dimensions"]["reasoning"].update(rating=True),
                       lambda r: r["candidates"].append(copy.deepcopy(r["candidates"][0]))):
            request = copy.deepcopy(self.request)
            change(request)
            with self.assertRaises(ValueError):
                self.call(request=request)

    def report_request(self):
        plan = self.call()
        return {"plan": self.save("plan", plan), "observation": {"candidate_id": "local", "worker_id": "job-1",
            "model": "small", "effort": "medium", "provider": "existing", "permissions": "workspace",
            "coordinator_after": copy.deepcopy(self.request["coordinator"]), "outcome": "accepted", "rescued": False,
            "evidence_ref": self.receipt, "checks_ref": self.receipt}, "measurements": None}

    def test_observed_mismatch_and_coordinator_drift_are_routing_failures(self):
        request = self.report_request()
        request["observation"]["model"] = "different"
        result = self.call("report-delegation", request)
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["candidate_accepted"])
        request["observation"]["model"] = "small"
        request["observation"]["coordinator_after"]["effort"] = "low"
        self.assertEqual(self.call("report-delegation", request)["status"], "blocked")

    def test_rescue_not_local_acceptance_and_missing_usage_unknown(self):
        request = self.report_request()
        request["observation"]["rescued"] = True
        result = self.call("report-delegation", request)
        self.assertFalse(result["candidate_accepted"])
        self.assertIsNone(result["accounting"]["operating_difference"])

    def test_local_permissions_bind_approved_scope_without_inheriting_coordinator_access(self):
        local = self.request["candidates"][1]
        permissions = {"execution": "proposal_only", "host_tools": []}
        self.edit_evidence(local["local_status_ref"], lambda s: s.update(permissions=permissions))
        self.edit_evidence(local["qualification_ref"], lambda q: q["binding"].update(permissions=permissions))
        request = self.report_request()
        request["observation"]["permissions"] = permissions
        result = self.call("report-delegation", request)
        self.assertTrue(result["candidate_accepted"])
        request["observation"]["permissions"] = "workspace"
        self.assertEqual(self.call("report-delegation", request)["status"], "blocked")
        self.edit_evidence(local["local_status_ref"], lambda s: s.update(permissions="workspace"))
        self.assertEqual(self.call()["decision"]["route"], "native")

    def measurements(self):
        def span(name, owner, amount):
            return {"source": "host", "run": name, "span": "total", "owner": owner, "amount": amount,
                    "complete": True, "exclusive": True, "overhead_complete": True,
                    "evidence_ref": self.receipt}
        return {"unit": "token_proxy", "matched": True, "match_ref": self.receipt,
                "expected_owners": ["baseline", "candidate", "investment"],
                "spans": [span("b", "baseline", 100), span("c", "candidate", 60), span("i", "investment", 10)]}

    def test_evaluation_counts_both_arms_as_investment_not_production_savings(self):
        self.request["mode"] = "evaluation"
        self.request["manifest"] = self.save("evaluation", {"mode": "evaluation", "candidate_bindings": {
            "local": json.loads(Path(self.request["candidates"][1]["qualification_ref"]).read_text())["binding"]},
            "authorization_ref": self.receipt, "expires_at": self.future, "max_calls": 1, "used_calls": 0,
            "scope": json.loads(Path(self.request["candidates"][1]["qualification_ref"]).read_text())["scope"],
            "case_refs": [self.receipt], "rubric_ref": self.receipt, "stop_conditions": ["Stop after one call"],
            "disposable": True})
        self.edit_evidence(self.request["candidates"][1]["local_status_ref"], lambda x: x.update(evaluation_path=True))
        request = self.report_request()
        request["measurements"] = self.measurements()
        result = self.call("report-delegation", request)
        self.assertEqual(result["accounting"]["operating_difference"], 40)
        self.assertEqual(result["accounting"]["experiment_investment"], 170)
        self.assertEqual(result["accounting"]["delivered_net_estimate"], 0)

    def test_delivered_estimate_subtracts_investment_and_preserves_negative_values(self):
        request = self.report_request()
        request["measurements"] = self.measurements()
        request["measurements"]["spans"][2]["amount"] = 50
        result = self.call("report-delegation", request)
        self.assertEqual(result["accounting"]["delivered_net_estimate"], -10)
        self.assertEqual(result["accounting"]["net_percent"], -10)

    def test_duplicate_conflicting_spans_rejected_and_incomplete_usage_unknown(self):
        request = self.report_request()
        request["measurements"] = self.measurements()
        request["measurements"]["spans"].append(copy.deepcopy(request["measurements"]["spans"][0]))
        self.assertEqual(self.call("report-delegation", request)["accounting"]["observed_spend"], 170)
        request["measurements"]["spans"][-1]["owner"] = "investment"
        with self.assertRaises(ValueError):
            self.call("report-delegation", request)
        request["measurements"] = self.measurements()
        request["measurements"]["spans"][0]["complete"] = False
        self.assertIsNone(self.call("report-delegation", request)["accounting"]["operating_difference"])

    def test_public_cli_plans_without_changing_policy_and_rejects_unknown_input(self):
        command = [sys.executable, "-B", str(PACKAGE / "workflow.py"), "plan-delegation", str(self.root)]
        policy = (self.root / ".codex/vibe-workflow.toml").read_bytes()
        result = subprocess.run(command, input=json.dumps(self.request), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(json.loads(result.stdout)["decision"]["route"], "local")
        self.assertEqual((self.root / ".codex/vibe-workflow.toml").read_bytes(), policy)
        result = subprocess.run(command, input=json.dumps({**self.request, "enable_routing": True}), text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)

    def test_plan_tampering_and_changed_evidence_require_reconciliation(self):
        request = self.report_request()
        self.edit_evidence(request["plan"], lambda p: p.update(mode="evaluation"))
        with self.assertRaisesRegex(ValueError, "Saved plan changed"):
            self.call("report-delegation", request)
        request = self.report_request()
        Path(self.receipt).write_text("New snapshot")
        with self.assertRaisesRegex(ValueError, "evidence changed"):
            self.call("report-delegation", request)

    def test_whole_task_total_supersedes_components_and_never_double_counts(self):
        request = self.report_request()
        request["measurements"] = self.measurements()
        component = dict(request["measurements"]["spans"][0], span="worker", kind="component", amount=80)
        request["measurements"]["spans"].append(component)
        self.assertEqual(self.call("report-delegation", request)["accounting"]["operating_difference"], 40)
        request["measurements"]["spans"] = [component, *request["measurements"]["spans"][1:3]]
        self.assertIsNone(self.call("report-delegation", request)["accounting"]["operating_difference"])

    def test_deadline_and_evidenced_harm_can_override_local_preference(self):
        local = self.request["candidates"][1]
        local["expected_seconds"] = 1000000
        local["timing_ref"] = self.receipt
        self.assertEqual(self.call()["decision"]["route"], "native")
        del local["expected_seconds"]
        local["avoid_local_ref"] = self.save("harm", {"reason": "measured_harm", "qualification_ref": local["qualification_ref"],
            "evidence_ref": self.receipt, "expires_at": self.future})
        self.assertEqual(self.call()["decision"]["route"], "native")

    def test_canary_needs_clean_pilot_and_cannot_hide_failed_deliveries(self):
        self.request["candidates"] = self.request["candidates"][:1]
        candidate = self.request["candidates"][0]
        self.edit_evidence(candidate["qualification_ref"], lambda q: q.update(state="pilot_only", canary=[]))
        self.request["mode"] = "canary"
        self.request["manifest"] = self.save("canary", {"mode": "canary", "candidate_bindings": {
            "native": json.loads(Path(candidate["qualification_ref"]).read_text())["binding"]},
            "authorization_ref": self.receipt, "expires_at": self.future, "max_calls": 10, "used_calls": 0,
            "scope": json.loads(Path(candidate["qualification_ref"]).read_text())["scope"],
            "case_refs": [self.receipt], "rubric_ref": self.receipt, "stop_conditions": ["Stop on failure"], "disposable": True})
        self.assertEqual(self.call()["decision"]["route"], "native")
        self.edit_evidence(candidate["qualification_ref"], lambda q: q["canary"].append(
            {"task_id": "bad", "outcome": "failed", "rescued": False, "critical_failure": False, "evidence_ref": self.receipt}))
        self.assertEqual(self.call()["decision"]["route"], "inherited")

    def test_authorization_uri_does_not_require_a_machine_specific_policy_path(self):
        (self.root / ".codex/vibe-workflow.toml").write_text(
            '[worker_selection]\nenabled = true\nauthorization_ref = "codex://threads/approved-task"\n')
        self.assertEqual(self.call()["decision"]["route"], "local")

    def test_local_rescue_can_deliver_but_never_qualifies_original_candidate(self):
        request = self.report_request()
        request["observation"]["rescued"] = True
        request["measurements"] = self.measurements()
        result = self.call("report-delegation", request)
        self.assertFalse(result["candidate_accepted"])
        self.assertTrue(result["delivered"])
        self.assertEqual(result["accounting"]["operating_difference"], 40)

    def test_multiple_totals_from_the_same_run_cannot_inflate_cost(self):
        request = self.report_request()
        request["measurements"] = self.measurements()
        request["measurements"]["spans"].append(dict(request["measurements"]["spans"][0], span="another-total"))
        with self.assertRaisesRegex(ValueError, "total"):
            self.call("report-delegation", request)

    def test_identical_failed_dispatch_cannot_replay_and_root_is_bound(self):
        plan = self.call()
        self.request["attempts"] = [{"attempt_id": "first", "state": "failed", "request_hash": plan["decision"]["request_hash"]}]
        self.request["recovery"] = {"diagnosis": "Incomplete output", "changed_variable": "model", "reason": "Escalate once"}
        result = self.call()
        self.assertEqual(result["decision"]["route"], "native")
        self.request["attempts"] = []
        request = self.report_request()
        other_root = self.home / "other"
        other_root.mkdir()
        with self.assertRaisesRegex(ValueError, "root"):
            self.handle("report-delegation", other_root, request, self.wf)

    def test_repeated_case_input_and_malformed_canary_never_qualify(self):
        self.request["candidates"] = self.request["candidates"][:1]
        path = self.request["candidates"][0]["qualification_ref"]
        self.edit_evidence(path, lambda q: q["pilot"][1].update(case_hash=q["pilot"][0]["case_hash"]))
        self.assertEqual(self.call()["decision"]["route"], "inherited")
        self.edit_evidence(path, lambda q: q.update(canary=None))
        self.assertEqual(self.call()["decision"]["route"], "inherited")

    def test_expired_naive_and_over_budget_requests_do_not_dispatch(self):
        self.request["budget"]["deadline"] = "2000-01-01T00:00:00Z"
        self.assertEqual(self.call()["decision"]["route"], "coordinator")
        self.request["budget"]["deadline"] = "2099-01-01T00:00:00"
        with self.assertRaises(ValueError):
            self.call()
        self.request["budget"]["deadline"] = self.future
        self.request["budget"]["output_tokens"] = 500
        self.assertEqual(self.call()["decision"]["route"], "coordinator")

    def test_suspended_candidate_needs_new_reassessment_and_local_plugin_gate(self):
        self.request["mode"] = "evaluation"
        self.request["candidates"] = self.request["candidates"][1:]
        local = self.request["candidates"][0]
        self.edit_evidence(local["qualification_ref"], lambda q: q.update(state="suspended"))
        self.request["manifest"] = self.save("reassessment", {"mode": "evaluation", "candidate_bindings": {
            "local": json.loads(Path(local["qualification_ref"]).read_text())["binding"]},
            "authorization_ref": self.receipt, "expires_at": self.future, "max_calls": 1, "used_calls": 0,
            "scope": json.loads(Path(local["qualification_ref"]).read_text())["scope"], "case_refs": [self.receipt],
            "rubric_ref": self.receipt, "stop_conditions": ["Stop after one call"], "disposable": True})
        self.assertEqual(self.call()["decision"]["route"], "inherited")
        self.edit_evidence(local["local_status_ref"], lambda s: s.update(evaluation_path=True))
        self.assertEqual(self.call()["decision"]["route"], "inherited")
        self.edit_evidence(self.request["manifest"], lambda m: m.update(diagnosis_ref=self.receipt))
        self.assertEqual(self.call()["decision"]["route"], "local")

    def test_missing_owners_zero_baseline_and_failed_delivery_never_claim_positive_savings(self):
        request = self.report_request()
        request["measurements"] = self.measurements()
        request["measurements"]["spans"][0]["amount"] = 0
        result = self.call("report-delegation", request)
        self.assertEqual(result["accounting"]["delivered_net_estimate"], -70)
        self.assertIsNone(result["accounting"]["net_percent"])
        request["observation"]["outcome"] = "failed"
        self.assertIsNone(self.call("report-delegation", request)["accounting"]["delivered_net_estimate"])
        request["measurements"]["spans"].pop()
        self.assertIsNone(self.call("report-delegation", request)["accounting"]["operating_difference"])

    def test_missing_candidate_fields_reject_route_without_crashing(self):
        for candidate in self.request["candidates"]:
            del candidate["effort"]
        result = self.call()
        self.assertEqual(result["decision"]["route"], "inherited")
        self.assertEqual(len(result["rejections"]), 2)

    def test_unknown_role_is_rejected_before_selection(self):
        self.request["task"]["role"] = "InventedRole"
        with self.assertRaisesRegex(ValueError, "role"):
            self.call()

    def test_evaluation_and_canary_manifest_reject_model_or_effort_substitution(self):
        self.request["candidates"] = self.request["candidates"][:1]
        candidate = self.request["candidates"][0]
        self.edit_evidence(candidate["qualification_ref"], lambda q: q.update(state="pilot_only", canary=[]))
        original = copy.deepcopy(candidate)
        qualification = json.loads(Path(candidate["qualification_ref"]).read_text())
        for mode in ("evaluation", "canary"):
            with self.subTest(mode=mode):
                self.request["mode"] = mode
                self.request["manifest"] = self.save("fixed-manifest", {"mode": mode, "candidate_bindings": {"native": qualification["binding"]},
                    "authorization_ref": self.receipt, "expires_at": self.future, "max_calls": 1, "used_calls": 0,
                    "scope": qualification["scope"], "case_refs": [self.receipt], "rubric_ref": self.receipt,
                    "stop_conditions": ["Stop after one call"], "disposable": True})
                self.assertEqual(self.call()["decision"]["route"], "native")
                for field, replacement in (("model", "other-model"), ("effort", "low")):
                    with self.subTest(mode=mode, field=field):
                        candidate[field] = replacement
                        self.edit_evidence(candidate["qualification_ref"], lambda q: q["binding"].update({field: replacement}))
                        self.request["client"]["pairs"] = [{"model": candidate["model"], "effort": candidate["effort"]}]
                        self.assertEqual(self.call()["decision"]["route"], "inherited")
                        candidate.update(original)
                        Path(candidate["qualification_ref"]).write_text(json.dumps(qualification))
                        self.request["client"]["pairs"] = [{"model": "small", "effort": "medium"}]

    def test_local_manifest_freezes_runtime_and_route_identity(self):
        self.request["candidates"] = self.request["candidates"][1:]
        candidate = self.request["candidates"][0]
        self.edit_evidence(candidate["qualification_ref"], lambda q: q.update(state="pilot_only", canary=[]))
        self.edit_evidence(candidate["local_status_ref"], lambda s: s.update(evaluation_path=True))
        original = copy.deepcopy(candidate)
        qualification = json.loads(Path(candidate["qualification_ref"]).read_text())
        status = json.loads(Path(candidate["local_status_ref"]).read_text())
        for mode in ("evaluation", "canary"):
            self.request["mode"] = mode
            self.request["manifest"] = self.save("local-manifest", {"mode": mode,
                "candidate_bindings": {"local": qualification["binding"]}, "authorization_ref": self.receipt,
                "expires_at": self.future, "max_calls": 1, "used_calls": 0, "scope": qualification["scope"],
                "case_refs": [self.receipt], "rubric_ref": self.receipt, "stop_conditions": ["Stop after one call"], "disposable": True})
            self.assertEqual(self.call()["decision"]["route"], "local")
            for field, replacement in (("runtime_digest", "b" * 64), ("permissions", "expanded-scope"), ("version", "v2"),
                                       ("provider", "another-local-runtime"), ("route", "native")):
                with self.subTest(mode=mode, field=field):
                    changed = copy.deepcopy(qualification)
                    changed["binding"][field] = replacement
                    if field in ("runtime_digest", "permissions"):
                        self.edit_evidence(candidate["local_status_ref"], lambda s: s.update({field: replacement}))
                    else:
                        candidate[field] = replacement
                    if field == "route":
                        changed["binding"].pop("runtime_digest")
                        changed["binding"].pop("permissions")
                    Path(candidate["qualification_ref"]).write_text(json.dumps(changed))
                    self.assertEqual(self.call()["decision"]["route"], "inherited")
                    candidate.update(original)
                    Path(candidate["qualification_ref"]).write_text(json.dumps(qualification))
                    Path(candidate["local_status_ref"]).write_text(json.dumps(status))


if __name__ == "__main__":
    unittest.main()
