"""Startup behavior against disposable Git repositories; no client/account changes."""
import contextlib
import fcntl
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

HELPER = Path(__file__).resolve().parents[1] / "workflow.py"


class WorkflowFixture(unittest.TestCase):
    def setUp(self):
        self.assertTrue(HELPER.exists(), "Phase 1 helper has not been implemented")
        spec = importlib.util.spec_from_file_location("workflow", HELPER)
        self.workflow = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.workflow)
        self.temp = tempfile.TemporaryDirectory(prefix="vibe-startup-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        env = patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": os.devnull,
                                    "GIT_CONFIG_NOSYSTEM": "1"})
        env.start()
        self.addCleanup(env.stop)
        self.source = self.make_repo("source")
        self.target = self.home / "task worktree"
        self.request = {"task_id": str(uuid4()), "worktree": str(self.target),
                        "branch": "task/example", "base": "main"}

    def git(self, root, *args):
        return subprocess.run(["git", "-C", str(root), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def make_repo(self, name):
        root = self.home / name
        root.mkdir()
        self.git(root, "init", "-q", "-b", "main")
        self.git(root, "config", "user.name", "Fixture")
        self.git(root, "config", "user.email", "fixture@example.invalid")
        (root / "app.txt").write_text("baseline\n")
        self.git(root, "add", "app.txt")
        self.git(root, "commit", "-qm", "fixture")
        return root

    def policy(self, text, root=None):
        path = (root or self.source) / ".codex/vibe-workflow.toml"
        path.parent.mkdir(exist_ok=True)
        path.write_text(text)
        return path

    def snapshot(self, root):
        return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*")
                if p.is_file() and not p.is_symlink()}

    def manual_worktree(self):
        self.git(self.source, "worktree", "add", "-b", self.request["branch"],
                 str(self.target), "main")


class WorkflowTests(WorkflowFixture):
    def test_default_policy_creates_worktree_and_preserves_explicit_opt_out(self):
        self.assertTrue(self.workflow.load_policy(self.source))
        policy = self.policy('schema_version = 1\n[task_lifecycle]\nenabled = false\n')
        before = self.snapshot(self.source)
        result = self.workflow.start_task(self.source, self.request)
        self.assertEqual(result["implementation"], "disabled")
        self.assertFalse(self.target.exists())
        self.assertEqual(before, self.snapshot(self.source))
        self.assertFalse(self.workflow.load_policy(self.source))
        self.assertIn("false", policy.read_text())

    def test_policy_rejects_malformed_unknown_owned_and_wrong_types(self):
        for text in ('[', 'schema_version = 2', 'schema_version = true',
                     '[task_lifecycle]\nenabled = "false"',
                     '[task_lifecycle]\nenabled = true\nenabled = false',
                     '[task_lifecycle]\nenabld = false', 'task_lifecycle = false'):
            with self.subTest(text=text):
                self.policy(text)
                with self.assertRaises(ValueError):
                    self.workflow.load_policy(self.source)

    def test_unrelated_policy_values_are_not_rewritten(self):
        path = self.policy('schema_version = 1\n[editor]\nindent = 4\n')
        before = path.read_bytes()
        self.assertTrue(self.workflow.load_policy(self.source))
        self.assertEqual(path.read_bytes(), before)

    def test_symlink_policy_is_refused(self):
        outside = self.home / "outside.toml"
        outside.write_text('[task_lifecycle]\nenabled = false\n')
        (self.source / ".codex").mkdir()
        (self.source / ".codex/vibe-workflow.toml").symlink_to(outside)
        with self.assertRaises(ValueError):
            self.workflow.load_policy(self.source)

    def test_nested_inspection_is_read_only_and_never_means_setup_complete(self):
        nested = self.source / "web/app"
        nested.mkdir(parents=True)
        (nested / "AGENTS.md").write_text("Keep existing settings.\n")
        (self.source / "app.txt").write_text("user edit\n")
        self.git(self.source, "add", "app.txt")
        before = self.snapshot(self.source)
        result = self.workflow.inspect_project(nested, ["app", "vscode"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["implementation"], "inspection_only")
        self.assertEqual(result["project"]["root"], str(self.source))
        self.assertEqual(result["project"]["requested_root"], str(nested))
        self.assertIn(str(nested / "AGENTS.md"), result["project"]["instructions"])
        self.assertTrue(result["project"]["changes"])
        self.assertEqual(before, self.snapshot(self.source))

    def test_umbrella_requires_explicit_repository_selection(self):
        other = self.make_repo("other")
        before = self.snapshot(self.home)
        result = self.workflow.inspect_project(self.home, ["app"])
        self.assertEqual(result["status"], "action_required")
        self.assertEqual(set(result["repositories"]), {str(self.source), str(other)})
        self.assertEqual(before, self.snapshot(self.home))

    def test_inspection_redacts_remote_credentials_and_does_not_claim_write_access(self):
        self.git(self.source, "remote", "add", "origin",
                 "https://account:secret-token@example.invalid/org/repo.git?token=secret-query")
        result = self.workflow.inspect_project(self.source, ["app"])
        rendered = json.dumps(result)
        self.assertNotIn("secret-token", rendered)
        self.assertNotIn("secret-query", rendered)
        self.assertEqual(result["access"]["remotes"][0]["transport"], "https")
        self.assertEqual(result["access"]["pr_write"], "unverified")
        self.assertEqual(result["access"]["commit_identity"]["email"], "fixture@example.invalid")

    def test_missing_identity_and_multiple_remotes_request_decisions_without_login(self):
        self.git(self.source, "config", "--unset", "user.email")
        for name in ("origin", "upstream"):
            self.git(self.source, "remote", "add", name, "git@example.invalid:org/repo.git")
        result = self.workflow.inspect_project(self.source, [])
        codes = {item["code"] for item in result["pending_user_actions"]}
        self.assertIn("commit_identity", codes)
        self.assertIn("select_remote", codes)
        self.assertEqual(result["status"], "ok")

    def test_start_creates_registered_worktree_and_explicit_worker_context(self):
        (self.source / "app.txt").write_text("unrelated edit\n")
        self.git(self.source, "add", "app.txt")
        index = (self.source / ".git/index").read_bytes()
        config = (self.source / ".git/config").read_bytes()
        result = self.workflow.start_task(self.source, self.request)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["implementation"], "worktree_verified")
        self.assertEqual(result["context"]["command_cwd"], str(self.target))
        self.assertEqual(result["context"]["worker_cwd"], str(self.target))
        self.assertEqual((self.target / "app.txt").read_text(), "baseline\n")
        self.assertEqual((self.source / "app.txt").read_text(), "unrelated edit\n")
        self.assertEqual((self.source / ".git/index").read_bytes(), index)
        self.assertEqual((self.source / ".git/config").read_bytes(), config)
        self.assertEqual(self.git(self.target, "branch", "--show-current"), "task/example")
        self.assertTrue(Path(result["evidence_ref"]).is_file())

    def test_start_rerun_rechecks_git_and_does_not_duplicate_or_rewrite(self):
        first = self.workflow.start_task(self.source, self.request)
        before = self.snapshot(self.home)
        second = self.workflow.start_task(self.source, self.request)
        self.assertEqual(second["status"], "ok")
        self.assertEqual(second["changes"], [])
        self.assertEqual(first["evidence_ref"], second["evidence_ref"])
        self.assertEqual(before, self.snapshot(self.home))
        self.git(self.target, "checkout", "-qb", "other")
        self.assertEqual(self.workflow.start_task(self.source, self.request)["status"], "blocked")

    def test_primary_checkout_and_nested_worktree_directory_are_refused(self):
        with self.assertRaises(ValueError):
            self.workflow.verify_worktree(self.source, self.source, "main")
        self.manual_worktree()
        nested = self.target / "nested"
        nested.mkdir()
        with self.assertRaises(ValueError):
            self.workflow.verify_worktree(self.source, nested, "task/example")

    def test_wrong_branch_foreign_repository_and_unregistered_copy_are_refused(self):
        self.manual_worktree()
        with self.assertRaises(ValueError):
            self.workflow.verify_worktree(self.source, self.target, "wrong")
        other = self.make_repo("other")
        with self.assertRaises(ValueError):
            self.workflow.verify_worktree(other, self.target, "task/example")
        copied = self.home / "copied"
        copied.mkdir()
        (copied / ".git").write_bytes((self.target / ".git").read_bytes())
        with self.assertRaises(ValueError):
            self.workflow.verify_worktree(self.source, copied, "task/example")

    def test_symlink_destination_or_ancestor_cannot_redirect_startup(self):
        self.manual_worktree()
        alias = self.home / "alias"
        alias.symlink_to(self.target, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.workflow.verify_worktree(self.source, alias, "task/example")
        parent = self.home / "alias-parent"
        parent.symlink_to(self.home, target_is_directory=True)
        request = dict(self.request, worktree=str(parent / "new"))
        self.assertEqual(self.workflow.start_task(self.source, request)["status"], "blocked")

    def test_existing_worktree_requires_explicit_adoption_then_binds_one_task(self):
        self.manual_worktree()
        self.assertEqual(self.workflow.start_task(self.source, self.request)["status"], "action_required")
        request = dict(self.request, create=False, adopt_existing=True)
        result = self.workflow.start_task(self.source, request)
        self.assertEqual(result["status"], "ok")
        other = dict(request, task_id=str(uuid4()))
        self.assertEqual(self.workflow.start_task(self.source, other)["status"], "blocked")

    def test_native_failure_uses_git_fallback_and_native_success_is_verified(self):
        # Native creation runs outside Python. An absent destination uses Git fallback.
        self.assertFalse(self.target.exists())
        self.assertEqual(self.workflow.start_task(self.source, self.request)["status"], "ok")
        second = dict(self.request, task_id=str(uuid4()), branch="task/native",
                      worktree=str(self.home / "native"), create=False, adopt_existing=True)
        self.git(self.source, "worktree", "add", "-b", "task/native", second["worktree"], "main")
        result = self.workflow.start_task(self.source, second)
        self.assertEqual(result["context"]["worker_cwd"], second["worktree"])

    def test_absent_worktree_in_verify_mode_requests_manual_creation(self):
        result = self.workflow.start_task(self.source, dict(self.request, create=False))
        self.assertEqual(result["status"], "action_required")
        self.assertFalse(self.target.exists())
        self.assertIn("worktree", json.dumps(result["pending_user_actions"]))
        self.manual_worktree()
        result = self.workflow.start_task(self.source, dict(self.request, create=False, adopt_existing=True))
        self.assertEqual(result["status"], "ok")

    def test_invalid_request_or_base_never_creates_branch_or_worktree(self):
        for update in ({"task_id": "../../outside"}, {"branch": "--detach"},
                       {"base": "absent"}, {"verified": True}, {"create": "yes"},
                       {"worktree": "relative"}, {"worktree": str(self.source / "nested")}):
            with self.subTest(update=update):
                result = self.workflow.start_task(self.source, dict(self.request, **update))
                self.assertEqual(result["status"], "blocked")
                self.assertFalse(self.target.exists())
                self.assertEqual(self.git(self.source, "branch", "--format=%(refname:short)"), "main")

    def test_wrong_base_and_detached_worktrees_cannot_be_adopted(self):
        self.manual_worktree()
        self.git(self.source, "checkout", "--orphan", "unrelated")
        self.git(self.source, "commit", "-qm", "unrelated root")
        result = self.workflow.start_task(self.source, dict(self.request, base="unrelated", adopt_existing=True))
        self.assertEqual(result["status"], "blocked")
        self.git(self.target, "checkout", "--detach")
        with self.assertRaises(ValueError):
            self.workflow.verify_worktree(self.source, self.target, "task/example")

    def test_start_refuses_destination_nested_inside_another_repository(self):
        other = self.make_repo("other")
        before = self.snapshot(other)
        for target in (other / "nested-task", other / "missing/parent/task", other / ".git/task"):
            with self.subTest(target=target):
                request = dict(self.request, worktree=str(target))
                result = self.workflow.start_task(self.source, request)
                self.assertEqual(result["status"], "blocked")
                self.assertFalse(target.exists())
                self.assertEqual(before, self.snapshot(other))

    def test_repository_environment_cannot_redirect_git_commands(self):
        other = self.make_repo("other")
        with patch.dict(os.environ, {"GIT_DIR": str(other / ".git"), "GIT_WORK_TREE": str(other)}):
            result = self.workflow.start_task(self.source, self.request)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["context"]["common_dir"], str(self.source / ".git"))
        self.assertEqual(self.git(other, "branch", "--format=%(refname:short)"), "main")

    def test_failed_creation_preserves_intent_and_recovers_after_manual_creation(self):
        real_git = self.workflow.git

        def fail_create(root, *args, **kwargs):
            if args[:2] == ("worktree", "add"):
                return subprocess.CompletedProcess(args, 1, "", "failure")
            return real_git(root, *args, **kwargs)

        with patch.object(self.workflow, "git", side_effect=fail_create):
            failed = self.workflow.start_task(self.source, self.request)
        self.assertEqual(failed["status"], "action_required")
        self.assertFalse(self.target.exists())
        record = self.source / ".git/vibe-setup/tasks" / f"{self.request['task_id']}.json"
        self.assertEqual(json.loads(record.read_text())["state"], "pending")
        self.manual_worktree()
        resumed = self.workflow.start_task(self.source, dict(self.request, create=False))
        self.assertEqual(resumed["status"], "ok")
        self.assertEqual(json.loads(record.read_text())["state"], "verified")

    def test_lock_contention_does_not_create_another_worktree(self):
        directory = self.source / ".git/vibe-setup"
        directory.mkdir()
        with (directory / "start.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.workflow.start_task(self.source, self.request)
        self.assertEqual(result["status"], "action_required")
        self.assertFalse(self.target.exists())

    def test_symlink_state_directory_never_writes_to_external_location(self):
        outside = self.home / "state"
        outside.mkdir()
        (self.source / ".git/vibe-setup").symlink_to(outside, target_is_directory=True)
        result = self.workflow.start_task(self.source, self.request)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse(self.target.exists())

    def test_unknown_or_mismatched_record_is_not_reinterpreted_as_verified(self):
        self.workflow.start_task(self.source, self.request)
        path = self.source / ".git/vibe-setup/tasks" / f"{self.request['task_id']}.json"
        original = json.loads(path.read_text())
        for update in ({"schema_version": True}, {"task_id": str(uuid4())},
                       {"base_commit": "--all"}):
            with self.subTest(update=update):
                path.write_text(json.dumps(dict(original, **update)))
                self.assertEqual(self.workflow.start_task(self.source, self.request)["status"], "blocked")

    def test_effective_commit_identity_reports_environment_without_changing_config(self):
        before = (self.source / ".git/config").read_bytes()
        with patch.dict(os.environ, {"GIT_AUTHOR_NAME": "Alternate", "GIT_AUTHOR_EMAIL": "alternate@example.invalid"}):
            result = self.workflow.inspect_project(self.source, [])
        self.assertEqual(result["access"]["effective_author"]["email"], "alternate@example.invalid")
        self.assertEqual(result["access"]["commit_identity"]["email"], "fixture@example.invalid")
        self.assertEqual((self.source / ".git/config").read_bytes(), before)

    def test_cli_returns_structured_status_and_rejects_duplicate_json_fields(self):
        process = subprocess.run([sys.executable, "-B", str(HELPER), "start", str(self.source)],
                                 input=json.dumps(self.request), capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr + process.stdout)
        self.assertEqual(json.loads(process.stdout)["implementation"], "worktree_verified")
        for payload in ('[]', '{"task_id":"one","task_id":"two"}'):
            with self.subTest(payload=payload), patch("sys.stdin", io.StringIO(payload)), contextlib.redirect_stdout(io.StringIO()) as out:
                code = self.workflow.main(["start", str(self.source)])
                self.assertEqual(code, 3)
                self.assertEqual(json.loads(out.getvalue())["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
