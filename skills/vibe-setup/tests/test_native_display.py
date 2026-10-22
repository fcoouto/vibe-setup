"""Native presentation metadata; no Habblaud server or account changes."""
import copy
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".codex/hooks/native_display.py"
PARENT = "11111111-1111-4111-8111-111111111111"
CHILD = "22222222-2222-4222-8222-222222222222"


class NativeDisplayTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.exists(), "native display adapter is not implemented")
        sys.path.insert(0, str(SCRIPT.parent))
        self.addCleanup(sys.path.remove, str(SCRIPT.parent))
        spec = importlib.util.spec_from_file_location("native_display", SCRIPT)
        self.adapter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.adapter)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / "codex"
        self.project = self.root / "project"
        records = self.project / ".codex-delegations"
        records.mkdir(parents=True)
        self.record = records / "reader.json"
        self.brief = dict(role="Reviewer", specialty="Unlisted specialty",
                          objective="Review supplied code.", context="Fixture only.",
                          instructions="Read only.", allowed_files=[], mutable_resources=[],
                          dependencies=[], acceptance=["Report findings."], checks=["Inspect code."],
                          read_only=True, budget=dict(minutes=1, attempts=1))
        self.record.write_text(json.dumps(self.brief))
        day = datetime.now(timezone.utc).strftime("%Y/%m/%d")
        self.rollout = self.home / "sessions" / day / f"rollout-fixture-{CHILD}.jsonl"
        self.rollout.parent.mkdir(parents=True)
        self.meta = dict(id=CHILD, cwd=str(self.project), source={"subagent": {"thread_spawn": {
            "parent_thread_id": PARENT, "agent_path": "/root/reader", "agent_role": None}}})
        self.write_meta()
        self.event = dict(hook_event_name="SubagentStart", session_id=PARENT,
                          agent_id=CHILD, agent_type="default", cwd=str(self.project),
                          model="preserved-model", permission_mode="default", turn_id="preserved-turn")

    def write_meta(self):
        self.rollout.write_text(json.dumps({"type": "session_meta", "payload": self.meta}) + "\n")

    def enrich(self, event=None, root=None):
        return self.adapter.enrich_event(self.event if event is None else event, self.home, root)

    def test_derives_role_from_bound_declaration_only_in_display_copy(self):
        original = copy.deepcopy(self.event)
        result = self.enrich()
        self.assertEqual(result, dict(original, agent_role="Reviewer", agent_type="Reviewer"))
        self.assertEqual(self.event, original)
        self.assertIsNone(self.meta["source"]["subagent"]["thread_spawn"]["agent_role"])
        self.assertEqual(json.loads(self.record.read_text()), self.brief)

    def test_present_hook_role_is_preserved_without_reading_declaration(self):
        for role in ("Native specialist", "", False, 7):
            with self.subTest(role=role), patch.object(self.adapter, "find_metadata", side_effect=AssertionError("must not calculate")):
                event = dict(self.event, agent_role=role)
                result = self.enrich(event)
                self.assertEqual(result["agent_role"], role)
                self.assertEqual(result["agent_type"], role if isinstance(role, str) and role.strip() else "default")

    def test_null_hook_role_is_absent_and_later_native_role_wins_without_cache(self):
        self.assertEqual(self.enrich(dict(self.event, agent_role=None))["agent_role"], "Reviewer")
        self.meta["source"]["subagent"]["thread_spawn"]["agent_role"] = "Native specialist"
        self.write_meta()
        with patch.object(self.adapter.subagents, "read_brief", side_effect=AssertionError("must not derive")):
            result = self.enrich()
        self.assertEqual(result["agent_role"], "Native specialist")
        self.assertEqual(result["agent_type"], "Native specialist")
        self.assertEqual(json.loads(self.rollout.read_text())["payload"], self.meta)

    def test_bad_child_parent_task_or_cwd_never_borrows_a_role(self):
        variants = [dict(self.meta, id=PARENT), dict(self.meta, cwd=str(self.root / "other"))]
        for field, value in (("parent_thread_id", CHILD), ("agent_path", "/root/../reader"),
                             ("agent_path", "/root/reader/../../escape"), ("agent_path", "reader")):
            meta = copy.deepcopy(self.meta)
            meta["source"]["subagent"]["thread_spawn"][field] = value
            variants.append(meta)
        for meta in variants:
            self.meta = meta
            self.write_meta()
            self.assertEqual(self.enrich(), self.event)

    def test_missing_invalid_or_unsafe_declaration_leaves_event_unchanged(self):
        for brief in (dict(self.brief, role="Wizard"), dict(self.brief, role="reviewer"),
                      dict(self.brief, read_only=False), {k:v for k,v in self.brief.items() if k != "role"}):
            self.record.write_text(json.dumps(brief))
            self.assertEqual(self.enrich(), self.event)
        self.record.unlink()
        self.assertEqual(self.enrich(), self.event)
        outside = self.root / "outside.json"
        outside.write_text(json.dumps(self.brief))
        self.record.symlink_to(outside)
        self.assertEqual(self.enrich(), self.event)

    def test_rollout_is_bounded_regular_unambiguous_and_inside_account(self):
        for raw in (b'{broken', b'x' * (128 * 1024 + 1), b'{"type":"message","payload":{}}\n'):
            self.rollout.write_bytes(raw)
            self.assertEqual(self.enrich(), self.event)
        self.rollout.unlink()
        outside = self.root / "outside.jsonl"
        outside.write_text(json.dumps({"type":"session_meta", "payload":self.meta}) + "\n")
        self.rollout.symlink_to(outside)
        self.assertEqual(self.enrich(), self.event)
        self.rollout.unlink()
        os.mkfifo(self.rollout)
        self.assertEqual(self.enrich(), self.event)
        self.rollout.unlink()
        self.write_meta()
        duplicate = self.rollout.with_name(f"rollout-duplicate-{CHILD}.jsonl")
        duplicate.write_bytes(self.rollout.read_bytes())
        self.assertEqual(self.enrich(), self.event)

    def test_explicit_harness_root_does_not_search_nearer_git_roots(self):
        service = self.project / "service"
        service.mkdir()
        self.event["cwd"] = str(service)
        self.meta["cwd"] = str(service)
        self.write_meta()
        self.assertEqual(self.enrich(), self.event)
        self.assertEqual(self.enrich(root=self.project)["agent_role"], "Reviewer")
        self.assertEqual(self.enrich(root=self.root / "unrelated"), self.event)

    def test_two_workers_resolve_their_own_roles(self):
        second = "33333333-3333-4333-8333-333333333333"
        self.record.with_name("builder.json").write_text(json.dumps(dict(self.brief, role="Builder")))
        meta = copy.deepcopy(self.meta)
        meta["id"] = second
        meta["source"]["subagent"]["thread_spawn"]["agent_path"] = "/root/builder"
        self.rollout.with_name(f"rollout-fixture-{second}.jsonl").write_text(json.dumps({"type":"session_meta", "payload":meta}) + "\n")
        self.assertEqual(self.enrich()["agent_role"], "Reviewer")
        self.assertEqual(self.enrich(dict(self.event, agent_id=second))["agent_role"], "Builder")

    def test_non_start_events_and_malformed_ids_are_unchanged(self):
        for update in ({"hook_event_name":"PermissionRequest"}, {"hook_event_name":"PreToolUse"},
                       {"agent_id":"../escape"}, {"agent_id":PARENT}, {"session_id":None}):
            event = dict(self.event, **update)
            self.assertEqual(self.enrich(event), event)

    def test_wrapper_preserves_original_hook_streams_status_and_input(self):
        target = self.root / "original.py"
        captured = self.root / "captured"
        target.write_text("import sys\nfrom pathlib import Path\nPath(sys.argv[1]).write_bytes(sys.stdin.buffer.read())\nsys.stdout.write('original stdout')\nsys.stderr.write('original stderr')\nraise SystemExit(7)\n")
        command = [sys.executable, '-B', str(SCRIPT), '--codex-home', str(self.home), '--', sys.executable, '-B', str(target), str(captured)]
        for raw in (b'{bad json', b'x' * (128 * 1024 + 10), json.dumps(dict(self.event, hook_event_name="PermissionRequest")).encode()):
            result = subprocess.run(command, input=raw, capture_output=True, timeout=3)
            self.assertEqual(result.returncode, 7)
            self.assertEqual(result.stdout, b'original stdout')
            self.assertEqual(result.stderr, b'original stderr')
            self.assertEqual(captured.read_bytes(), raw)
        subprocess.run(command, input=json.dumps(self.event).encode(), capture_output=True, timeout=3)
        self.assertEqual(json.loads(captured.read_bytes())["agent_type"], "Reviewer")

    def test_wrapper_preserves_signals_and_early_exit_with_oversized_input(self):
        command = [sys.executable, '-B', str(SCRIPT), '--', sys.executable, '-B', '-c']
        result = subprocess.run(command + ['import os,signal; os.kill(os.getpid(),signal.SIGTERM)'],
                                input=b'{}', capture_output=True, timeout=3)
        self.assertEqual(result.returncode, -signal.SIGTERM)
        result = subprocess.run(command + ['raise SystemExit(7)'],
                                input=b'x' * (1024 * 1024), capture_output=True, timeout=3)
        self.assertEqual(result.returncode, 7)
        self.assertEqual(result.stderr, b'')
