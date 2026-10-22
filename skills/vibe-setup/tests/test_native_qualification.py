"""Native qualification receipts: real files and native event shapes, no live calls."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from uuid import uuid4

PACKAGE = Path(__file__).resolve().parents[1]


class NativeQualificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.root = self.home / "project"
        self.root.mkdir()
        self.wf = runpy.run_path(str(PACKAGE / "workflow.py"))
        self.handle = runpy.run_path(str(PACKAGE / "native_qualification.py"))["handle"]
        self.parent_id, self.child_id, self.turn = str(uuid4()), str(uuid4()), str(uuid4())
        self.parent = self.home / "parent.jsonl"
        self.child = self.home / "child.jsonl"
        self.record = self.home / "probe.json"
        self.context = self.home / "context.json"
        self.hook = self.root / ".codex/hooks.json"
        self.hook.parent.mkdir()
        self.hook.write_bytes((PACKAGE / ".codex/hooks.json").read_bytes())
        self.script = self.root / ".codex/hooks/subagents.py"
        self.script.parent.mkdir()
        self.script.write_bytes((PACKAGE / ".codex/hooks/subagents.py").read_bytes())
        self.readme = self.root / "README.md"
        self.readme.write_text("# Example\nRead this line.\nDo not read this line.\n")
        self.name = "client_canary"
        self.declaration = self.root / f".codex-delegations/{self.name}.json"
        self.declaration.parent.mkdir()
        self.declaration.write_text(json.dumps({
            "role": "Tester", "specialty": "Custom client validation", "objective": "Read only",
            "context": str(self.root), "instructions": "Read declaration and README lines 1–2.",
            "allowed_files": [], "mutable_resources": [], "dependencies": [],
            "acceptance": ["Read only"], "checks": ["Read declaration and README"],
            "read_only": True, "budget": {"minutes": 3, "attempts": 1}}))
        self.settings = {"turn_id": self.turn, "root_turn_id": self.turn, "cwd": str(self.root),
                         "model": "inherited-model", "effort": "high", "approval_policy": "never",
                         "sandbox_policy": {"type": "danger-full-access"}}
        self.append(self.parent, "session_meta", {"id": self.parent_id, "cwd": str(self.root),
                    "originator": "codex_work_desktop", "model_provider": "openai", "cli_version": "test"})
        self.append(self.parent, "turn_context", self.settings)
        self.context.write_text(json.dumps({"client": "app", "thread_id": self.parent_id,
            "runtime": "test", "harness_root": str(self.root), "observed_via": "native-ui",
            "hook_sources": [{"path": str(self.hook), "sha256": self.sha(self.hook),
                              "trusted": True, "scripts": {str(self.script): self.sha(self.script)}}]}))
        self.request = {"record_path": str(self.record), "task_name": self.name,
                        "parent_log": str(self.parent), "client_context": str(self.context),
                        "tool": {"name": "collaboration.spawn_agent",
                                 "fields": ["task_name", "message", "fork_turns", "model"]},
                        "read_paths": [{"path": str(self.readme), "max_lines": 2}],
                        "protected_files": [str(self.hook)], "display_required": True}
        self.report = {"status": "done", "summary": "Read only", "changed_files": [],
                       "checks": ["Declaration and README read"], "risks": [], "blockers": [],
                       "next_action": "Coordinator verifies evidence"}

    def sha(self, path):
        return self.wf["fingerprint"](path)["sha256"]

    def append(self, path, kind, payload):
        with path.open("a") as stream:
            stream.write(json.dumps({"type": kind, "payload": payload}) + "\n")

    def call(self, op, request=None):
        return self.handle(op, self.root, request or {"record_path": str(self.record)}, self.wf)

    def prepare_begin(self):
        result = self.call("prepare-probe", self.request)
        self.assertEqual(result["status"], "ok")
        begun = self.call("begin-probe")
        self.assertEqual(begun["status"], "ok")
        return begun

    def completed(self, report=None, settings=None):
        self.append(self.parent, "response_item", {"type": "function_call", "name": "spawn_agent",
            "namespace": "collaboration", "call_id": "call1", "arguments": json.dumps(
                json.loads(self.record.read_text())["native_arguments"])})
        self.append(self.parent, "response_item", {"type": "function_call_output", "call_id": "call1",
            "output": json.dumps({"task_name": "/root/" + self.name})})
        self.append(self.child, "session_meta", {"id": self.child_id, "cwd": str(self.root),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "parent_thread_id": self.parent_id, "originator": "codex_work_desktop", "model_provider": "openai",
            "source": {"subagent": {"thread_spawn": {"parent_thread_id": self.parent_id,
                         "agent_path": "/root/" + self.name}}}})
        self.append(self.child, "turn_context", settings or {**self.settings, "turn_id": str(uuid4())})
        for path, text in ((self.declaration, self.declaration.read_text()),
                           (self.readme, "# Example\nRead this line.\n")):
            cid = path.name
            self.append(self.child, "response_item", {"type": "function_call", "name": "exec_command",
                "call_id": cid, "arguments": json.dumps({"cmd": "cat " + str(path)})})
            self.append(self.child, "response_item", {"type": "function_call_output", "call_id": cid,
                "output": json.dumps({"exit_code": 0, "output": text})})
        self.append(self.child, "response_item", {"type": "message", "role": "assistant", "phase": "final_answer",
            "content": [{"type": "output_text", "text": "```delegation-report\n" +
                         json.dumps(report or self.report) + "\n```"}]})
        return {"record_path": str(self.record), "child_log": str(self.child)}

    def test_packet_supplies_top_level_name_and_no_execution_overrides(self):
        result = self.call("prepare-probe", self.request)
        args = result["native_arguments"]
        self.assertEqual(set(args), {"task_name", "message", "fork_turns"})
        self.assertEqual(args["task_name"], "client_canary")
        self.assertEqual(args["message"].count(".codex-delegations/client_canary.json"), 1)
        self.assertEqual(set(result["report_skeleton"]), set(self.report))
        self.assertEqual(result["specialty_assessment"], "Not assessed")

    def test_public_cli_prepares_a_packet_and_rejects_unknown_request_fields(self):
        command = [sys.executable, "-B", str(PACKAGE / "workflow.py"), "prepare-probe", str(self.root)]
        result = subprocess.run(command, input=json.dumps(self.request), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(json.loads(result.stdout)["native_arguments"]["task_name"], self.name)
        result = subprocess.run(command, input=json.dumps({**self.request, "model": "override"}),
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(json.loads(result.stdout)["status"], "blocked")

    def test_wrong_root_ambiguous_guard_and_unsupported_schema_never_prepare(self):
        original = json.loads(self.context.read_text())
        for change in ("root", "guards", "tool", "name", "role"):
            with self.subTest(change=change):
                self.context.write_text(json.dumps(original))
                request = copy.deepcopy(self.request)
                if change == "root":
                    value = {**original, "harness_root": str(self.home)}
                    self.context.write_text(json.dumps(value))
                elif change == "guards":
                    self.context.write_text(json.dumps({**original, "hook_sources": original["hook_sources"] * 2}))
                elif change == "tool":
                    request["tool"]["fields"].remove("task_name")
                elif change == "name":
                    request["task_name"] = "../invalid"
                else:
                    brief = json.loads(self.declaration.read_text())
                    brief["role"] = "Wizard"
                    self.declaration.write_text(json.dumps(brief))
                with self.assertRaises(ValueError):
                    self.call("prepare-probe", request)
                self.assertFalse(self.record.exists())

    def test_consumed_attempt_survives_restart_and_denial(self):
        self.prepare_begin()
        with self.assertRaises(ValueError):
            self.call("begin-probe")
        self.append(self.parent, "response_item", {"type": "function_call", "name": "spawn_agent",
            "namespace": "collaboration", "arguments": json.dumps({"task_name": self.name}), "call_id": "denied"})
        self.append(self.parent, "response_item", {"type": "function_call_output", "call_id": "denied",
            "output": "Subagent dispatch denied"})
        result = self.call("record-probe")
        self.assertFalse(result["protocol_passed"])
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(result["state"], "denied")
        with self.assertRaises(ValueError):
            self.call("begin-probe")

    def test_uncertain_response_never_allows_another_call(self):
        self.prepare_begin()
        result = self.call("record-probe")
        self.assertEqual(result["state"], "uncertain")
        with self.assertRaises(ValueError):
            self.call("begin-probe")

    def test_first_report_and_display_are_separate_from_execution(self):
        self.prepare_begin()
        result = self.call("record-probe", self.completed())
        self.assertTrue(result["execution_passed"])
        self.assertTrue(result["protocol_passed"])
        self.assertFalse(result["display_passed"])
        self.assertFalse(result["complete"])
        self.assertEqual(result["authentication"], "not_exposed")

    def test_corrected_report_never_erases_first_report_failure(self):
        self.prepare_begin()
        request = self.completed({**self.report, "observed": "extra"})
        self.append(self.child, "response_item", {"type": "message", "role": "assistant", "phase": "final_answer",
            "content": [{"type": "output_text", "text": "```delegation-report\n" + json.dumps(self.report) + "\n```"}]})
        result = self.call("record-probe", request)
        self.assertFalse(result["protocol_passed"])
        self.assertTrue(result["recovery_observed"])

    def test_commentary_is_not_mistaken_for_an_invalid_final_report(self):
        self.prepare_begin()
        request = self.completed()
        rows = self.child.read_text().splitlines()
        rows.insert(-1, json.dumps({"type": "response_item", "payload": {"type": "message",
            "role": "assistant", "phase": "commentary", "content": [{"text": "Reading the files."}]}}))
        self.child.write_text("\n".join(rows) + "\n")
        result = self.call("record-probe", request)
        self.assertTrue(result["protocol_passed"])
        self.assertEqual(result["final_reports"], 1)

    def test_native_argument_changes_and_unavailable_encrypted_messages_do_not_pass(self):
        for field, value in (("message", "wrong declaration"), ("fork_turns", "none"), ("message", "gAAAAopaque")):
            with self.subTest(field=field, value=value):
                if self.record.exists():
                    self.record.unlink()
                self.child.unlink(missing_ok=True)
                self.prepare_begin()
                request = self.completed()
                rows = [json.loads(line) for line in self.parent.read_text().splitlines()]
                call = rows[-2]["payload"]
                args = json.loads(call["arguments"])
                args[field] = value
                call["arguments"] = json.dumps(args)
                self.parent.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
                result = self.call("record-probe", request)
                self.assertFalse(result["protocol_passed"])

    def test_cached_pass_rejects_changed_child_evidence_but_allows_appended_events(self):
        self.request["display_required"] = False
        self.prepare_begin()
        self.call("record-probe", self.completed())
        self.append(self.child, "event_msg", {"type": "task_complete"})
        self.assertTrue(self.call("status-probe")["complete"])
        self.child.write_text(self.child.read_text().replace("Read only", "Different"))
        with self.assertRaises(ValueError):
            self.call("status-probe")

    def test_missing_settings_and_stale_script_do_not_qualify(self):
        self.append(self.parent, "turn_context", {**self.settings, "effort": None})
        with self.assertRaises(ValueError):
            self.call("prepare-probe", self.request)
        self.append(self.parent, "turn_context", self.settings)
        self.call("prepare-probe", self.request)
        self.script.write_text("changed guard")
        with self.assertRaises(ValueError):
            self.call("begin-probe")

    def test_modified_prepared_packet_never_returns_an_execution_override(self):
        self.call("prepare-probe", self.request)
        record = json.loads(self.record.read_text())
        record["native_arguments"]["model"] = "a different model"
        self.record.write_text(json.dumps(record))
        with self.assertRaises(ValueError):
            self.call("begin-probe")

    def test_encrypted_message_requires_an_attributed_exact_call_capture(self):
        self.request["display_required"] = False
        self.prepare_begin()
        request = self.completed()
        rows = [json.loads(line) for line in self.parent.read_text().splitlines()]
        call = rows[-2]["payload"]
        observed = json.loads(call["arguments"])
        call["arguments"] = json.dumps({**observed, "message": "gAAAAencrypted-native-message"})
        self.parent.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
        self.assertFalse(self.call("record-probe", request)["complete"])
        capture = self.home / "dispatch.json"
        capture.write_text(json.dumps({"call_id": "call1", "tool": "collaboration.spawn_agent",
            "arguments": observed, "observed_via": "native-tool-call", "source_ref": "fixture native invocation call1"}))
        self.assertTrue(self.call("record-probe", {**request, "dispatch_evidence": str(capture)})["complete"])

    def test_spawn_error_text_cannot_bind_an_older_same_named_child(self):
        self.prepare_begin()
        request = self.completed()
        rows = [json.loads(line) for line in self.parent.read_text().splitlines()]
        rows[-1]["payload"]["output"] = "Cannot create /root/client_canary: task already exists"
        self.parent.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
        self.assertFalse(self.call("record-probe", request)["execution_passed"])
        rows[-1]["payload"]["output"] = json.dumps({"task_name": "/root/client_canary"})
        self.parent.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
        child = [json.loads(line) for line in self.child.read_text().splitlines()]
        child[0]["payload"]["timestamp"] = "2020-01-01T00:00:00Z"
        self.child.write_text("\n".join(json.dumps(row) for row in child) + "\n")
        self.assertFalse(self.call("record-probe", request)["execution_passed"])

    def test_unphased_report_correction_is_never_misreported_as_first_pass(self):
        self.prepare_begin()
        request = self.completed({**self.report, "observed": "invalid extra field"})
        rows = [json.loads(line) for line in self.child.read_text().splitlines()]
        rows[-1]["payload"].pop("phase")
        self.child.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
        corrected = "```delegation-report\n" + json.dumps(self.report) + "\n```"
        self.append(self.child, "response_item", {"type": "message", "role": "assistant", "content": [{"text": corrected}]})
        self.append(self.child, "event_msg", {"type": "task_complete", "last_agent_message": corrected})
        with self.assertRaises(ValueError):
            self.call("record-probe", request)

    def test_later_parent_turn_can_reconcile_but_cannot_dispatch_stale_packet(self):
        self.prepare_begin()
        request = self.completed()
        self.append(self.parent, "turn_context", {**self.settings, "turn_id": str(uuid4())})
        self.assertTrue(self.call("record-probe", request)["execution_passed"])

    def test_workspace_edit_or_mutation_tool_cannot_pass_a_read_only_probe(self):
        self.prepare_begin()
        request = self.completed()
        (self.root / "unexpected.txt").write_text("a worker write")
        self.assertFalse(self.call("record-probe", request)["execution_passed"])
        (self.root / "unexpected.txt").unlink()
        self.append(self.child, "response_item", {"type": "custom_tool_call", "name": "apply_patch",
            "input": "*** Begin Patch\n*** End Patch", "call_id": "write"})
        self.assertFalse(self.call("record-probe", request)["execution_passed"])

    def test_setting_override_foreign_child_and_changed_protected_file_fail(self):
        self.prepare_begin()
        request = self.completed(settings={**self.settings, "turn_id": str(uuid4()), "model": "different-model"})
        result = self.call("record-probe", request)
        self.assertFalse(result["settings_preserved"])
        self.assertFalse(result["complete"])
        self.hook.write_text("modified")
        with self.assertRaises(ValueError):
            self.call("record-probe", request)

    def test_valid_display_requires_matching_child_role_and_prearmed_observer(self):
        self.prepare_begin()
        request = self.completed()
        record = json.loads(self.record.read_text())
        display = self.home / "display.json"
        value = {"client": "app", "parent_thread_id": self.parent_id, "child_thread_id": self.child_id,
                 "role": "Tester", "observed_label": "Tester", "observer_started_at": record["begun_at"] - 1,
                 "observed_at": record["begun_at"] + 1, "source": "habblaud"}
        snapshot = self.home / "snapshot.png"
        snapshot.write_bytes(b"\x89PNG\r\n\x1a\nfixture-image-bytes")
        value["snapshot"] = str(snapshot)
        display.write_text(json.dumps(value))
        result = self.call("record-probe", {**request, "display_evidence": str(display)})
        self.assertTrue(result["complete"])
        self.assertTrue(result["display_passed"])
        snapshot.write_bytes(b"changed-image")
        with self.assertRaises(ValueError):
            self.call("status-probe")
        display.write_text(json.dumps({**value, "child_thread_id": "other"}))
        with self.assertRaises(ValueError):
            self.call("record-probe", {**request, "display_evidence": str(display)})


if __name__ == "__main__":
    unittest.main()
