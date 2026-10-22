"""Recoverable updates in disposable repositories; no native clients or accounts."""
import copy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4


PACKAGE = Path(__file__).resolve().parents[1]


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((PACKAGE / "update_workflow.py").is_file(), "Update transaction is not implemented")
        self.api = runpy.run_path(str(PACKAGE / "update_workflow.py"))
        self.workflow = runpy.run_path(str(PACKAGE / "workflow.py"))
        self.temp = tempfile.TemporaryDirectory(prefix="vibe-update-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        env = patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})
        env.start()
        self.addCleanup(env.stop)
        self.source = self.repo("source")
        self.candidate = self.source / "skills/vibe-setup"
        shutil.copytree(PACKAGE, self.candidate, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        self.installed = self.home / "installed"
        shutil.copytree(self.candidate, self.installed)
        self.installed_baseline = self.manifest(self.installed)
        self.project = self.repo("project")
        runpy.run_path(str(self.candidate / "install.py"))["install"](self.project)
        (self.project / ".codex/vibe-workflow.toml").write_text(
            "schema_version = 1\n[task_lifecycle]\nenabled = false\nauto_cleanup = false\n")
        self.baseline = {name: self.fp(self.project / name) for name in self.workflow["SETUP_FILES"]}
        self.git(self.project, "add", ".")
        self.git(self.project, "commit", "-qm", "installed fixture")
        (self.candidate / "delegation-brief.md").write_text("Updated delegation instructions.\n")
        (self.candidate / "README.md").write_text("Updated package documentation.\n")
        self.git(self.source, "add", ".")
        self.git(self.source, "commit", "-qm", "candidate")
        self.record = self.home / "records" / str(uuid4())
        self.native_settings = {"model": "fixture-inherited", "effort": "xhigh", "provider": "openai",
                                "approval_policy": "never", "sandbox_policy": {"type": "danger-full-access"},
                                "permission_profile": None, "active_permission_profile": None}
        self.context = {"runtime": "fixture-app-1", "session": "native-session-1",
                        "hook_source": str(self.project / ".codex/hooks.json"),
                        "settings_sha256": hashlib.sha256(json.dumps(self.native_settings, sort_keys=True,
                                                                      separators=(",", ":")).encode()).hexdigest()}
        self.request = {"operation_id": self.record.name, "record_dir": str(self.record),
                        "candidate_dir": str(self.candidate),
                        "revision": self.git(self.source, "rev-parse", "HEAD"),
                        "installed": {"root": str(self.installed), "baseline": self.installed_baseline},
                        "targets": [{"root": str(self.project), "kind": "project", "baseline": self.baseline,
                                     "clients": {"app": self.context}, "task": None,
                                     "activation_revision": None, "exclusions": []}],
                        "authorizations": [{"action": "install", "roots": [str(self.installed)],
                                            "provenance": "Explicit fixture update request", "constraints": []},
                                           {"action": "adopt", "roots": [str(self.project)],
                                            "provenance": "Explicit fixture adoption request", "constraints": []}],
                        "requirements": [{"root": str(self.project), "layer": "execution", "client": "app"}]}

    def git(self, root, *args):
        return subprocess.run(["git", "-C", str(root), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def repo(self, name):
        root = self.home / name
        root.mkdir()
        self.git(root, "init", "-q", "-b", "main")
        self.git(root, "config", "user.name", "Fixture")
        self.git(root, "config", "user.email", "fixture@example.invalid")
        (root / "app.txt").write_text("Existing application\n")
        self.git(root, "add", ".")
        self.git(root, "commit", "-qm", "baseline")
        return root

    def fp(self, path):
        if not path.exists():
            return None
        return {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "mode": path.stat().st_mode & 0o7777}

    def manifest(self, root):
        return {str(p.relative_to(root)): self.fp(p) for p in root.rglob("*") if p.is_file()}

    def call(self, operation, request=None, workflow=None):
        return self.api["handle"](operation, self.source, request or {"record_dir": str(self.record)},
                                  workflow or self.workflow)

    def row(self, result, layer="execution", client="app", root=None):
        return next(row for row in result["outcomes"] if row["layer"] == layer and row["client"] == client
                    and row["root"] == str(root or self.project))

    def native_receipt(self, root, client):
        """Build complete deterministic native event fixtures through the real evaluator."""
        root = Path(root)
        fixture = self.home / f"native-{uuid4()}"
        fixture.mkdir()
        parent, child = fixture / "parent.jsonl", fixture / "child.jsonl"
        observation, record = fixture / "context.json", fixture / "probe.json"
        dispatch, display, snapshot = fixture / "dispatch.json", fixture / "display.json", fixture / "snapshot.txt"
        name = "update_canary_" + uuid4().hex
        declaration = root / ".codex-delegations" / f"{name}.json"
        declaration.parent.mkdir(exist_ok=True)
        declaration.write_text(json.dumps({"role": "Tester", "specialty": "Fixture qualification",
            "objective": "Read only", "context": str(root), "instructions": "Read declaration and app.txt.",
            "allowed_files": [], "mutable_resources": [], "dependencies": [], "acceptance": ["Read only"],
            "checks": ["Read declaration and app.txt"], "read_only": True, "budget": {"minutes": 3, "attempts": 1}}))
        def append(file, kind, payload):
            with file.open("a") as stream:
                stream.write(json.dumps({"type": kind, "payload": payload}) + "\n")
        turn, child_id = str(uuid4()), str(uuid4())
        settings = {key: value for key, value in self.native_settings.items() if key != "provider"}
        settings.update(turn_id=turn, root_turn_id=turn, cwd=str(root))
        originator = "codex_work_desktop" if client == "app" else "codex_vscode"
        append(parent, "session_meta", {"id": self.context["session"], "cwd": str(root),
                                        "originator": originator, "model_provider": "openai"})
        append(parent, "turn_context", settings)
        script = root / ".codex/hooks/subagents.py"
        hooks = root / ".codex/hooks.json"
        observation.write_text(json.dumps({"client": client, "thread_id": self.context["session"],
            "runtime": self.context["runtime"], "harness_root": str(root), "observed_via": "native-ui",
            "hook_sources": [{"path": str(hooks), "sha256": self.fp(hooks)["sha256"], "trusted": True,
                              "scripts": {str(script): self.fp(script)["sha256"]}}]}))
        handler = runpy.run_path(str(PACKAGE / "native_qualification.py"))["handle"]
        prepared = handler("prepare-probe", root, {"record_path": str(record), "task_name": name,
            "parent_log": str(parent), "client_context": str(observation),
            "tool": {"name": "collaboration.spawn_agent", "fields": ["task_name", "message", "fork_turns"]},
            "read_paths": [{"path": str(root / "app.txt"), "max_lines": None}],
            "protected_files": [str(hooks)], "display_required": True}, self.workflow)
        handler("begin-probe", root, {"record_path": str(record)}, self.workflow)
        begun = json.loads(record.read_text())["begun_at"]
        append(parent, "response_item", {"type": "function_call", "name": "spawn_agent", "namespace": "collaboration",
            "call_id": "update-call", "arguments": json.dumps(prepared["native_arguments"])})
        append(parent, "response_item", {"type": "function_call_output", "call_id": "update-call",
                                         "output": json.dumps({"agent_id": child_id})})
        dispatch.write_text(json.dumps({"call_id": "update-call", "tool": "collaboration.spawn_agent",
            "arguments": prepared["native_arguments"], "observed_via": "native-tool-call", "source_ref": "fixture call capture"}))
        append(child, "session_meta", {"id": child_id, "cwd": str(root),
            "timestamp": datetime.now(timezone.utc).isoformat(), "parent_thread_id": self.context["session"],
            "originator": originator, "model_provider": "openai", "source": {"subagent": {"thread_spawn": {
                "parent_thread_id": self.context["session"], "agent_path": "/root/" + name}}}})
        append(child, "turn_context", {**settings, "turn_id": str(uuid4())})
        for file in (declaration, root / "app.txt"):
            append(child, "response_item", {"type": "function_call", "name": "exec_command", "call_id": file.name,
                                            "arguments": json.dumps({"cmd": "cat " + str(file)})})
            append(child, "response_item", {"type": "function_call_output", "call_id": file.name,
                                            "output": json.dumps({"exit_code": 0, "output": file.read_text()})})
        report = {"status": "done", "summary": "Read declared fixture files", "changed_files": [],
                  "checks": ["Read declaration and app.txt"], "risks": [], "blockers": [], "next_action": "Verify evidence"}
        append(child, "response_item", {"type": "message", "role": "assistant", "phase": "final_answer",
            "content": [{"type": "output_text", "text": "```delegation-report\n" + json.dumps(report) + "\n```"}]})
        snapshot.write_text("Fixture Habblaud label: Tester\n")
        display.write_text(json.dumps({"client": client, "parent_thread_id": self.context["session"],
            "child_thread_id": child_id, "role": "Tester", "observed_label": "Tester", "source": "habblaud",
            "observer_started_at": begun - 1, "observed_at": begun + 1, "snapshot": str(snapshot)}))
        result = handler("record-probe", root, {"record_path": str(record), "child_log": str(child),
            "display_evidence": str(display), "dispatch_evidence": str(dispatch)}, self.workflow)
        self.assertTrue(result["complete"], result)
        return record

    def evidence(self, result, layer="execution", client="app", state="passed", outcome="verified", root=None):
        row = self.row(result, layer, client, root)
        payload = {"schema_version": 1, "root": row["root"], "layer": layer, "client": client,
                   "fingerprint": row["fingerprint"], "state": state, "reason": "Observed fixture result",
                   "next_action": "No action required" if state == "passed" else "Resolve fixture blocker",
                   "source": ({"client": client, **self.context} if client else None),
                   "outcome": outcome, "references": []}
        if layer in {"execution", "protocol", "display"} and state == "passed":
            probe_path = self.native_receipt(row["root"], client)
            payload["outcome"] = "native_probe"
            payload["references"] = [{"path": str(probe_path), "sha256": self.fp(probe_path)["sha256"]}]
        path = self.home / f"evidence-{uuid4()}.json"
        path.write_text(json.dumps(payload))
        return path, payload

    def record_evidence(self, path):
        return self.call("record-update", {"record_dir": str(self.record),
                                          "evidence": {"path": str(path), "sha256": self.fp(path)["sha256"]}})

    def test_plan_stages_complete_candidate_without_touching_destinations(self):
        before = self.manifest(self.installed), self.manifest(self.project)
        result = self.call("plan-update", self.request)
        self.assertEqual(before, (self.manifest(self.installed), self.manifest(self.project)))
        self.assertEqual((self.record / "stage/README.md").read_text(), "Updated package documentation.\n")
        self.assertEqual(self.manifest(self.candidate), self.manifest(self.record / "stage"))
        self.assertFalse(result["complete"])
        self.assertEqual(self.row(result)["state"], "pending")

    def test_three_way_conflict_preserves_custom_file_and_independent_install(self):
        custom = self.project / ".codex/delegation-brief.md"
        custom.write_text("User-owned customization\n")
        result = self.call("plan-update", self.request)
        self.assertTrue(result["conflicts"])
        result = self.call("apply-update")
        self.assertEqual(custom.read_text(), "User-owned customization\n")
        self.assertEqual((self.installed / "README.md").read_text(), "Updated package documentation.\n")
        self.assertFalse(result["complete"])

    def test_apply_preserves_unselected_roots_custom_settings_and_independent_opt_outs(self):
        other = self.repo("unselected")
        before_other = self.manifest(other)
        config = self.project / ".codex/config.toml"
        config.write_text(config.read_text() + '\n[custom]\nkeep = "yes"\n')
        before_config = config.read_bytes()
        before_policy = (self.project / ".codex/vibe-workflow.toml").read_bytes()
        self.call("plan-update", self.request)
        result = self.call("apply-update")
        self.assertEqual(config.read_bytes(), before_config)
        self.assertEqual((self.project / ".codex/vibe-workflow.toml").read_bytes(), before_policy)
        self.assertEqual(before_other, self.manifest(other))
        self.assertEqual((self.project / ".codex/delegation-brief.md").read_text(), "Updated delegation instructions.\n")
        self.assertEqual(self.row(result, "installation", None)["state"], "passed")
        self.assertEqual(self.row(result)["state"], "pending")

    def test_interrupted_write_resumes_from_hashes_without_replacing_original_backup(self):
        old = (self.installed / "README.md").read_bytes()
        self.call("plan-update", self.request)
        original = self.workflow["replace_setup_file"]
        def interrupted(path, *args):
            original(path, *args)
            if path == self.installed / "README.md":
                raise OSError("Fixture interruption after replacement")
        with self.assertRaises(OSError):
            self.call("apply-update", workflow={**self.workflow, "replace_setup_file": interrupted})
        self.call("resume-update")
        result = self.call("rollback-update")
        self.assertEqual((self.installed / "README.md").read_bytes(), old)
        self.assertEqual(result["transaction"], "rolled_back")

    def test_rollback_refuses_later_edits_and_preserves_unrelated_files(self):
        self.call("plan-update", self.request)
        self.call("apply-update")
        changed = self.installed / "README.md"
        changed.write_text("Later user edit\n")
        extra = self.installed / "custom.txt"
        extra.write_text("Keep me\n")
        with self.assertRaisesRegex(ValueError, "changed|edit|conflict"):
            self.call("rollback-update")
        self.assertEqual(changed.read_text(), "Later user edit\n")
        self.assertEqual(extra.read_text(), "Keep me\n")

    def test_foreign_client_and_mutated_evidence_never_complete_execution(self):
        result = self.call("plan-update", self.request)
        self.call("apply-update")
        path, payload = self.evidence(result)
        payload["source"]["client"] = "vscode"
        path.write_text(json.dumps(payload))
        with self.assertRaises(ValueError):
            self.record_evidence(path)
        payload["source"]["client"] = "app"
        path.write_text(json.dumps(payload))
        result = self.record_evidence(path)
        self.assertTrue(result["complete"])
        path.write_text(path.read_text() + "\n")
        result = self.call("status-update")
        self.assertEqual(self.row(result)["state"], "stale")
        self.assertFalse(result["complete"])

    def test_noop_rerun_preserves_evidence_and_file_mtimes(self):
        result = self.call("plan-update", self.request)
        self.call("apply-update")
        path, _ = self.evidence(result)
        self.record_evidence(path)
        files = [self.record / "state.json", self.record / "plan.json", self.installed / "README.md",
                 self.project / ".codex/delegation-brief.md"]
        before = [p.stat().st_mtime_ns for p in files]
        repeated = self.call("plan-update", self.request)
        applied = self.call("apply-update")
        self.assertTrue(repeated["complete"])
        self.assertTrue(applied["complete"])
        self.assertEqual(before, [p.stat().st_mtime_ns for p in files])
        self.assertEqual(applied["changes"], [])

    def test_inaccessible_remote_blocks_only_dependent_target(self):
        self.request["requirements"].append({"root": str(self.project), "layer": "publication", "client": None})
        result = self.call("plan-update", self.request)
        path, _ = self.evidence(result, "remote_access", None, "blocked", "inaccessible")
        self.record_evidence(path)
        original = (self.project / ".codex/delegation-brief.md").read_bytes()
        result = self.call("apply-update")
        self.assertEqual((self.project / ".codex/delegation-brief.md").read_bytes(), original)
        self.assertEqual((self.installed / "README.md").read_text(), "Updated package documentation.\n")
        self.assertEqual(self.row(result, "remote_access", None)["state"], "blocked")

    def test_queued_archive_and_configured_exclusion_remain_pending(self):
        self.request["targets"][0]["exclusions"] = ["legacy-skill"]
        self.request["requirements"].append({"root": str(self.project), "layer": "cleanup", "client": None})
        result = self.call("plan-update", self.request)
        for layer, client, outcome in (("cleanup", None, "archive_requested"), ("exclusions", "app", "configured")):
            path, _ = self.evidence(result, layer, client, "passed", outcome)
            recorded = self.record_evidence(path)
            self.assertNotEqual(self.row(recorded, layer, client)["state"], "passed")
            self.assertFalse(recorded["complete"])

    def test_primary_lifecycle_edits_require_exact_revision_or_verified_task(self):
        (self.project / ".codex/vibe-workflow.toml").write_text("schema_version = 1\n[task_lifecycle]\nenabled = true\n")
        with self.assertRaisesRegex(ValueError, "worktree|revision|binding"):
            self.call("plan-update", self.request)
        self.request["targets"][0]["activation_revision"] = self.git(self.project, "rev-parse", "HEAD")
        with self.assertRaisesRegex(ValueError, "revision|review|tracked"):
            self.call("plan-update", self.request)

    def test_missing_authority_cannot_apply_but_does_not_request_native_trust(self):
        self.request["authorizations"] = []
        self.call("plan-update", self.request)
        before = self.manifest(self.installed), self.manifest(self.project)
        result = self.call("apply-update")
        self.assertEqual(before, (self.manifest(self.installed), self.manifest(self.project)))
        self.assertFalse(result["complete"])
        self.assertIn("authorization", json.dumps(result))

    def test_unsafe_unknown_or_uncommitted_inputs_fail_before_destination_writes(self):
        before = self.manifest(self.installed), self.manifest(self.project)
        bad = copy.deepcopy(self.request)
        bad["unknown"] = True
        with self.assertRaises(ValueError):
            self.call("plan-update", bad)
        bad = copy.deepcopy(self.request)
        bad["record_dir"] = str(self.installed / "private-state")
        with self.assertRaises(ValueError):
            self.call("plan-update", bad)
        (self.candidate / "dependency.py").write_text("unreviewed = True\n")
        with self.assertRaises(ValueError):
            self.call("plan-update", self.request)
        self.assertEqual(before, (self.manifest(self.installed), self.manifest(self.project)))

    def test_deleted_owned_file_is_a_customization_not_permission_to_recreate(self):
        (self.installed / "README.md").unlink()
        (self.project / ".codex/delegation-brief.md").unlink()
        self.call("plan-update", self.request)
        result = self.call("apply-update")
        self.assertFalse((self.installed / "README.md").exists())
        self.assertFalse((self.project / ".codex/delegation-brief.md").exists())
        self.assertEqual(len(result["conflicts"]), 2)

    def test_native_pass_requires_matching_evaluated_probe_not_generic_assertion(self):
        result = self.call("plan-update", self.request)
        path, payload = self.evidence(result)
        payload["outcome"] = "verified"
        payload["references"] = []
        path.write_text(json.dumps(payload))
        with self.assertRaises(ValueError):
            self.record_evidence(path)

    def test_binary_dependency_is_frozen_and_installed_without_text_conversion(self):
        binary = b"\x00\xff\xfe\r\n\x80asset"
        (self.candidate / "asset.bin").write_bytes(binary)
        self.git(self.source, "add", ".")
        self.git(self.source, "commit", "-qm", "binary package asset")
        self.request["revision"] = self.git(self.source, "rev-parse", "HEAD")
        self.call("plan-update", self.request)
        self.call("apply-update")
        self.assertEqual((self.installed / "asset.bin").read_bytes(), binary)

    def test_changed_runtime_invalidates_only_client_evidence(self):
        result = self.call("plan-update", self.request)
        self.call("apply-update")
        evidence, _ = self.evidence(result)
        self.record_evidence(evidence)
        result = self.call("status-update", {"record_dir": str(self.record),
                    "contexts": {str(self.project): {"app": {**self.context, "runtime": "fixture-app-2"}}}})
        self.assertEqual(self.row(result)["state"], "stale")
        self.assertEqual(self.row(result, "installation", None)["state"], "passed")

    def test_external_symlink_swap_is_rejected_before_any_apply(self):
        self.call("plan-update", self.request)
        before = (self.installed / "README.md").read_bytes()
        outside = self.home / "outside"
        outside.write_text("Unrelated\n")
        destination = self.project / ".codex/delegation-brief.md"
        destination.unlink()
        destination.symlink_to(outside)
        with self.assertRaises(ValueError):
            self.call("apply-update")
        self.assertEqual((self.installed / "README.md").read_bytes(), before)
        self.assertEqual(outside.read_text(), "Unrelated\n")

    def test_cross_operation_destination_lock_prevents_concurrent_writes(self):
        self.call("plan-update", self.request)
        descriptor = os.open(self.project, os.O_RDONLY)
        self.addCleanup(os.close, descriptor)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        before = self.manifest(self.installed)
        with self.assertRaises(BlockingIOError):
            self.call("apply-update")
        self.assertEqual(before, self.manifest(self.installed))

    def test_rollback_never_claims_an_external_identical_new_file(self):
        new_file = self.candidate / "new-owned.txt"
        new_file.write_text("New package file\n")
        self.git(self.source, "add", ".")
        self.git(self.source, "commit", "-qm", "new package file")
        self.request["revision"] = self.git(self.source, "rev-parse", "HEAD")
        self.call("plan-update", self.request)
        external = self.installed / "new-owned.txt"
        external.write_bytes(new_file.read_bytes())
        external.chmod(new_file.stat().st_mode & 0o777)
        self.call("rollback-update")
        self.assertEqual(external.read_text(), "New package file\n")

    def test_required_package_checks_gate_installation_before_writes(self):
        self.request["requirements"].append({"root": str(self.source), "layer": "tests", "client": None})
        self.call("plan-update", self.request)
        before = self.manifest(self.installed), self.manifest(self.project)
        result = self.call("apply-update")
        self.assertEqual(before, (self.manifest(self.installed), self.manifest(self.project)))
        self.assertFalse(result["complete"])

    def test_new_noop_plan_reuses_only_matching_prior_native_evidence(self):
        result = self.call("plan-update", self.request)
        self.call("apply-update")
        evidence, _ = self.evidence(result)
        self.record_evidence(evidence)
        previous = self.record
        self.record = self.home / "records" / str(uuid4())
        self.request.update(operation_id=self.record.name, record_dir=str(self.record), reuse_from=str(previous))
        result = self.call("plan-update", self.request)
        self.assertEqual(self.row(result)["state"], "passed")
        self.assertEqual(self.call("apply-update")["changes"], [])

    def test_custom_hook_conflict_does_not_hide_independent_installed_update(self):
        hooks = self.project / ".codex/hooks.json"
        data = json.loads(hooks.read_text())
        data["hooks"]["SubagentStart"][0]["timeout"] = 999
        hooks.write_text(json.dumps(data))
        before = hooks.read_bytes()
        self.call("plan-update", self.request)
        result = self.call("apply-update")
        self.assertEqual(hooks.read_bytes(), before)
        self.assertEqual((self.installed / "README.md").read_text(), "Updated package documentation.\n")
        self.assertTrue(result["conflicts"])

    def test_umbrella_noop_preserves_hook_format_and_never_enrolls_children(self):
        umbrella = self.home / "umbrella"
        umbrella.mkdir()
        runpy.run_path(str(self.candidate / "install.py"))["install"](umbrella, non_git=True)
        shutil.copyfile(self.candidate / ".codex/vibe-workflow.toml", umbrella / ".codex/vibe-workflow.toml")
        hooks = umbrella / ".codex/hooks.json"
        hooks.write_text(json.dumps(json.loads(hooks.read_text()), separators=(",", ":")))
        child = umbrella / "child"
        child.mkdir()
        (child / "keep.txt").write_text("Unselected\n")
        self.request["targets"] = [{"root": str(umbrella), "kind": "umbrella",
                                     "baseline": {name: self.fp(umbrella / name) for name in self.workflow["SETUP_FILES"]},
                                     "clients": {}, "task": None, "activation_revision": None, "exclusions": []}]
        self.request["requirements"] = []
        self.request["authorizations"][1]["roots"] = [str(umbrella)]
        before = self.manifest(umbrella)
        self.call("plan-update", self.request)
        self.call("apply-update")
        self.assertEqual(self.manifest(umbrella), before)

    def test_reviewed_owned_hook_upgrade_preserves_unrelated_groups(self):
        hooks = self.project / ".codex/hooks.json"
        current = json.loads(hooks.read_text())
        unrelated = {"hooks": [{"type": "command", "command": "printf fixture", "timeout": 1}]}
        current["hooks"]["SubagentStart"].append(unrelated)
        hooks.write_text(json.dumps(current))
        self.request["targets"][0]["baseline"][".codex/hooks.json"] = self.fp(hooks)
        candidate_hooks = self.candidate / ".codex/hooks.json"
        proposed = json.loads(candidate_hooks.read_text())
        proposed["hooks"]["SubagentStart"][0]["hooks"][0]["timeout"] = 4
        candidate_hooks.write_text(json.dumps(proposed))
        self.git(self.source, "add", ".")
        self.git(self.source, "commit", "-qm", "reviewed hook update")
        self.request["revision"] = self.git(self.source, "rev-parse", "HEAD")
        self.call("plan-update", self.request)
        self.call("apply-update")
        updated = json.loads(hooks.read_text())
        self.assertIn(unrelated, updated["hooks"]["SubagentStart"])
        self.assertEqual(updated["hooks"]["SubagentStart"][0]["hooks"][0]["timeout"], 4)

    def test_verified_task_allows_adoption_without_touching_primary(self):
        policy = self.project / ".codex/vibe-workflow.toml"
        policy.write_text("schema_version = 1\n[task_lifecycle]\nenabled = true\nauto_cleanup = false\n")
        self.git(self.project, "add", ".")
        self.git(self.project, "commit", "-qm", "enable lifecycle")
        task = {"task_id": str(uuid4()), "worktree": str(self.home / "worker"), "branch": "codex/update-fixture", "base": "main"}
        self.assertEqual(self.workflow["start_task"](self.project, task)["implementation"], "worktree_verified")
        worker = Path(task["worktree"])
        primary = (self.project / ".codex/delegation-brief.md").read_bytes()
        self.request["targets"][0].update(root=str(worker), clients={}, task={"task_id": task["task_id"], "worktree": str(worker)})
        self.request["authorizations"][1]["roots"] = [str(worker)]
        self.request["requirements"] = []
        self.call("plan-update", self.request)
        self.call("apply-update")
        self.assertEqual((worker / ".codex/delegation-brief.md").read_text(), "Updated delegation instructions.\n")
        self.assertEqual((self.project / ".codex/delegation-brief.md").read_bytes(), primary)

    def test_tampered_record_and_unknown_evidence_are_rejected(self):
        result = self.call("plan-update", self.request)
        evidence, payload = self.evidence(result)
        payload["trust_granted"] = True
        evidence.write_text(json.dumps(payload))
        with self.assertRaises(ValueError):
            self.record_evidence(evidence)
        state_path = self.record / "state.json"
        state = json.loads(state_path.read_text())
        state["started"] = ["outside-owned-scope"]
        state_path.write_text(json.dumps(state))
        before = self.manifest(self.installed), self.manifest(self.project)
        with self.assertRaises(ValueError):
            self.call("resume-update")
        self.assertEqual(before, (self.manifest(self.installed), self.manifest(self.project)))

    def test_installed_target_overlap_is_rejected_before_staging_in_both_directions(self):
        for installed_is_parent in (True, False):
            for kind in ("project", "umbrella", "source"):
                with self.subTest(installed_is_parent=installed_is_parent, kind=kind):
                    installed = self.home / f"overlap-{installed_is_parent}-{kind}"
                    installed.mkdir()
                    if installed_is_parent:
                        target = installed / "child"
                        target.mkdir()
                    else:
                        target = installed
                        installed = target / "child"
                        installed.mkdir()
                    (target / "sentinel.txt").write_text("Preserve selected root\n")
                    (installed / "installed-sentinel.txt").write_text("Preserve installed skill\n")
                    request = copy.deepcopy(self.request)
                    record = self.home / "records" / str(uuid4())
                    request.update(operation_id=record.name, record_dir=str(record))
                    request["installed"] = {"root": str(installed), "baseline": {}}
                    request["targets"] = [{"root": str(target), "kind": kind, "baseline": {},
                                           "clients": {}, "task": None, "activation_revision": None,
                                           "exclusions": []}]
                    request["authorizations"] = []
                    request["requirements"] = []
                    before = self.manifest(target), self.manifest(installed)
                    with self.assertRaisesRegex(ValueError, "Installed.*target|installed.*target"):
                        self.call("plan-update", request)
                    self.assertFalse(record.exists())
                    self.assertEqual(before, (self.manifest(target), self.manifest(installed)))

    def test_explicit_umbrella_and_child_targets_can_coexist(self):
        umbrella = self.home / "coordination"
        umbrella.mkdir()
        child = self.repo("coordination/child")
        (child / ".codex").mkdir()
        (child / ".codex/vibe-workflow.toml").write_text("schema_version = 1\n[task_lifecycle]\nenabled = false\n")
        self.request["targets"] = [
            {"root": str(root), "kind": kind, "baseline": {}, "clients": {}, "task": None,
             "activation_revision": None, "exclusions": []}
            for root, kind in ((umbrella, "umbrella"), (child, "project"))]
        self.request["requirements"] = []
        self.request["authorizations"][1]["roots"] = [str(umbrella), str(child)]
        result = self.call("plan-update", self.request)
        roots = {row["root"] for row in result["outcomes"] if row["layer"] == "installation"}
        self.assertEqual(roots, {str(self.installed), str(umbrella), str(child)})
        self.assertFalse((umbrella / ".codex").exists())
        self.assertFalse((child / ".codex/hooks.json").exists())

    def test_truncated_native_receipt_with_pass_flags_cannot_be_ingested(self):
        result = self.call("plan-update", self.request)
        self.call("apply-update")
        evidence, envelope = self.evidence(result)
        reference = envelope["references"][0]
        probe = Path(reference["path"])
        original = json.loads(probe.read_text())
        kept = {key: original[key] for key in ("schema_version", "root", "client", "parent_thread_id",
                                               "attempts", "context", "settings", "result")}
        probe.write_text(json.dumps(kept))
        reference["sha256"] = self.fp(probe)["sha256"]
        evidence.write_text(json.dumps(envelope))
        with self.assertRaises(ValueError):
            self.record_evidence(evidence)
        self.assertEqual(self.row(self.call("status-update"))["state"], "pending")

    def test_malformed_inner_native_fields_stale_only_the_affected_outcome(self):
        result = self.call("plan-update", self.request)
        self.call("apply-update")
        evidence, envelope = self.evidence(result)
        self.record_evidence(evidence)
        reference = envelope["references"][0]
        probe = Path(reference["path"])
        data = json.loads(probe.read_text())
        data["reads"] = [None]
        probe.write_text(json.dumps(data))
        reference["sha256"] = self.fp(probe)["sha256"]
        evidence.write_text(json.dumps(envelope))
        state_file = self.record / "state.json"
        state = json.loads(state_file.read_text())
        state["evidence"][next(iter(state["evidence"]))]["sha256"] = self.fp(evidence)["sha256"]
        state_file.write_text(json.dumps(state))
        result = self.call("status-update")
        self.assertEqual(self.row(result)["state"], "stale")
        self.assertEqual(self.row(result, "installation", None)["state"], "passed")

    def test_inner_native_and_display_artifact_changes_invalidate_update_status(self):
        result = self.call("plan-update", self.request)
        self.call("apply-update")
        evidence, envelope = self.evidence(result)
        self.record_evidence(evidence)
        probe = Path(envelope["references"][0]["path"])
        fixture = probe.parent
        for name in ("child.jsonl", "dispatch.json", "snapshot.txt"):
            with self.subTest(name=name):
                artifact = fixture / name
                original = artifact.read_bytes()
                artifact.write_bytes(b"changed" + original)
                status = self.call("status-update")
                self.assertEqual(self.row(status)["state"], "stale")
                self.assertFalse(status["complete"])
                artifact.write_bytes(original)
        (fixture / "parent.jsonl").unlink()
        self.assertEqual(self.row(self.call("status-update"))["state"], "stale")

    def test_append_only_native_events_remain_valid_but_stale_receipts_are_not_reused(self):
        result = self.call("plan-update", self.request)
        self.call("apply-update")
        evidence, envelope = self.evidence(result)
        self.record_evidence(evidence)
        fixture = Path(envelope["references"][0]["path"]).parent
        for name in ("parent.jsonl", "child.jsonl"):
            with (fixture / name).open("a") as stream:
                stream.write(json.dumps({"type": "event_msg", "payload": {"type": "task_complete"}}) + "\n")
        self.assertTrue(self.call("status-update")["complete"])
        (fixture / "child.jsonl").unlink()
        previous = self.record
        self.record = self.home / "records" / str(uuid4())
        self.request.update(operation_id=self.record.name, record_dir=str(self.record), reuse_from=str(previous))
        result = self.call("plan-update", self.request)
        self.assertEqual(self.row(result)["state"], "pending")

    def test_git_primary_and_nested_directories_cannot_claim_umbrella_kind(self):
        policy = self.project / ".codex/vibe-workflow.toml"
        policy.write_text("schema_version = 1\n[task_lifecycle]\nenabled = true\n")
        nested = self.project / "nested"
        nested.mkdir()
        for root in (self.project, nested):
            with self.subTest(root=root):
                request = copy.deepcopy(self.request)
                record = self.home / "records" / str(uuid4())
                request.update(operation_id=record.name, record_dir=str(record))
                request["targets"][0].update(root=str(root), kind="umbrella", clients={})
                request["requirements"] = []
                request["authorizations"][1]["roots"] = [str(root)]
                before = self.manifest(self.project)
                with self.assertRaisesRegex(ValueError, "umbrella|Git"):
                    self.call("plan-update", request)
                self.assertEqual(self.manifest(self.project), before)
                self.assertFalse(record.exists())

    def test_umbrella_becoming_git_after_plan_blocks_all_apply_writes(self):
        umbrella = self.home / "new-umbrella"
        umbrella.mkdir()
        self.request["targets"][0].update(root=str(umbrella), kind="umbrella", clients={}, baseline={})
        self.request["requirements"] = []
        self.request["authorizations"][1]["roots"] = [str(umbrella)]
        self.call("plan-update", self.request)
        self.git(umbrella, "init", "-q")
        before = self.manifest(self.installed), self.manifest(umbrella)
        with self.assertRaisesRegex(ValueError, "umbrella|Git"):
            self.call("apply-update")
        self.assertEqual(before, (self.manifest(self.installed), self.manifest(umbrella)))

    def test_broken_git_metadata_cannot_be_classified_as_an_umbrella(self):
        broken = self.home / "broken-worktree"
        broken.mkdir()
        (broken / ".git").write_text("gitdir: /nonexistent/vibe-fixture-worktree\n")
        config = self.project / ".git/config"
        config.write_text("[invalid Git configuration\n")
        nested = self.project / "nested-broken"
        nested.mkdir()
        for root in (broken, self.project, nested):
            with self.subTest(root=root):
                request = copy.deepcopy(self.request)
                record = self.home / "records" / str(uuid4())
                request.update(operation_id=record.name, record_dir=str(record))
                request["targets"] = [{"root": str(root), "kind": "umbrella", "baseline": {},
                                       "clients": {}, "task": None, "activation_revision": None, "exclusions": []}]
                request["authorizations"][1]["roots"] = [str(root)]
                request["requirements"] = []
                before = self.manifest(root)
                with self.assertRaisesRegex(ValueError, "umbrella|Git"):
                    self.call("plan-update", request)
                self.assertFalse(record.exists())
                self.assertEqual(self.manifest(root), before)

    def test_broken_git_pointer_added_after_planning_blocks_apply(self):
        umbrella = self.home / "later-broken-umbrella"
        umbrella.mkdir()
        self.request["targets"][0].update(root=str(umbrella), kind="umbrella", clients={}, baseline={})
        self.request["requirements"] = []
        self.request["authorizations"][1]["roots"] = [str(umbrella)]
        self.call("plan-update", self.request)
        (umbrella / ".git").write_text("gitdir: /nonexistent/vibe-fixture-worktree\n")
        before = self.manifest(self.installed), self.manifest(umbrella)
        with self.assertRaisesRegex(ValueError, "umbrella|Git"):
            self.call("apply-update")
        self.assertEqual(before, (self.manifest(self.installed), self.manifest(umbrella)))

    def test_unknown_or_empty_git_failure_does_not_prove_non_git(self):
        umbrella = self.home / "unknown-git-failure"
        umbrella.mkdir()
        for diagnostic in ("", "fatal: unreadable repository configuration"):
            with self.subTest(diagnostic=diagnostic):
                result = subprocess.CompletedProcess(["git"], 128, stdout="", stderr=diagnostic)
                workflow = {**self.workflow, "git": lambda *args, **kwargs: result}
                with self.assertRaises(ValueError):
                    self.api["verify_umbrella"](umbrella, workflow)

    def installed_call(self, operation, request=None):
        result = subprocess.run(["python3", "-B", str(self.installed / "workflow.py"), operation, str(self.source)],
                                input=json.dumps(request or {"record_dir": str(self.record)}),
                                text=True, capture_output=True)
        self.assertIn(result.returncode, (0, 2), result.stderr)
        payload = json.loads(result.stdout)
        self.assertNotEqual(payload["status"], "blocked", payload)
        return payload

    def test_installed_helper_records_observed_archive_after_source_worktree_removal(self):
        self.request["targets"].append({"root": str(self.source), "kind": "source", "baseline": {},
            "clients": {}, "task": None, "activation_revision": None, "exclusions": []})
        self.request["requirements"].append({"root": str(self.source), "layer": "cleanup", "client": None})
        self.request["authorizations"].append({"action": "cleanup", "roots": [str(self.source)],
                                             "provenance": "Observed fixture archive", "constraints": []})
        result = self.call("plan-update", self.request)
        self.call("apply-update")
        evidence, _ = self.evidence(result)
        self.record_evidence(evidence)
        queued, _ = self.evidence(result, "cleanup", None, outcome="archive_requested", root=self.source)
        self.record_evidence(queued)
        archived, _ = self.evidence(result, "cleanup", None, outcome="archived", root=self.source)
        shutil.rmtree(self.source)
        before = self.manifest(self.installed), self.manifest(self.project)
        status = self.installed_call("status-update")
        self.assertEqual(self.row(status, "cleanup", None, self.source)["state"], "pending")
        self.assertFalse(status["complete"])
        result = self.installed_call("record-update", {"record_dir": str(self.record), "evidence": {
            "path": str(archived), "sha256": self.fp(archived)["sha256"]}})
        self.assertTrue(result["complete"], result)
        self.assertEqual(result["roots"][str(self.source)], "archived")
        self.assertEqual(self.row(result)["state"], "passed")
        self.assertEqual(self.row(result, "installation", None, self.installed)["state"], "passed")
        self.assertTrue(self.installed_call("status-update")["complete"])
        self.assertFalse(self.source.exists())
        self.assertEqual(before, (self.manifest(self.installed), self.manifest(self.project)))

    def test_unobserved_source_disappearance_does_not_prove_cleanup(self):
        self.request["requirements"] = []
        self.call("plan-update", self.request)
        self.assertTrue(self.call("apply-update")["complete"])
        shutil.rmtree(self.source)
        before = (self.record / "state.json").read_bytes()
        result = self.installed_call("status-update")
        self.assertFalse(result["complete"])
        self.assertEqual(result["roots"][str(self.source)], "unavailable")
        self.assertEqual((self.record / "state.json").read_bytes(), before)
        self.assertFalse(self.source.exists())

    def test_removed_writable_target_retains_history_without_current_deployment_claim(self):
        self.request["requirements"].append({"root": str(self.project), "layer": "cleanup", "client": None})
        result = self.call("plan-update", self.request)
        self.call("apply-update")
        evidence, _ = self.evidence(result)
        self.record_evidence(evidence)
        archived, _ = self.evidence(result, "cleanup", None, outcome="archived")
        shutil.rmtree(self.project)
        result = self.call("status-update")
        self.assertEqual(result["roots"][str(self.project)], "unavailable")
        self.assertEqual(self.row(result, "cleanup", None)["state"], "pending")
        self.assertEqual(self.row(result)["state"], "stale")
        self.assertEqual(self.row(result)["historical_evidence"]["path"], str(evidence))
        result = self.record_evidence(archived)
        self.assertEqual(result["roots"][str(self.project)], "archived")
        self.assertEqual(self.row(result, "cleanup", None)["state"], "passed")
        for layer, client in (("installation", None), ("activation", None), ("execution", "app")):
            self.assertEqual(self.row(result, layer, client)["state"], "stale")
        self.assertEqual(self.row(result, "installation", None, self.installed)["state"], "passed")
        self.assertFalse(result["complete"])
        self.assertFalse(self.project.exists())

    def test_missing_roots_refuse_all_mutations_before_writing_other_destinations(self):
        self.call("plan-update", self.request)
        for removed in (self.project, self.candidate, self.source):
            saved = self.home / f"removed-{uuid4()}"
            removed.rename(saved)
            before = self.manifest(self.installed), (self.record / "state.json").read_bytes()
            for operation in ("apply-update", "resume-update", "rollback-update"):
                with self.subTest(root=removed, operation=operation):
                    with self.assertRaises(ValueError):
                        self.call(operation)
                    self.assertFalse(removed.exists())
                    self.assertEqual(before, (self.manifest(self.installed), (self.record / "state.json").read_bytes()))
            saved.rename(removed)

    def test_archived_verified_task_preserves_only_proven_historical_installation(self):
        policy = self.project / ".codex/vibe-workflow.toml"
        policy.write_text("schema_version = 1\n[task_lifecycle]\nenabled = true\nauto_cleanup = true\n")
        self.git(self.project, "add", ".")
        self.git(self.project, "commit", "-qm", "enable lifecycle")
        original = copy.deepcopy(self.request)
        for case in ("observed", "no_authority", "not_applied", "missing_write_receipt", "rolled_back", "client_inputs_missing"):
            with self.subTest(case=case):
                self.record = self.home / "records" / str(uuid4())
                task = {"task_id": str(uuid4()), "worktree": str(self.home / ("worker-" + case)),
                        "branch": "codex/" + case, "base": "main"}
                self.assertEqual(self.workflow["start_task"](self.project, task)["implementation"], "worktree_verified")
                worker = Path(task["worktree"])
                self.request = copy.deepcopy(original)
                self.request.update(operation_id=self.record.name, record_dir=str(self.record))
                self.request["targets"][0].update(root=str(worker), clients={},
                    task={"task_id": task["task_id"], "worktree": str(worker)})
                self.request["authorizations"][1]["roots"] = [str(worker)]
                if case != "no_authority":
                    self.request["authorizations"].append({"action": "cleanup", "roots": [str(worker)],
                        "provenance": "Explicit fixture cleanup", "constraints": []})
                self.request["requirements"] = [{"root": str(worker), "layer": "cleanup", "client": None}]
                if case == "client_inputs_missing":
                    self.context = {**self.context, "hook_source": str(worker / ".codex/hooks.json")}
                    self.request["targets"][0]["clients"] = {"app": self.context}
                    self.request["requirements"].append({"root": str(worker), "layer": "execution", "client": "app"})
                result = self.call("plan-update", self.request)
                if case != "not_applied":
                    self.call("apply-update")
                if case == "rolled_back":
                    self.call("rollback-update")
                if case == "client_inputs_missing":
                    native, _ = self.evidence(result, root=worker)
                    self.record_evidence(native)
                queued, _ = self.evidence(result, "cleanup", None, outcome="archive_requested", root=worker)
                self.record_evidence(queued)
                archived, _ = self.evidence(result, "cleanup", None, outcome="archived", root=worker)
                if case == "missing_write_receipt":
                    state_path = self.record / "state.json"
                    state = json.loads(state_path.read_text())
                    plan = json.loads((self.record / "plan.json").read_text())
                    changed = next(name for name, item in plan["destinations"][str(worker)]["files"].items()
                                   if item["before"] != item["after"])
                    state["done"].remove(self.api["file_id"](str(worker), changed))
                    state_path.write_text(json.dumps(state))
                shutil.rmtree(worker)
                pending = self.call("status-update")
                self.assertEqual(self.row(pending, "installation", None, worker)["state"], "stale")
                self.assertFalse(pending["complete"])
                result = self.record_evidence(archived)
                historical = case in {"observed", "client_inputs_missing"}
                for layer in ("installation", "activation"):
                    row = self.row(result, layer, None, worker)
                    self.assertEqual(row["state"], "passed" if historical else "stale")
                    if historical:
                        self.assertEqual(row["basis"], "historical")
                        self.assertEqual(row["deployment"], "inactive")
                if case == "client_inputs_missing":
                    self.assertEqual(self.row(result, root=worker)["state"], "stale")
                self.assertEqual(result["complete"], case == "observed")
                self.assertFalse(worker.exists())

    def test_noop_verified_task_can_archive_with_historical_completion(self):
        (self.project / ".codex/vibe-workflow.toml").write_text(
            "schema_version = 1\n[task_lifecycle]\nenabled = true\nauto_cleanup = true\n")
        self.git(self.project, "add", ".")
        self.git(self.project, "commit", "-qm", "enable lifecycle")
        task = {"task_id": str(uuid4()), "worktree": str(self.home / "noop-worker"),
                "branch": "codex/noop-worker", "base": "main"}
        self.assertEqual(self.workflow["start_task"](self.project, task)["implementation"], "worktree_verified")
        worker = Path(task["worktree"])
        self.request["targets"][0].update(root=str(worker), clients={},
            task={"task_id": task["task_id"], "worktree": str(worker)})
        self.request["authorizations"][1]["roots"] = [str(worker)]
        self.request["requirements"] = []
        self.call("plan-update", self.request)
        self.call("apply-update")
        self.record = self.home / "records" / str(uuid4())
        self.request.update(operation_id=self.record.name, record_dir=str(self.record))
        self.request["authorizations"].append({"action": "cleanup", "roots": [str(worker)],
                                             "provenance": "Explicit fixture cleanup", "constraints": []})
        self.request["requirements"] = [{"root": str(worker), "layer": "cleanup", "client": None}]
        result = self.call("plan-update", self.request)
        self.assertEqual(self.call("apply-update")["changes"], [])
        self.assertEqual(json.loads((self.record / "state.json").read_text())["done"], [])
        archived, _ = self.evidence(result, "cleanup", None, outcome="archived", root=worker)
        shutil.rmtree(worker)
        result = self.record_evidence(archived)
        self.assertTrue(result["complete"], result)
        for layer in ("installation", "activation"):
            row = self.row(result, layer, None, worker)
            self.assertEqual(row["state"], "passed")
            self.assertEqual(row["basis"], "historical")
            self.assertEqual(row["deployment"], "inactive")
        self.assertFalse(worker.exists())


if __name__ == "__main__":
    unittest.main()
