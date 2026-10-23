"""Read-only completion across existing repository lifecycle records."""
import copy
import contextlib
import io
import json
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from test_workflow_lifecycle import PublicationFixture


class CompletionTests(PublicationFixture):
    def setUp(self):
        super().setUp()
        self.assertTrue(hasattr(self.workflow, "check_completion"), "Cross-repository completion is missing")
        self.assertEqual(self.sync(self.event("checkpoint"))["status"], "ok")
        self.binding = self.workflow.task_binding(self.source, self.request["task_id"])
        self.path = self.workflow.lifecycle_path(self.binding)
        self.second = self.make_repo("companion")
        request = {"task_id": str(uuid4()), "worktree": str(self.home / "companion-task"),
                   "branch": "task/companion", "base": "main"}
        self.assertEqual(self.workflow.start_task(self.second, request)["status"], "ok")
        self.second_binding = self.workflow.task_binding(self.second, request["task_id"])
        self.git(self.second, "remote", "add", "origin", "https://github.com/fixture/companion.git")
        state = copy.deepcopy(self.workflow.read_lifecycle(self.path))
        state["binding"] = self.second_binding
        state["publication"].update(repository="fixture/companion", branches=[request["branch"]])
        head = self.git(self.second, "rev-parse", "HEAD")
        state["prs"] = [{"number": 2, "branch": request["branch"], "head": head}]
        self.workflow.save_lifecycle(state)
        self.other_pr = copy.deepcopy(self.prs[0])
        self.other_pr.update(number=2, body=self.other_pr["body"].replace(self.request["task_id"], request["task_id"]))
        self.other_pr["head"] = {"ref": request["branch"], "sha": head, "repo": {"full_name": "fixture/companion"}}
        self.members = {"members": [{"source": str(self.source), "task_id": self.request["task_id"]},
                                    {"source": str(self.second), "task_id": request["task_id"]}]}
        self.api_patch.stop()
        def api(publication, endpoint, method="GET", payload=None, paginate=False):
            self.assertEqual(method, "GET", "Completion must never mutate GitHub")
            if publication["repository"] == "fixture/companion":
                if endpoint == "user": return {"login": "fixture"}
                if endpoint == "repos/fixture/companion": return {"full_name": "fixture/companion", "default_branch": "main"}
                if "/pulls?" in endpoint: return [copy.deepcopy(self.other_pr)]
                raise AssertionError(endpoint)
            return self.api(publication, endpoint, method, payload, paginate)
        self.read_api = patch.object(self.workflow, "gh_api", side_effect=api)
        self.read_api.start()
        self.addCleanup(self.read_api.stop)
        for pr in (self.prs[0], self.other_pr):
            pr.update(state="closed", draft=False, merged_at="2026-10-23T00:00:00Z")

    def check(self):
        return self.workflow.check_completion(self.source, self.members)

    def test_complete_only_when_every_companion_merged_and_no_files_change(self):
        before = self.snapshot(self.home)
        result = self.check()
        self.assertEqual(result["completion"], "complete")
        self.assertEqual([m["completion"] for m in result["members"]], ["complete", "complete"])
        self.assertEqual(before, self.snapshot(self.home))

    def test_open_companion_is_pending_and_closed_unmerged_is_blocked(self):
        self.other_pr.update(state="open", merged_at=None, draft=True)
        self.assertEqual(self.check()["completion"], "pending")
        self.other_pr["state"] = "closed"
        self.assertEqual(self.check()["completion"], "blocked")

    def test_missing_publication_is_pending(self):
        self.workflow.lifecycle_path(self.second_binding).unlink()
        self.assertEqual(self.check()["members"][1]["completion"], "pending")

    def test_unavailable_remote_never_uses_old_success(self):
        self.assertEqual(self.check()["completion"], "complete")
        self.remote_failure = self.workflow.RemoteFailure("access", "Fixture unavailable")
        result = self.check()
        self.assertEqual(result["completion"], "blocked")
        self.assertEqual(result["members"][1]["completion"], "complete")

    def test_changed_head_base_or_ownership_blocks(self):
        original = copy.deepcopy(self.other_pr)
        for mutation in (lambda p: p["head"].update(sha="a" * 40),
                         lambda p: p["base"].update(ref="different"),
                         lambda p: p.update(body="unrelated"),
                         lambda p: p.update(number=99)):
            with self.subTest(mutation=mutation):
                self.other_pr = copy.deepcopy(original)
                mutation(self.other_pr)
                self.assertEqual(self.check()["completion"], "blocked")

    def test_removed_worktree_does_not_lose_completion(self):
        self.git(self.second, "worktree", "remove", self.second_binding["worktree"])
        self.assertEqual(self.check()["completion"], "complete")

    def test_unpublished_local_edits_block(self):
        (Path(self.second_binding["worktree"]) / "app.txt").write_text("unfinished\n")
        self.assertEqual(self.check()["completion"], "blocked")

    def test_stale_local_commit_blocks(self):
        root = Path(self.second_binding["worktree"])
        (root / "app.txt").write_text("new work\n")
        self.git(root, "commit", "-am", "unpublished")
        self.assertEqual(self.check()["completion"], "blocked")

    def test_duplicate_or_invalid_members_are_rejected(self):
        for request in ({"members": []}, {"members": [self.members["members"][0]] * 2},
                        {"members": [{"source": "relative", "task_id": str(uuid4())}]},
                        {"members": [{"source": str(self.source), "task_id": "../escape"}]}):
            with self.subTest(request=request), self.assertRaises(ValueError):
                self.workflow.check_completion(self.source, request)

    def test_cli_uses_same_read_only_path(self):
        output = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(self.members))), contextlib.redirect_stdout(output):
            code = self.workflow.main(["check-completion", str(self.source)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["completion"], "complete")

    def test_record_change_during_observation_blocks(self):
        original = self.workflow.inventory_prs
        def changing(publication):
            prs = original(publication)
            if publication["repository"] == "fixture/project":
                state = self.workflow.read_lifecycle(self.path)
                state["cleanup"]["concurrent_change"] = True
                self.workflow.save_lifecycle(state)
            return prs
        with patch.object(self.workflow, "inventory_prs", side_effect=changing):
            self.assertEqual(self.check()["completion"], "blocked")

    def test_missing_or_malformed_inventory_blocks(self):
        for value in ([], [{"number": True}], None):
            with self.subTest(value=value), patch.object(self.workflow, "gh_api", return_value=value):
                self.assertEqual(self.check()["completion"], "blocked")

    def test_no_publication_records_never_vacuously_complete(self):
        for binding in (self.binding, self.second_binding):
            self.workflow.lifecycle_path(binding).unlink()
        self.assertEqual(self.check()["completion"], "pending")

    def test_symlink_member_and_oversized_manifest_are_rejected(self):
        link = self.home / "alias"
        link.symlink_to(self.source, target_is_directory=True)
        for request in ({"members": [{"source": str(link), "task_id": self.request["task_id"]}]},
                        {"members": self.members["members"] * 17}):
            with self.subTest(request=request), self.assertRaises(ValueError):
                self.workflow.check_completion(self.source, request)

    def test_cli_pending_and_blocked_exit_codes(self):
        for state, expected in (("open", 2), ("closed", 3)):
            self.other_pr.update(state=state, merged_at=None)
            with patch("sys.stdin", io.StringIO(json.dumps(self.members))), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(self.workflow.main(["check-completion", str(self.source)]), expected)

    def test_removed_worktree_with_advanced_retained_branch_blocks(self):
        root = Path(self.second_binding["worktree"])
        (root / "app.txt").write_text("unpublished\n")
        self.git(root, "commit", "-am", "unfinished companion")
        self.git(self.second, "worktree", "remove", str(root))
        self.assertEqual(self.check()["completion"], "blocked")

    def test_moved_worktree_with_uncommitted_changes_blocks(self):
        root = Path(self.second_binding["worktree"])
        (root / "app.txt").write_text("unfinished\n")
        self.git(self.second, "worktree", "move", str(root), str(self.home / "moved-task"))
        self.assertEqual(self.check()["completion"], "blocked")
