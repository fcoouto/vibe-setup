"""Security gates use private, current evidence without running third-party tools."""
import copy
import contextlib
import io
import json
import hashlib
from pathlib import Path
from unittest.mock import patch

from test_workflow_lifecycle import PublicationFixture
from test_workflow_setup import WorkflowFixture


def coverage_proof(snapshot, proof, files=("app.txt",)):
    path = Path(proof["path"]).with_name("coverage.json")
    record = {"schema_version": 1, "snapshot": snapshot, "files": list(files),
              "areas": {name: {"status": "covered", "summary": "Fixture boundary inspected.",
                                "evidence": [proof]}
                        for name in ("scope", "methods", "history", "callers", "tests", "adversarial", "execution")}}
    path.write_text(json.dumps(record))
    return {"name": "security-coverage", "outcome": "passed", "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def security_record(snapshot, proof, risk="R0"):
    names = ["impact-review", "trailofbits-update-review"]
    if risk in ("R1", "R2"):
        names.append("security-validation")
    if risk == "R2":
        names.append("independent-security-review")
    record = {"snapshot": snapshot, "risk": risk, "rationale": "Private scope and risk assessment.",
            "status": "complete", "required_checks": names,
            "checks": [{**proof, "name": name} for name in names]}
    if risk in ("R1", "R2"):
        record["required_checks"].append("security-coverage")
        record["checks"].append(coverage_proof(snapshot, proof))
    return record


class SecurityPublicationTests(PublicationFixture):
    def secure_event(self, risk="R0", **kwargs):
        event = self.event(**kwargs)
        event["validation"]["security"] = security_record(
            event["snapshot"], event["validation"]["review"], risk)
        return event

    def rewrite_coverage(self, event, change):
        entry = next(c for c in event["validation"]["security"]["checks"] if c["name"] == "security-coverage")
        path = Path(entry["path"])
        record = json.loads(path.read_text())
        change(record)
        path.write_text(json.dumps(record))
        entry["sha256"] = self.workflow.fingerprint(path)["sha256"]

    def test_ready_rejects_assertion_only_security_coverage(self):
        event = self.secure_event("R2")
        security = event["validation"]["security"]
        security["required_checks"].remove("security-coverage")
        security["checks"] = [c for c in security["checks"] if c["name"] != "security-coverage"]
        self.assertEqual(self.sync(event)["status"], "blocked")
        self.assertEqual(self.calls, [])

    def test_coverage_requires_every_area_current_scope_and_concrete_evidence(self):
        changes = [
            lambda r: r.update(snapshot="0" * 64),
            lambda r: r.update(files=["another.py"]),
            lambda r: r.update(schema_version=True),
            lambda r: r.update(files=["app.txt", "app.txt"]),
            lambda r: r["areas"].pop("history"),
            lambda r: r["areas"]["callers"].update(status="not_run"),
            lambda r: r["areas"]["history"].update(summary=" "),
            lambda r: r["areas"]["history"].update(evidence=[]),
            lambda r: r["areas"]["tests"].update(status="not_applicable"),
            lambda r: r["areas"]["methods"].update(evidence=[{"claim": "passed"}]),
            lambda r: r["areas"]["tests"]["evidence"][0].update(outcome="not_run"),
        ]
        for change in changes:
            with self.subTest(change=changes.index(change)):
                event = self.secure_event("R2")
                self.rewrite_coverage(event, change)
                self.assertEqual(self.sync(event)["status"], "blocked")
        self.assertEqual(self.calls, [])

    def test_coverage_exclusions_need_inspected_scope_and_malformed_json_blocks(self):
        event = self.secure_event("R2")
        self.rewrite_coverage(event, lambda r: r["areas"]["history"].update(
            status="not_applicable", summary="New entrypoint; baseline has no prior implementation."))
        self.workflow.validate_event(event)
        entry = event["validation"]["security"]["checks"][-1]
        path = Path(entry["path"])
        valid = path.read_bytes()
        malformed = [b"not JSON", b"[" * 2000, valid + b" " * 65536,
                     valid.replace(b'"schema_version": 1', b'"schema_version": 1, "schema_version": 1')]
        for payload in malformed:
            with self.subTest(payload=payload[:20]):
                path.write_bytes(payload)
                entry["sha256"] = self.workflow.fingerprint(path)["sha256"]
                self.assertEqual(self.sync(event)["status"], "blocked")
        self.assertEqual(self.calls, [])

    def test_nested_coverage_evidence_is_rechecked_during_ready(self):
        event = self.secure_event("R2")
        nested = self.home / "history.log"
        nested.write_text("Baseline protection traced to its introducing commit.")
        proof = {"name": "history", "outcome": "passed", "path": str(nested),
                 "sha256": self.workflow.fingerprint(nested)["sha256"]}
        self.rewrite_coverage(event, lambda r: r["areas"]["history"].update(evidence=[proof]))
        original = self.api
        def mutate(publication, endpoint, method="GET", payload=None, paginate=False):
            result = original(publication, endpoint, method, payload, paginate)
            if endpoint == "graphql" and "markPullRequestReadyForReview" not in payload.get("query", ""):
                nested.write_text("History evidence changed after initial acceptance")
            return result
        with patch.object(self.workflow, "gh_api", side_effect=mutate):
            response = self.sync(event)
        self.assertEqual(response["status"], "blocked", response)
        self.assertTrue(self.prs[0]["title"].startswith("[BLOCKED]"))

    def test_legacy_ready_without_security_blocks_before_publication(self):
        event = self.event()
        event["validation"].pop("security", None)
        before = self.git(self.target, "rev-parse", "HEAD")
        self.assertEqual(self.sync(event)["status"], "blocked")
        self.assertEqual(self.git(self.target, "rev-parse", "HEAD"), before)
        self.assertEqual(self.calls, [])

    def test_ready_requires_update_review_even_when_both_lists_omit_it(self):
        event = self.secure_event()
        security = event["validation"]["security"]
        security["required_checks"].remove("trailofbits-update-review")
        security["checks"] = [item for item in security["checks"] if item["name"] != "trailofbits-update-review"]
        self.assertEqual(self.sync(event)["status"], "blocked")
        self.assertEqual(self.calls, [])

    def test_each_risk_level_accepts_its_complete_required_evidence(self):
        for risk in ("R0", "R1", "R2"):
            with self.subTest(risk=risk):
                self.workflow.validate_event(self.secure_event(risk))
        response = self.sync(self.secure_event("R2"))
        self.assertEqual(response["status"], "ok", response)
        self.assertTrue(self.prs[0]["title"].startswith("[READY]"))

    def test_invalid_or_incomplete_security_blocks_before_remote_calls(self):
        base = self.secure_event("R2")
        mutations = [
            {"snapshot": "0" * 64}, {"risk": "unknown"}, {"risk": []},
            {"status": "incomplete"}, {"status": "failed"}, {"rationale": " "},
            {"required_checks": []}, {"required_checks": ["impact-review"]},
            {"required_checks": ["impact-review"] * 2}, {"required_checks": [None]},
            {"checks": []}, {"unexpected": True},
        ]
        for changes in mutations:
            with self.subTest(changes=changes):
                event = copy.deepcopy(base)
                event["validation"]["security"].update(changes)
                self.assertEqual(self.sync(event)["status"], "blocked")
        for outcome in ("failed", "not_run", "incomplete"):
            event = copy.deepcopy(base)
            event["validation"]["security"]["checks"][-1]["outcome"] = outcome
            self.assertEqual(self.sync(event)["status"], "blocked")
        self.assertEqual(self.calls, [])

    def test_project_requirements_cannot_be_omitted_or_duplicated(self):
        event = self.secure_event("R1")
        security = event["validation"]["security"]
        security["required_checks"].append("dependency-audit")
        self.assertEqual(self.sync(event)["status"], "blocked")
        security["checks"].append({**security["checks"][0], "name": "dependency-audit"})
        self.workflow.validate_event(event)
        security["checks"].append(dict(security["checks"][0]))
        self.assertEqual(self.sync(event)["status"], "blocked")

    def test_security_evidence_changed_missing_or_source_changed_blocks(self):
        event = self.secure_event()
        proof = self.home / "security.log"
        proof.write_text("reviewed")
        entry = event["validation"]["security"]["checks"][0]
        entry.update(path=str(proof), sha256=self.workflow.fingerprint(proof)["sha256"])
        proof.write_text("changed")
        self.assertEqual(self.sync(event)["status"], "blocked")
        proof.unlink()
        self.assertEqual(self.sync(event)["status"], "blocked")
        proof.write_text("reviewed")
        (self.target / "app.txt").write_text("new unreviewed behavior")
        self.assertEqual(self.sync(event)["status"], "blocked")
        self.assertEqual(self.calls, [])

    def test_checkpoint_and_withdrawal_allow_missing_security(self):
        checkpoint = self.event(kind="checkpoint")
        checkpoint["validation"].pop("security", None)
        self.assertEqual(self.sync(checkpoint)["status"], "ok")
        self.assertTrue(self.prs[0]["title"].startswith("[BLOCKED]"))
        self.prs[0]["title"] = "[READY] Fixture feature"
        reopen = self.event(kind="reopen", milestone="phase-2")
        reopen["validation"]["security"] = {"stale": "withdrawal must remain possible"}
        self.assertEqual(self.sync(reopen)["status"], "ok")
        self.assertTrue(self.prs[0]["title"].startswith("[BLOCKED]"))

    def test_public_status_never_discloses_security_details(self):
        event = self.secure_event("R2")
        private = "private-vulnerability-do-not-publish"
        security = event["validation"]["security"]
        security["rationale"] = private
        security["required_checks"].append(private)
        security["checks"].append({**security["checks"][0], "name": private})
        self.assertEqual(self.sync(event)["status"], "ok")
        body = self.prs[0]["body"]
        self.assertIn("Security: passed (R2)", body)
        for value in (private, str(self.evidence), security["checks"][0]["sha256"]):
            self.assertNotIn(value, body)

    def test_resume_and_manual_confirmation_cannot_override_missing_security(self):
        event = self.secure_event()
        self.remote_failure = "access"
        self.assertEqual(self.sync(event)["status"], "action_required")
        binding, _ = self.workflow.setup_context(self.task)
        state = self.workflow.read_lifecycle(self.workflow.lifecycle_path(binding))
        del state["events"][event["event_id"]]["request"]["validation"]["security"]
        self.workflow.save_lifecycle(state)
        confirmation = {"actor": "Human", "head": self.git(self.target, "rev-parse", "HEAD"),
                        "pr_number": 1, "actions": ["publication", "metadata", "non_draft", "readiness"]}
        response = self.workflow.resume_operation(self.source, event["event_id"], confirmation, usage=self.usage)
        self.assertEqual(response["status"], "blocked", response)

    def check_midflight_mutation(self, path):
        event = self.secure_event()
        original = self.api
        def mutate(publication, endpoint, method="GET", payload=None, paginate=False):
            result = original(publication, endpoint, method, payload, paginate)
            if endpoint == "graphql" and "markPullRequestReadyForReview" not in payload.get("query", ""):
                path.write_text("Changed during readiness checks")
            return result
        with patch.object(self.workflow, "gh_api", side_effect=mutate):
            response = self.sync(event)
        self.assertEqual(response["status"], "blocked", response)
        self.assertTrue(self.prs[0]["title"].startswith("[BLOCKED]"))

    def test_source_changed_during_remote_checks_cannot_promote(self):
        self.check_midflight_mutation(self.target / "app.txt")

    def test_evidence_changed_during_remote_checks_cannot_promote(self):
        self.check_midflight_mutation(self.evidence)

    def test_omitted_file_created_during_remote_checks_cannot_promote(self):
        self.check_midflight_mutation(self.target / "unreviewed.py")

    def test_dirty_connected_file_omitted_from_scope_blocks_before_commit(self):
        guard = self.target / "guard.py"
        guard.write_text("allow = True\n")
        self.git(self.target, "add", "guard.py")
        self.git(self.target, "commit", "-qm", "baseline guard")
        guard.write_text("allow = False\n")
        event = self.secure_event("R2")
        head = self.git(self.target, "rev-parse", "HEAD")
        self.assertEqual(self.sync(event)["status"], "blocked")
        self.assertEqual(self.git(self.target, "rev-parse", "HEAD"), head)
        self.assertEqual(guard.read_text(), "allow = False\n")
        self.assertEqual(self.calls, [])

    def test_untracked_file_omitted_from_scope_blocks_before_commit(self):
        (self.target / "guard.py").write_text("allow = False\n")
        self.assertEqual(self.sync(self.secure_event("R2"))["status"], "blocked")
        self.assertEqual(self.calls, [])

    def check_reconciliation_mutation(self, path):
        event = self.secure_event("R2")
        self.assertEqual(self.sync(event)["status"], "ok")
        original = self.api
        def mutate(publication, endpoint, method="GET", payload=None, paginate=False):
            result = original(publication, endpoint, method, payload, paginate)
            if endpoint == "graphql":
                path.write_text("Changed during repeated readiness checks")
            return result
        with patch.object(self.workflow, "gh_api", side_effect=mutate):
            response = self.sync(event)
        self.assertEqual(response["status"], "blocked", response)
        self.assertTrue(self.prs[0]["title"].startswith("[BLOCKED]"))
        self.assertNotIn("Security: passed", self.prs[0]["body"])

    def test_reconciliation_revalidates_security_and_withdraws_stale_ready(self):
        self.check_reconciliation_mutation(self.evidence)

    def test_reconciliation_revalidates_source_and_withdraws_stale_ready(self):
        self.check_reconciliation_mutation(self.target / "app.txt")

    def test_manual_confirmation_revalidates_evidence_after_remote_failure(self):
        event = self.secure_event()
        self.remote_failure = "access"
        self.assertEqual(self.sync(event)["status"], "action_required")
        self.git(self.target, "add", "app.txt")
        self.git(self.target, "commit", "-qm", "manual reviewed commit")
        confirmation = {"actor": "Human", "head": self.git(self.target, "rev-parse", "HEAD"),
                        "pr_number": 1, "actions": ["publication", "metadata", "non_draft", "readiness"]}
        original = self.api
        def mutate(*args, **kwargs):
            self.evidence.write_text("Changed after initial validation")
            return original(*args, **kwargs)
        with patch.object(self.workflow, "gh_api", side_effect=mutate):
            response = self.workflow.resume_operation(self.source, event["event_id"], confirmation, usage=self.usage)
        self.assertEqual(response["status"], "blocked", response)
        self.assertNotEqual(response["delivery"], "user_confirmed")


class SecurityReleaseTests(WorkflowFixture):
    def cli(self, operation, request=None, *options):
        output = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(request))), contextlib.redirect_stdout(output):
            code = self.workflow.main([operation, str(self.source), *options])
        return code, json.loads(output.getvalue())

    def request_security(self):
        code, output = self.cli("inspect", None, "--file", "app.txt")
        self.assertEqual(code, 0, output)
        self.assertIn("publication_snapshot", output)
        snapshot = output["publication_snapshot"]["digest"]
        proof_path = self.home / "security.log"
        proof_path.write_text("Exact release scope reviewed; complete and passing.")
        proof = {"name": "impact-review", "outcome": "passed", "path": str(proof_path),
                 "sha256": self.workflow.fingerprint(proof_path)["sha256"]}
        return {"files": ["app.txt"], "snapshot": snapshot, "security": security_record(snapshot, proof)}

    def test_release_rejects_unsubstantiated_behavior_coverage(self):
        request = self.request_security()
        proof = request["security"]["checks"][0]
        request["security"] = security_record(request["snapshot"], proof, "R1")
        self.assertEqual(self.cli("check-security", request)[0], 0)
        record = Path(request["security"]["checks"][-1]["path"])
        record.write_text("All checks passed")
        request["security"]["checks"][-1]["sha256"] = self.workflow.fingerprint(record)["sha256"]
        self.assertEqual(self.cli("check-security", request)[0], 3)

    def test_release_gate_works_without_task_even_when_lifecycle_disabled(self):
        self.policy('[task_lifecycle]\nenabled = false\nauto_cleanup = false\n')
        self.git(self.source, "add", ".codex/vibe-workflow.toml")
        self.git(self.source, "commit", "-qm", "opt out")
        request = self.request_security()
        before = self.snapshot(self.source)
        code, output = self.cli("check-security", request)
        self.assertEqual(code, 0, output)
        self.assertEqual(output["security"], "passed")
        self.assertEqual(output["implementation"], "validation_only")
        self.assertEqual(before, self.snapshot(self.source))
        del request["security"]
        code, output = self.cli("check-security", request)
        self.assertEqual(code, 3, output)

    def test_release_rejects_stale_snapshot_and_unreviewed_checkout(self):
        request = self.request_security()
        (self.source / "app.txt").write_text("changed")
        code, _ = self.cli("check-security", request)
        self.assertEqual(code, 3)
        self.git(self.source, "add", "app.txt")
        self.git(self.source, "commit", "-qm", "new release")
        code, _ = self.cli("check-security", request)
        self.assertEqual(code, 3)
        request = self.request_security()
        (self.source / "omitted.py").write_text("unreviewed release input")
        code, _ = self.cli("check-security", request)
        self.assertEqual(code, 3)

    def test_release_requires_complete_passing_security(self):
        request = self.request_security()
        for change in ({"status": "incomplete"}, {"checks": []}, {"snapshot": "0" * 64}):
            bad = copy.deepcopy(request)
            bad["security"].update(change)
            code, _ = self.cli("check-security", bad)
            self.assertEqual(code, 3)
        request["security"]["checks"][0]["outcome"] = "failed"
        code, _ = self.cli("check-security", request)
        self.assertEqual(code, 3)

    def test_release_requires_current_passing_update_review(self):
        request = self.request_security()
        missing = copy.deepcopy(request)
        missing["security"]["required_checks"].remove("trailofbits-update-review")
        missing["security"]["checks"] = [item for item in missing["security"]["checks"]
                                            if item["name"] != "trailofbits-update-review"]
        self.assertEqual(self.cli("check-security", missing)[0], 3)
        for outcome in ("not_run", "failed"):
            bad = copy.deepcopy(request)
            bad["security"]["checks"][1]["outcome"] = outcome
            self.assertEqual(self.cli("check-security", bad)[0], 3)
        proof = self.home / "upstream-review.log"
        proof.write_text("Upstream comparison and applicability reviewed.")
        request["security"]["checks"][1].update(path=str(proof), sha256=self.workflow.fingerprint(proof)["sha256"])
        self.assertEqual(self.cli("check-security", request)[0], 0)
        proof.write_text("Changed review evidence")
        self.assertEqual(self.cli("check-security", request)[0], 3)
