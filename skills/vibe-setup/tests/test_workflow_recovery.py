"""Recoverable setup against disposable worktrees, including interrupted writes."""
import contextlib
import fcntl
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from test_workflow_setup import WorkflowFixture


class RecoveryTests(WorkflowFixture):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.workflow.start_task(self.source, self.request)["status"], "ok")
        self.task = {key: self.request[key] for key in ("task_id", "worktree")}
        self.state = Path(self.workflow.repository(self.target)["common_dir"]) / "vibe-setup"

    def plan(self):
        return self.workflow.plan_setup(self.task)

    def apply(self, plan=None):
        return self.workflow.apply_setup(plan or self.plan(), self.task)

    def resume(self, plan):
        return self.workflow.resume_operation(self.target, plan["operation_id"])

    def cli(self, arguments, payload=""):
        stream = io.StringIO()
        with patch("sys.stdin", io.StringIO(payload)), contextlib.redirect_stdout(stream):
            code = self.workflow.main(arguments)
        return code, json.loads(stream.getvalue())

    def test_preview_does_not_write_bytecode_to_reviewed_package(self):
        package = self.home / "reviewed package"
        shutil.copytree(Path(self.workflow.__file__).parent, package,
                        ignore=shutil.ignore_patterns("__pycache__"))
        before = self.snapshot(package)
        run = subprocess.run([sys.executable, str(package / "workflow.py"), "inspect", str(self.target),
                              "--task-id", self.task["task_id"]], capture_output=True, text=True, timeout=15)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(before, self.snapshot(package))

    def test_worktree_change_after_last_write_cannot_mark_operation_complete(self):
        plan = self.plan()
        original = self.workflow.replace_setup_file
        def change_branch(path, *args, **kwargs):
            original(path, *args, **kwargs)
            if path == self.target / ".codex/vibe-workflow.toml":
                self.git(self.target, "checkout", "-qb", "changed-after-write")
        with patch.object(self.workflow, "replace_setup_file", side_effect=change_branch):
            response = self.apply(plan)
        self.assertEqual(response["status"], "blocked")
        record = json.loads(Path(response["evidence_ref"]).read_text())
        self.assertEqual(record["state"], "pending")
        self.git(self.target, "checkout", "-q", self.request["branch"])
        self.assertEqual(self.resume(plan)["status"], "ok")

    def test_preview_is_read_only_and_apply_is_idempotent(self):
        before = self.snapshot(self.home)
        plan = self.plan()
        self.assertEqual(self.snapshot(self.home), before)
        applied = self.apply(plan)
        self.assertEqual(applied["status"], "ok", applied)
        self.assertEqual(applied["implementation"], "setup_configured")
        self.assertEqual(applied["delivery"], "not_checked")
        self.assertEqual(len(applied["changes"]), 9)
        first = self.snapshot(self.home)
        self.assertEqual(self.apply(plan)["status"], "ok")
        self.assertEqual(self.resume(plan)["status"], "ok")
        self.assertEqual(first, self.snapshot(self.home))
        fresh = self.apply()
        self.assertEqual(fresh["changes"], [])

    def test_custom_config_hooks_permissions_and_policy_survive_without_secret_snapshots(self):
        config = self.target / ".codex/config.toml"
        config.parent.mkdir()
        original = b'model = "chosen-model"\nmodel_reasoning_effort = "high"\napproval_policy = "on-request"\nsecret = "fixture-sensitive-value"\n'
        config.write_bytes(original)
        config.chmod(0o640)
        hooks = self.target / ".codex/hooks.json"
        custom = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo fixture-hook-secret"}]}]}}
        hooks.write_text(json.dumps(custom))
        policy = self.policy('schema_version = 1\n[task_lifecycle]\nenabled = false\n', self.target)
        policy_bytes = policy.read_bytes()
        plan = self.plan()
        response = self.apply(plan)
        self.assertEqual(response["status"], "ok", response)
        self.assertTrue(config.read_bytes().startswith(original))
        self.assertEqual(config.stat().st_mode & 0o777, 0o640)
        self.assertEqual(json.loads(hooks.read_text())["hooks"]["Stop"], custom["hooks"]["Stop"])
        self.assertEqual(policy.read_bytes(), policy_bytes)
        recorded = json.dumps(plan) + json.dumps(response) + "".join(p.read_text() for p in self.state.rglob("*.json"))
        self.assertNotIn("fixture-sensitive-value", recorded)
        self.assertNotIn("fixture-hook-secret", recorded)

    def test_stale_plan_changes_nothing(self):
        plan = self.plan()
        (self.target / ".gitignore").write_text("human edit\n")
        before = self.snapshot(self.home)
        self.assertEqual(self.apply(plan)["status"], "blocked")
        self.assertEqual(self.snapshot(self.home), before)

    def test_malformed_or_injected_plan_is_rejected_without_writes(self):
        plan = self.plan()
        variants = [None, [], {**plan, "schema_version": True},
                    {**plan, "files": {"../outside": {"before": None, "after": None}}},
                    {**plan, "verified": True}]
        for candidate in variants:
            with self.subTest(candidate=candidate):
                before = self.snapshot(self.home)
                response = self.workflow.apply_setup(candidate, self.task)
                self.assertEqual(response["status"], "blocked", response)
                self.assertEqual(self.snapshot(self.home), before)

    def test_interruptions_before_and_after_every_owned_write_resume_same_operation(self):
        plan = self.plan()
        original = self.workflow.replace_setup_file
        for relative in plan["files"]:
            for when in ("before", "after"):
                with self.subTest(path=relative, when=when):
                    # Reset only this disposable fixture; never roll back the product's files.
                    for path in reversed(sorted(self.target.rglob("*"))):
                        if path.name == ".git" or path.name == "app.txt":
                            continue
                        if path.is_file():
                            path.unlink()
                        elif path.is_dir():
                            path.rmdir()
                    for record in (self.state / "operations").glob("*.json"):
                        record.unlink()
                    plan = self.plan()
                    def interrupt(path, *args, **kwargs):
                        matches = path == self.target / relative
                        if matches and when == "before":
                            raise OSError("fixture interruption")
                        original(path, *args, **kwargs)
                        if matches and when == "after":
                            raise OSError("fixture interruption")
                    with patch.object(self.workflow, "replace_setup_file", side_effect=interrupt):
                        response = self.apply(plan)
                    self.assertEqual(response["status"], "action_required", response)
                    self.assertTrue(Path(response["evidence_ref"]).is_file())
                    resumed = self.resume(plan)
                    self.assertEqual(resumed["status"], "ok", resumed)
                    self.assertEqual(self.plan()["files"], {name: {"before": entry["after"], "after": entry["after"]}
                                                          for name, entry in plan["files"].items()})

    def test_foreign_edit_after_interruption_is_never_overwritten(self):
        plan = self.plan()
        original = self.workflow.replace_setup_file
        def interrupt(path, *args, **kwargs):
            original(path, *args, **kwargs)
            raise OSError("fixture interruption")
        with patch.object(self.workflow, "replace_setup_file", side_effect=interrupt):
            self.assertEqual(self.apply(plan)["status"], "action_required")
        first = next(iter(plan["files"]))
        (self.target / first).write_text("human customization after interruption\n")
        before = self.snapshot(self.home)
        self.assertEqual(self.resume(plan)["status"], "blocked")
        self.assertEqual(before, self.snapshot(self.home))

    def test_lock_and_pending_operation_prevent_competing_setup(self):
        plan = self.plan()
        lock_path = self.state / "setup.lock"
        with lock_path.open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(self.apply(plan)["status"], "action_required")
        with patch.object(self.workflow, "replace_setup_file", side_effect=OSError):
            self.assertEqual(self.apply(plan)["status"], "action_required")
        response = self.apply(self.plan())
        self.assertEqual(response["status"], "action_required", response)
        self.assertIn(plan["operation_id"], response["next_action"])
        self.assertEqual(self.resume(plan)["status"], "ok")

    def test_conflicts_nonregular_and_symlink_targets_stop_before_writes(self):
        config = self.target / ".codex/config.toml"
        config.parent.mkdir()
        for content in ('[hooks]\nsecret="fixture-config-secret"\n', '[agents]\nenabled=false\n'):
            config.write_text(content)
            before = self.snapshot(self.home)
            code, response = self.cli(["inspect", str(self.target), "--task-id", self.task["task_id"]])
            self.assertEqual(code, 3)
            self.assertNotIn("fixture-config-secret", json.dumps(response))
            self.assertEqual(before, self.snapshot(self.home))
        config.unlink()
        config.symlink_to(self.source / "app.txt")
        with self.assertRaises(ValueError):
            self.plan()
        config.unlink()
        os.mkfifo(config)
        with self.assertRaises(ValueError):
            self.plan()

    def test_changed_binding_branch_head_and_package_stop_recovery(self):
        plan = self.plan()
        self.git(self.target, "checkout", "-qb", "unrelated")
        self.assertEqual(self.apply(plan)["status"], "blocked")
        self.git(self.target, "checkout", "-q", self.request["branch"])
        self.git(self.target, "commit", "--allow-empty", "-qm", "new head")
        self.assertEqual(self.apply(plan)["status"], "blocked")
        plan = self.plan()
        with patch.object(self.workflow, "replace_setup_file", side_effect=OSError):
            self.apply(plan)
        with patch.object(self.workflow, "package_digest", return_value="0" * 64):
            self.assertEqual(self.resume(plan)["status"], "blocked")
        self.assertEqual(self.resume(plan)["status"], "ok")

    def test_journal_failure_after_file_write_recovers_without_rewriting_file(self):
        plan = self.plan()
        original = self.workflow.write_record
        count = 0
        def interrupt(path, record):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("journal update interrupted")
            original(path, record)
        with patch.object(self.workflow, "write_record", side_effect=interrupt):
            response = self.apply(plan)
        self.assertEqual(response["status"], "action_required")
        first = self.target / next(iter(plan["files"]))
        before = first.stat().st_mtime_ns
        self.assertEqual(self.resume(plan)["status"], "ok")
        self.assertEqual(first.stat().st_mtime_ns, before)

    def test_initial_intent_failure_cannot_write_recipe_files(self):
        plan = self.plan()
        before = self.snapshot(self.target)
        with patch.object(self.workflow, "write_record", side_effect=OSError):
            self.assertEqual(self.apply(plan)["status"], "action_required")
        self.assertEqual(before, self.snapshot(self.target))
        self.assertEqual(self.apply(plan)["status"], "ok")

    def test_process_exit_with_complete_temporary_file_resumes(self):
        plan = self.plan()
        script = """import json, os, sys
sys.path.insert(0, sys.argv[1])
import workflow
request = json.load(sys.stdin)
original = os.replace
def crash(source, target):
    if str(target).endswith('/.codex/hooks/subagents.py'):
        os._exit(77)
    return original(source, target)
workflow.os.replace = crash
workflow.apply_setup(request['plan'], request['task'])
"""
        run = subprocess.run([sys.executable, "-B", "-c", script, str(Path(self.workflow.__file__).parent)],
                             input=json.dumps({"plan": plan, "task": self.task}), text=True,
                             capture_output=True, timeout=15)
        self.assertEqual(run.returncode, 77, run.stderr)
        temporary = self.workflow.setup_temporary(self.target / ".codex/hooks/subagents.py", plan["operation_id"])
        self.assertTrue(temporary.is_file())
        self.assertEqual(self.resume(plan)["status"], "ok")
        self.assertFalse(temporary.exists())

    def test_unknown_temporary_and_customized_managed_files_are_preserved(self):
        plan = self.plan()
        with patch.object(self.workflow, "replace_setup_file", side_effect=OSError):
            self.apply(plan)
        path = self.target / ".codex/hooks/subagents.py"
        path.parent.mkdir(parents=True)
        temporary = self.workflow.setup_temporary(path, plan["operation_id"])
        temporary.write_bytes(b"partial or foreign content")
        before = self.snapshot(self.home)
        self.assertEqual(self.resume(plan)["status"], "blocked")
        self.assertEqual(before, self.snapshot(self.home))
        temporary.unlink()
        self.assertEqual(self.resume(plan)["status"], "ok")
        path.write_text("# customized guard\n")
        before = self.snapshot(self.home)
        with self.assertRaises(ValueError):
            self.plan()
        self.assertEqual(before, self.snapshot(self.home))

    def test_changed_permission_and_completed_file_removal_stop_recovery(self):
        plan = self.plan()
        self.assertEqual(self.apply(plan)["status"], "ok")
        path = self.target / ".codex/config.toml"
        path.chmod(0o644)
        before = self.snapshot(self.home)
        self.assertEqual(self.resume(plan)["status"], "blocked")
        self.assertEqual(before, self.snapshot(self.home))
        path.chmod(0o600)
        path.unlink()
        self.assertEqual(self.resume(plan)["status"], "blocked")
        self.assertFalse(path.exists())

    def test_primary_and_unbound_worktree_cannot_apply_setup(self):
        plan = self.plan()
        primary = {**self.task, "worktree": str(self.source)}
        self.assertEqual(self.workflow.apply_setup(plan, primary)["status"], "blocked")
        self.assertEqual(self.workflow.resume_operation(self.source, plan["operation_id"])["status"], "action_required")
        task_file = self.state / "tasks" / f"{self.task['task_id']}.json"
        task_file.unlink()
        before = self.snapshot(self.target)
        self.assertNotEqual(self.apply(plan)["status"], "ok")
        self.assertEqual(before, self.snapshot(self.target))

    def test_installer_git_timeout_returns_sanitized_json_without_recipe_writes(self):
        plan = self.plan()
        with patch.object(self.workflow, "replace_setup_file", side_effect=OSError):
            self.apply(plan)
        original = subprocess.run
        def timeout(*args, **kwargs):
            if kwargs.get("timeout") == 5:
                raise subprocess.TimeoutExpired(["fixture-sensitive-command"], 5,
                                                output="fixture-sensitive-output")
            return original(*args, **kwargs)
        requests = [(["inspect", str(self.target), "--task-id", self.task["task_id"]], ""),
                    (["apply", str(self.target)], json.dumps({"task_id": self.task["task_id"], "plan": plan})),
                    (["resume", str(self.target)], json.dumps({"operation_id": plan["operation_id"]}))]
        before = self.snapshot(self.home)
        for arguments, payload in requests:
            with self.subTest(operation=arguments[0]), patch("subprocess.run", side_effect=timeout):
                code, response = self.cli(arguments, payload)
                self.assertEqual(code, 3)
                self.assertEqual(response["status"], "blocked")
                self.assertIn("timed out", response["next_action"])
                self.assertNotIn("fixture-sensitive", json.dumps(response))
                self.assertEqual(before, self.snapshot(self.home))
        self.assertEqual(self.resume(plan)["status"], "ok")

    def test_cli_preview_apply_resume_and_invalid_requests(self):
        code, response = self.cli(["inspect", str(self.target), "--task-id", self.task["task_id"], "--client", "app"])
        self.assertEqual(code, 0)
        self.assertEqual(response["implementation"], "inspection_only")
        self.assertEqual(response["clients"], {"app": "not_tested"})
        plan = response["setup_plan"]
        request = json.dumps({"task_id": self.task["task_id"], "plan": plan})
        code, response = self.cli(["apply", str(self.target)], request)
        self.assertEqual(code, 0, response)
        code, response = self.cli(["resume", str(self.target)], json.dumps({"operation_id": plan["operation_id"]}))
        self.assertEqual(code, 0, response)
        for payload in ('[]', '{}', '{"task_id":1,"task_id":2}', 'x' * 65537):
            self.assertEqual(self.cli(["apply", str(self.target)], payload)[0], 3)
        self.assertEqual(self.workflow.resume_operation(self.target, "../bad")["status"], "blocked")
        self.assertEqual(self.workflow.resume_operation(self.target, plan["operation_id"], {"verified": True})["status"], "blocked")
