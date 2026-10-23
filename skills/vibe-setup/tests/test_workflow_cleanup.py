"""Ordered cleanup against real disposable remotes; never delete a user's worktree."""
import copy
import json
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from test_workflow_lifecycle import PublicationFixture


class CleanupTests(PublicationFixture):
    def setUp(self):
        super().setUp()
        self.assertTrue(hasattr(self.workflow, "cleanup_worktree"), "Ordered cleanup is missing")
        self.event_request = self.event()
        self.assertEqual(self.sync(self.event_request)["status"], "ok")
        self.head = self.git(self.target, "rev-parse", "HEAD")
        self.prs[0].update(state="closed", merged_at="2026-10-22T00:00:00Z", draft=False)
        self.cleanup_task = {**self.task, "usage": self.usage, "source": str(self.source)}

    def cleanup(self):
        return self.workflow.cleanup_worktree(self.cleanup_task)

    def exists_remote(self, branch=None):
        return bool(self.git(self.remote, "for-each-ref", "--format=%(objectname)",
                             "refs/heads/" + (branch or self.request["branch"])))

    def test_all_merged_deletes_remote_before_worktree_and_keeps_local_branch(self):
        original = self.workflow.git
        events = []
        def ordered(root, *args, **kwargs):
            if args[0] == "push" and any(arg.startswith(":refs/heads/") for arg in args):
                self.assertTrue(self.target.exists())
                self.assertIn(f"--force-with-lease=refs/heads/{self.request['branch']}:{self.head}", args)
                events.append("remote")
            if args[:2] == ("worktree", "remove"):
                self.assertFalse(self.exists_remote())
                self.assertNotIn("--force", args)
                events.append("local")
            return original(root, *args, **kwargs)
        with patch.object(self.workflow, "git", side_effect=ordered):
            response = self.cleanup()
        self.assertEqual(response["cleanup"], "complete", response)
        self.assertEqual(events, ["remote", "local"])
        self.assertFalse(self.target.exists())
        self.assertFalse(self.exists_remote())
        self.assertEqual(self.git(self.source, "rev-parse", self.request["branch"]), self.head)
        self.assertEqual(self.cleanup()["cleanup"], "complete")

    def test_cleanup_on_sync_and_resume_uses_same_external_record(self):
        response = self.workflow.resume_operation(self.source, self.event_request["event_id"], usage=self.usage)
        self.assertEqual(response["cleanup"], "complete", response)
        self.assertTrue(Path(response["evidence_ref"]).is_file())
        self.assertEqual(self.workflow.resume_operation(self.source, self.event_request["event_id"], usage=self.usage)["cleanup"], "complete")

    def test_cleanup_resume_does_not_require_old_build_or_review_evidence(self):
        self.evidence.unlink()
        response = self.workflow.resume_operation(self.source, self.event_request["event_id"], usage=self.usage)
        self.assertEqual(response["cleanup"], "complete", response)
        self.assertFalse(self.target.exists())

    def test_resume_requires_fresh_host_usage_before_cleanup(self):
        response = self.workflow.resume_operation(self.source, self.event_request["event_id"])
        self.assertNotEqual(response.get("cleanup"), "complete")
        self.assertTrue(self.exists_remote())
        self.assertTrue(self.target.exists())
        active = {**self.usage, "writers": [{"id": "new writer", "state": "running"}]}
        response = self.workflow.resume_operation(self.source, self.event_request["event_id"], usage=active)
        self.assertNotEqual(response.get("cleanup"), "complete")
        self.assertTrue(self.exists_remote())

    def test_opt_out_and_lifecycle_disable_perform_no_deletions(self):
        for values in ('auto_cleanup = false', 'enabled = false'):
            self.policy('[task_lifecycle]\n' + values + '\n', self.target)
            before = self.snapshot(self.target)
            response = self.cleanup()
            self.assertEqual(response["cleanup"], "disabled", response)
            self.assertTrue(self.exists_remote())
            self.assertEqual(before, self.snapshot(self.target))
        self.policy('[task_lifecycle]\nauto_cleanup = "false"\n', self.target)
        self.assertNotEqual(self.cleanup()["status"], "ok")
        self.assertTrue(self.exists_remote())

    def test_any_open_draft_merged_missing_or_foreign_pr_prevents_deletion(self):
        original = copy.deepcopy(self.prs)
        variants = [dict(original[0], state="open", merged_at=None),
                    dict(original[0], draft=True),
                    dict(original[0], body=original[0]["body"].replace(self.task["task_id"], str(uuid4())))]
        for pr in variants:
            with self.subTest(pr=pr):
                self.prs = [pr]
                self.assertEqual(self.cleanup()["cleanup"], "pending")
                self.assertTrue(self.exists_remote())
                self.assertTrue(self.target.exists())
        self.prs = []
        self.assertEqual(self.cleanup()["cleanup"], "pending")
        self.prs = original
        self.remote_failure = "access"
        self.assertEqual(self.cleanup()["cleanup"], "pending")
        self.assertTrue(self.exists_remote())

    def test_multiple_merged_prs_and_squash_merge_do_not_require_main_ancestry(self):
        another = copy.deepcopy(self.prs[0])
        another["number"] = 2
        self.prs.append(another)
        self.assertNotEqual(self.git(self.source, "rev-parse", "main"), self.head)
        response = self.cleanup()
        self.assertEqual(response["cleanup"], "complete", response)
        self.assertEqual(response["cleanup_checks"]["merged_prs"], 2)

    def test_default_protected_and_shared_branches_remain(self):
        self.protected.add(self.request["branch"])
        self.assertEqual(self.cleanup()["cleanup"], "pending")
        self.assertTrue(self.exists_remote())
        self.protected.clear()
        for scope in ("shared", "pinned"):
            self.cleanup_task["usage"] = {**self.usage, "scope": scope}
            self.assertEqual(self.cleanup()["cleanup"], "pending")
            self.assertTrue(self.exists_remote())
        self.cleanup_task["usage"] = {**self.usage, "kind": "managed"}
        self.assertEqual(self.cleanup()["cleanup"], "pending")
        self.assertTrue(self.target.exists())

    def test_dirty_untracked_ignored_extra_commit_and_active_writer_preserve_everything(self):
        (self.target / "app.txt").write_text("unfinished\n")
        self.assertEqual(self.cleanup()["cleanup"], "pending")
        self.git(self.target, "restore", "app.txt")
        untracked = self.target / "private.txt"
        untracked.write_text("keep\n")
        self.assertEqual(self.cleanup()["cleanup"], "pending")
        untracked.unlink()
        self.git(self.source, "config", "core.excludesfile", str(self.home / "ignore"))
        (self.home / "ignore").write_text("private.txt\n")
        untracked.write_text("ignored but valuable\n")
        self.assertEqual(self.cleanup()["cleanup"], "pending")
        untracked.unlink()
        self.cleanup_task["usage"] = {**self.usage, "writers": [{"id": "worker", "state": "running"}]}
        self.assertEqual(self.cleanup()["cleanup"], "pending")
        self.cleanup_task["usage"] = self.usage
        self.git(self.target, "commit", "--allow-empty", "-qm", "unfinished local commit")
        self.assertEqual(self.cleanup()["cleanup"], "pending")
        self.assertTrue(self.exists_remote())
        self.assertTrue(self.target.exists())

    def test_primary_foreign_locked_and_current_directory_worktrees_are_refused(self):
        for target in (self.source, self.make_repo("foreign")):
            response = self.workflow.cleanup_worktree({**self.cleanup_task, "worktree": str(target)})
            self.assertNotEqual(response["cleanup"], "complete")
        self.git(self.source, "worktree", "lock", str(self.target))
        self.assertEqual(self.cleanup()["cleanup"], "pending")
        self.git(self.source, "worktree", "unlock", str(self.target))
        with patch.object(Path, "cwd", return_value=self.target):
            self.assertEqual(self.cleanup()["cleanup"], "pending")
        self.assertTrue(self.exists_remote())

    def test_advanced_remote_head_and_conditional_deletion_race_preserve_branch(self):
        self.git(self.source, "push", str(self.remote), f"main:refs/heads/{self.request['branch']}", "--force")
        self.assertEqual(self.cleanup()["cleanup"], "pending")
        self.git(self.source, "push", str(self.remote), f"{self.head}:refs/heads/{self.request['branch']}")
        original = self.workflow.git
        def race(root, *args, **kwargs):
            if args[0] == "push" and any(arg.startswith(":refs/heads/") for arg in args):
                self.git(self.source, "push", str(self.remote), f"main:refs/heads/{self.request['branch']}", "--force")
            return original(root, *args, **kwargs)
        with patch.object(self.workflow, "git", side_effect=race):
            self.assertEqual(self.cleanup()["cleanup"], "pending")
        self.assertTrue(self.exists_remote())
        self.assertTrue(self.target.exists())

    def test_already_absent_branch_and_lost_local_removal_response_reconcile(self):
        self.git(self.source, "push", str(self.remote), ":refs/heads/" + self.request["branch"])
        original = self.workflow.git
        def interrupt(root, *args, **kwargs):
            response = original(root, *args, **kwargs)
            if args[:2] == ("worktree", "remove"):
                raise ValueError("lost removal response")
            return response
        with patch.object(self.workflow, "git", side_effect=interrupt):
            response = self.cleanup()
        self.assertIn(response["cleanup"], ("complete", "pending"))
        self.assertFalse(self.target.exists())
        self.assertEqual(self.cleanup()["cleanup"], "complete")

    def test_local_failure_keeps_record_and_recreated_remote_is_not_deleted_again(self):
        original = self.workflow.git
        def interrupt(root, *args, **kwargs):
            if args[:2] == ("worktree", "remove"):
                raise ValueError("filesystem busy")
            return original(root, *args, **kwargs)
        with patch.object(self.workflow, "git", side_effect=interrupt):
            self.assertEqual(self.cleanup()["cleanup"], "pending")
        self.assertFalse(self.exists_remote())
        self.assertTrue(self.target.exists())
        self.git(self.source, "push", str(self.remote), f"{self.head}:refs/heads/{self.request['branch']}")
        self.assertEqual(self.cleanup()["cleanup"], "pending")
        self.assertTrue(self.exists_remote())
        self.assertTrue(self.target.exists())

    def test_default_branch_or_unknown_default_blocks_all_deletions(self):
        original = self.api
        for default in (self.request["branch"], None):
            def altered(publication, endpoint, method="GET", payload=None, paginate=False):
                result = original(publication, endpoint, method, payload, paginate)
                if endpoint == "repos/fixture/project":
                    result["default_branch"] = default
                return result
            with self.subTest(default=default), patch.object(self.workflow, "gh_api", side_effect=altered):
                self.assertEqual(self.cleanup()["cleanup"], "pending")
                self.assertTrue(self.exists_remote())
                self.assertTrue(self.target.exists())

    def test_partial_branch_cleanup_preserves_local_until_every_branch_is_absent(self):
        other = "task/other"
        self.git(self.source, "branch", other, self.head)
        self.git(self.source, "push", str(self.remote), f"{self.head}:refs/heads/{other}")
        pr = copy.deepcopy(self.prs[0])
        pr["number"] = 2
        pr["head"]["ref"] = other
        self.prs.append(pr)
        # Fixture supplies a durable explicitly registered prior branch.
        path = self.workflow.lifecycle_path(self.workflow.setup_context(self.task)[0])
        state = json.loads(path.read_text())
        state["publication"]["branches"].append(other)
        self.workflow.write_record(path, state)
        original = self.workflow.git
        def interrupt(root, *args, **kwargs):
            if args[0] == "push" and f":refs/heads/{other}" in args:
                raise ValueError("remote unavailable")
            return original(root, *args, **kwargs)
        with patch.object(self.workflow, "git", side_effect=interrupt):
            self.assertEqual(self.cleanup()["cleanup"], "pending")
        self.assertFalse(self.exists_remote())
        self.assertTrue(self.exists_remote(other))
        self.assertTrue(self.target.exists())
        self.assertEqual(self.cleanup()["cleanup"], "complete")
        self.assertFalse(self.exists_remote(other))
        self.assertFalse(self.target.exists())

    def test_cleanup_opt_out_survives_setup_and_resume(self):
        self.policy('[task_lifecycle]\nauto_cleanup = false\n', self.target)
        before = (self.target / ".codex/vibe-workflow.toml").read_bytes()
        plan = self.workflow.plan_setup(self.task)
        self.assertEqual(self.workflow.apply_setup(plan, self.task)["status"], "ok")
        self.assertEqual(self.workflow.resume_operation(self.target, plan["operation_id"])["status"], "ok")
        self.assertEqual((self.target / ".codex/vibe-workflow.toml").read_bytes(), before)
        self.assertEqual(self.workflow.resume_operation(self.source, self.event_request["event_id"], usage=self.usage)["cleanup"], "disabled")
        self.assertTrue(self.exists_remote())
