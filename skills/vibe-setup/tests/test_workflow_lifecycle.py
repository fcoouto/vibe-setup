"""Publication behavior using real disposable Git and a deterministic GitHub boundary."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
from uuid import uuid4

from test_workflow_setup import WorkflowFixture


class LifecycleContractTests(WorkflowFixture):
    def test_schedule_limits_only_routine_milestones(self):
        self.assertTrue(hasattr(self.workflow, "validate_schedule"), "Lifecycle schedule validation is missing")
        self.assertEqual(self.workflow.validate_schedule("checkpoints", ["one", "two"]), ("one", "two"))
        self.assertEqual(len(self.workflow.validate_schedule("phases", list("abcdef"))), 6)
        for mode, ids in (("checkpoints", list("abcde")), ("checkpoints", []),
                          ("phases", ["one", "one"]), ("phases", [" "]), ("steps", ["one"])):
            with self.subTest(mode=mode, ids=ids), self.assertRaises(ValueError):
                self.workflow.validate_schedule(mode, ids)

    def test_rendering_preserves_human_text_and_rejects_foreign_markers(self):
        self.assertTrue(hasattr(self.workflow, "render_pr"), "PR rendering is missing")
        task = str(uuid4())
        title, body = self.workflow.render_pr("Human title", "Human introduction\n", task, "BLOCKED", "Progress")
        self.assertEqual(title, "[BLOCKED] Human title")
        self.assertTrue(body.startswith("Human introduction\n"))
        title, body = self.workflow.render_pr(title, body + "\nHuman footer", task, "READY", "Complete")
        self.assertEqual(title, "[READY] Human title")
        self.assertIn("\nComplete\n", body)
        self.assertTrue(body.endswith("\nHuman footer"))
        for bad in (body + body, body.replace(task, str(uuid4())), '<!-- vibe-task-lifecycle:broken -->'):
            with self.subTest(body=bad), self.assertRaises(ValueError):
                self.workflow.render_pr(title, bad, task, "BLOCKED", "Update")
        with self.assertRaises(ValueError):
            self.workflow.render_pr(title, body, task, "WORKING", "Update")

    def test_cleanup_policy_defaults_on_and_preserves_explicit_opt_out(self):
        self.assertTrue(hasattr(self.workflow, "load_cleanup_policy"), "Cleanup policy is missing")
        self.assertTrue(self.workflow.load_cleanup_policy(self.source))
        for values in ('auto_cleanup = false', 'enabled = false', 'enabled = false\nauto_cleanup = true'):
            self.policy('schema_version = 1\n[task_lifecycle]\n' + values + '\n')
            before = self.snapshot(self.source)
            self.assertFalse(self.workflow.load_cleanup_policy(self.source))
            self.assertEqual(before, self.snapshot(self.source))
        for value in ('"false"', '1', '[]'):
            self.policy('[task_lifecycle]\nauto_cleanup = ' + value + '\n')
            with self.assertRaises(ValueError):
                self.workflow.load_cleanup_policy(self.source)


class PublicationFixture(WorkflowFixture):
    def setUp(self):
        super().setUp()
        self.assertTrue(hasattr(self.workflow, "sync_event"), "Publication synchronization is missing")
        self.assertEqual(self.workflow.start_task(self.source, self.request)["status"], "ok")
        self.task = {key: self.request[key] for key in ("task_id", "worktree")}
        self.remote = self.home / "remote.git"
        self.git(self.home, "init", "--bare", "-q", str(self.remote))
        self.git(self.source, "push", str(self.remote), "main")
        self.git(self.source, "remote", "add", "origin", "https://github.com/fixture/project.git")
        self.raw_git = self.workflow.git
        def transport(root, *args, **kwargs):
            if args and args[0] in ("push", "ls-remote"):
                args = tuple(str(self.remote) if arg == "origin" else arg for arg in args)
            return self.raw_git(root, *args, **kwargs)
        self.git_patch = patch.object(self.workflow, "git", side_effect=transport)
        self.git_patch.start()
        self.addCleanup(self.git_patch.stop)
        self.prs = []
        self.actor = "fixture"
        self.ready = {"isDraft": False, "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN",
                      "reviewDecision": "", "commits": {"nodes": [{"commit": {"statusCheckRollup": None}}]}}
        self.remote_failure = None
        self.lost_create = False
        self.fail_ready = False
        self.protected = set()
        self.calls = []
        self.api_patch = patch.object(self.workflow, "gh_api", side_effect=self.api)
        self.api_patch.start()
        self.addCleanup(self.api_patch.stop)
        self.usage = {"kind": "git", "scope": "exclusive", "writers": []}
        self.publication = {"host": "github.com", "repository": "fixture/project", "remote": "origin",
                            "base": "main", "actor": "fixture", "branches": [self.request["branch"]]}
        (self.target / "app.txt").write_text("feature\n")
        self.evidence = self.home / "validation.log"
        self.evidence.write_text("Fixture checks and independent review passed.\n")

    def api(self, publication, endpoint, method="GET", payload=None, paginate=False):
        self.calls.append((endpoint, method, copy.deepcopy(payload), paginate))
        if self.remote_failure:
            raise self.workflow.RemoteFailure(self.remote_failure, "Remote action unavailable")
        if endpoint == "user":
            return {"login": self.actor}
        if endpoint == "graphql":
            if method == "POST" and "markPullRequestReadyForReview" in payload.get("query", ""):
                if self.fail_ready:
                    raise self.workflow.RemoteFailure("draft", "Draft transition unavailable")
                self.prs[0]["draft"] = False
                return {"data": {"markPullRequestReadyForReview": {"pullRequest": {"isDraft": False}}}}
            ready = copy.deepcopy(self.ready)
            ready.update(headRefOid=self.prs[0]["head"]["sha"], isDraft=self.prs[0]["draft"])
            return {"data": {"repository": {"pullRequest": ready}}}
        base = "repos/fixture/project"
        if endpoint == base:
            return {"full_name": "fixture/project", "default_branch": "main", "permissions": {"push": True}}
        if endpoint.startswith(base + "/rules/branches/"):
            return []
        if endpoint.startswith(base + "/branches/"):
            branch = endpoint.split("/branches/", 1)[1]
            from urllib.parse import unquote
            branch = unquote(branch)
            return {"name": branch, "protected": branch in self.protected}
        if endpoint.startswith(base + "/pulls?"):
            self.assertTrue(paginate, "PR inventory must request every page")
            from urllib.parse import parse_qs, urlsplit
            branch = parse_qs(urlsplit(endpoint).query)["head"][0].split(":", 1)[1]
            return copy.deepcopy([pr for pr in self.prs if pr["head"]["ref"] == branch])
        if endpoint == base + "/pulls" and method == "POST":
            self.assertTrue(payload["draft"])
            self.assertTrue(payload["title"].startswith("[BLOCKED] "))
            head = self.git(self.remote, "rev-parse", f"refs/heads/{payload['head']}")
            pr = {"number": len(self.prs) + 1, "node_id": "PR_fixture", "state": "open", "merged_at": None,
                  "draft": True, "title": payload["title"], "body": payload["body"],
                  "head": {"ref": payload["head"], "sha": head, "repo": {"full_name": "fixture/project"}},
                  "base": {"ref": payload["base"]}, "html_url": "https://github.com/fixture/project/pull/1",
                  "user": {"login": "fixture"}}
            self.prs.append(pr)
            if self.lost_create:
                self.lost_create = False
                raise self.workflow.RemoteFailure("create_unknown", "Creation outcome unknown")
            return copy.deepcopy(pr)
        if endpoint.startswith(base + "/pulls/"):
            number = int(endpoint.rsplit("/", 1)[1])
            pr = self.prs[number - 1]
            if method == "PATCH":
                pr.update(payload)
            return copy.deepcopy(pr)
        raise AssertionError((endpoint, method, payload))

    def event(self, kind="ready", milestone="phase-1", files=None):
        files = files or ["app.txt"]
        snapshot = self.workflow.publication_snapshot(self.task, files)
        proof = {"name": "fixture checks", "outcome": "passed", "path": str(self.evidence),
                 "sha256": self.workflow.fingerprint(self.evidence)["sha256"]}
        return {"event_id": str(uuid4()), "kind": kind, "milestone": milestone,
                "schedule": {"mode": "phases", "ids": ["phase-1", "phase-2"]},
                "publication": self.publication, "usage": self.usage, "files": files,
                "snapshot": snapshot["digest"], "message": "feat: fixture change", "title": "Fixture feature",
                "summary": "Implement the fixture feature.", "progress": "Phase complete.",
                "remaining": "None.", "blockers": "", "validation": {"snapshot": snapshot["digest"],
                    "checks": [proof], "review": {**proof, "name": "independent review"},
                    "security": {"snapshot": snapshot["digest"], "risk": "R0", "status": "complete",
                        "rationale": "Synthetic text fixture has no executable behavior.",
                        "required_checks": ["impact-review", "trailofbits-update-review"],
                        "checks": [{**proof, "name": name}
                                   for name in ("impact-review", "trailofbits-update-review")]}}}

    def sync(self, request):
        return self.workflow.sync_event(request, self.task)


class PublicationTests(PublicationFixture):
    def test_exhausted_checkpoint_budget_allows_ready_but_not_another_checkpoint(self):
        checkpoint = self.event("checkpoint")
        checkpoint["schedule"] = {"mode": "checkpoints", "ids": ["phase-1"]}
        self.assertEqual(self.sync(checkpoint)["status"], "ok")
        ready = self.event()
        ready["schedule"] = copy.deepcopy(checkpoint["schedule"])
        self.assertEqual(self.sync(ready)["status"], "ok")
        self.assertEqual(self.prs[0]["title"], "[READY] Fixture feature")
        duplicate = self.event("checkpoint")
        duplicate["schedule"] = copy.deepcopy(checkpoint["schedule"])
        self.assertEqual(self.sync(duplicate)["status"], "blocked")
        changed_schedule = self.event("checkpoint", "phase-2")
        self.assertEqual(self.sync(changed_schedule)["status"], "blocked")
        self.assertEqual(len(self.prs), 1)

    def test_reopened_ready_reuses_milestone_without_rewriting_prior_events(self):
        first = self.event()
        self.assertEqual(self.sync(first)["status"], "ok")
        self.assertEqual(self.sync(self.event("reopen"))["status"], "ok")
        blocker = self.event("blocker")
        blocker["blockers"] = "Additional validation requested; rerun readiness when complete."
        self.assertEqual(self.sync(blocker)["status"], "ok")
        binding, _ = self.workflow.setup_context(self.task)
        path = self.workflow.lifecycle_path(binding)
        before = self.workflow.read_lifecycle(path)
        refreshed = self.event()
        self.assertEqual(self.sync(refreshed)["status"], "ok")
        after = self.workflow.read_lifecycle(path)
        self.assertEqual(after["schedule"], before["schedule"])
        for identity, event in before["events"].items():
            self.assertEqual(after["events"][identity], event)
        self.assertTrue(after["events"][refreshed["event_id"]]["delivered"])
        rewritten = {**refreshed, "progress": "Changed immutable request"}
        self.assertEqual(self.sync(rewritten)["status"], "blocked")
        self.assertEqual(self.sync(refreshed)["status"], "ok")

    def test_reopened_ready_still_requires_current_local_security_and_remote_gates(self):
        self.assertEqual(self.sync(self.event())["status"], "ok")
        self.assertEqual(self.sync(self.event("reopen"))["status"], "ok")
        for failure in ("missing", "stale", "incomplete", "failing", "checks", "review"):
            with self.subTest(failure=failure):
                request = self.event()
                validation = request["validation"]
                if failure == "missing":
                    del validation["security"]
                elif failure == "stale":
                    validation["security"]["snapshot"] = "0" * 64
                elif failure == "incomplete":
                    validation["security"]["status"] = "incomplete"
                elif failure == "failing":
                    validation["security"]["checks"][0]["outcome"] = "failed"
                elif failure == "checks":
                    validation["checks"][0]["outcome"] = "failed"
                else:
                    validation["review"]["outcome"] = "failed"
                self.assertEqual(self.sync(request)["status"], "blocked")
                self.assertTrue(self.prs[0]["title"].startswith("[BLOCKED] "))
        request = self.event()
        self.ready["mergeStateStatus"] = "BLOCKED"
        self.assertEqual(self.sync(request)["delivery"], "pending")
        self.assertTrue(self.prs[0]["title"].startswith("[BLOCKED] "))
        self.ready["mergeStateStatus"] = "CLEAN"
        self.assertEqual(self.sync(request)["status"], "ok")
        self.assertEqual(self.prs[0]["title"], "[READY] Fixture feature")

    def test_commit_push_draft_then_ready_and_idempotent_reconciliation(self):
        request = self.event()
        response = self.sync(request)
        self.assertEqual(response["status"], "ok", response)
        self.assertEqual(response["delivery"], "synchronized")
        self.assertEqual(self.prs[0]["title"], "[READY] Fixture feature")
        self.assertFalse(self.prs[0]["draft"])
        self.assertIn("Vibe-Event: " + request["event_id"], self.git(self.target, "log", "-1", "--format=%B"))
        head = self.git(self.target, "rev-parse", "HEAD")
        self.assertEqual(self.git(self.remote, "rev-parse", self.request["branch"]), head)
        mutations = sum(method != "GET" and endpoint != "graphql" for endpoint, method, _, _ in self.calls)
        self.assertEqual(self.sync(request)["delivery"], "synchronized")
        self.assertEqual(len(self.prs), 1)
        self.assertEqual(self.git(self.target, "rev-parse", "HEAD"), head)
        self.assertEqual(sum(method != "GET" and endpoint != "graphql" for endpoint, method, _, _ in self.calls), mutations)

    def test_lost_creation_response_reconciles_without_duplicate_pr(self):
        self.lost_create = True
        request = self.event()
        self.assertEqual(self.sync(request)["status"], "action_required")
        self.assertEqual(self.sync(request)["status"], "ok")
        self.assertEqual(len(self.prs), 1)

    def test_lost_ready_response_reconciles_without_repeating_mutation(self):
        request = self.event()
        original = self.api
        def lose(publication, endpoint, method="GET", payload=None, paginate=False):
            response = original(publication, endpoint, method, payload, paginate)
            if method == "PATCH" and payload.get("title", "").startswith("[READY]"):
                raise self.workflow.RemoteFailure("unknown", "Lost ready response")
            return response
        with patch.object(self.workflow, "gh_api", side_effect=lose):
            self.assertEqual(self.sync(request)["delivery"], "pending")
        changes = sum(method == "PATCH" for _, method, _, _ in self.calls)
        self.assertEqual(self.sync(request)["delivery"], "synchronized")
        self.assertEqual(sum(method == "PATCH" for _, method, _, _ in self.calls), changes)

    def test_lost_ready_update_still_pauses_reopen_when_remote_is_unavailable(self):
        request = self.event()
        original = self.api
        def lose(publication, endpoint, method="GET", payload=None, paginate=False):
            response = original(publication, endpoint, method, payload, paginate)
            if method == "PATCH" and payload.get("title", "").startswith("[READY]"):
                raise self.workflow.RemoteFailure("unknown", "Lost ready response")
            return response
        with patch.object(self.workflow, "gh_api", side_effect=lose):
            self.assertEqual(self.sync(request)["delivery"], "pending")
        self.assertTrue(self.prs[0]["title"].startswith("[READY]"))
        self.remote_failure = "access"
        response = self.sync(self.event("reopen", "phase-2"))
        self.assertEqual(response["status"], "blocked")
        self.assertEqual(response["implementation"], "paused_for_pr")

    def test_manual_blocked_confirmation_unpauses_known_pr_without_cleanup(self):
        self.assertEqual(self.sync(self.event())["status"], "ok")
        request = self.event("reopen", "phase-2")
        self.remote_failure = "access"
        self.assertEqual(self.sync(request)["implementation"], "paused_for_pr")
        confirmation = {"actor": "Human user", "head": self.git(self.target, "rev-parse", "HEAD"),
                        "pr_number": 1, "actions": ["readiness_withdrawal"]}
        for changed in ({"pr_number": 99}, {"head": "0" * 40}):
            response = self.workflow.resume_operation(self.source, request["event_id"],
                        {**confirmation, **changed}, usage=self.usage)
            self.assertNotEqual(response.get("delivery"), "user_confirmed")
        self.prs[0]["title"] = self.prs[0]["title"].replace("[READY]", "[BLOCKED]")
        response = self.workflow.resume_operation(self.source, request["event_id"], confirmation, usage=self.usage)
        self.assertEqual(response["implementation"], "worktree_verified", response)
        self.assertEqual(response["delivery"], "user_confirmed")
        self.assertEqual(response["confirmation_source"], "Human user")
        self.assertEqual(response["cleanup"], "unverified")
        self.assertTrue(self.target.exists())

    def test_confirmation_cannot_override_observed_draft(self):
        self.fail_ready = True
        request = self.event()
        self.assertEqual(self.sync(request)["status"], "action_required")
        response = self.workflow.resume_operation(self.source, request["event_id"], {
            "actor": "Human user", "head": self.git(self.target, "rev-parse", "HEAD"),
            "pr_number": 1, "actions": ["publication", "metadata", "non_draft", "readiness"]}, usage=self.usage)
        self.assertNotEqual(response["delivery"], "user_confirmed")

    def test_lost_commit_response_reconciles_without_second_commit(self):
        request = self.event()
        original = self.workflow.git
        def lose(root, *args, **kwargs):
            response = original(root, *args, **kwargs)
            if args[0] == "commit":
                raise ValueError("Commit response lost")
            return response
        with patch.object(self.workflow, "git", side_effect=lose):
            self.assertEqual(self.sync(request)["delivery"], "pending")
        head = self.git(self.target, "rev-parse", "HEAD")
        self.assertEqual(self.sync(request)["delivery"], "synchronized")
        self.assertEqual(self.git(self.target, "rev-parse", "HEAD"), head)

    def test_active_writers_prevent_staging_and_commit(self):
        request = self.event()
        request["usage"]["writers"] = [{"id": "writer", "state": "running"}]
        head = self.git(self.target, "rev-parse", "HEAD")
        response = self.sync(request)
        self.assertEqual(response["status"], "blocked")
        self.assertEqual(self.git(self.target, "rev-parse", "HEAD"), head)
        self.assertEqual(self.git(self.target, "diff", "--cached", "--name-only"), "")
        self.assertEqual(self.prs, [])

    def test_stale_snapshot_and_unrelated_staged_work_are_preserved(self):
        request = self.event()
        (self.target / "app.txt").write_text("foreign edit\n")
        self.assertEqual(self.sync(request)["status"], "blocked")
        (self.target / "unrelated.txt").write_text("leave this\n")
        self.git(self.target, "add", "unrelated.txt")
        request = self.event()
        self.assertEqual(self.sync(request)["status"], "blocked")
        self.assertEqual(self.git(self.target, "diff", "--cached", "--name-only"), "unrelated.txt")

    def test_account_mismatch_and_remote_failure_produce_concrete_manual_handoff(self):
        request = self.event()
        self.actor = "different-account"
        response = self.sync(request)
        self.assertEqual(response["status"], "action_required")
        self.assertEqual(self.prs, [])
        self.actor = "fixture"
        self.remote_failure = "access"
        response = self.sync(request)
        self.assertEqual(response["implementation"], "ready")
        self.assertEqual(response["delivery"], "pending")
        action = response["pending_user_actions"][0]
        self.assertEqual(action["worktree"], str(self.target))
        self.assertEqual(action["branch"], self.request["branch"])
        self.assertEqual(action["base"], "main")
        self.assertIn("look up", action["message"].lower())

    def test_no_diff_creates_no_empty_commit_or_pr(self):
        self.git(self.target, "restore", "app.txt")
        request = self.event("checkpoint")
        head = self.git(self.target, "rev-parse", "HEAD")
        response = self.sync(request)
        self.assertEqual(response["delivery"], "not_needed", response)
        self.assertEqual(self.git(self.target, "rev-parse", "HEAD"), head)
        self.assertEqual(self.prs, [])
        self.assertEqual(self.sync(request)["delivery"], "not_needed")
        self.assertEqual(self.prs, [])

    def test_failed_checks_or_draft_transition_never_promote_ready(self):
        self.ready["mergeStateStatus"] = "BLOCKED"
        response = self.sync(self.event())
        self.assertEqual(response["delivery"], "pending")
        self.assertTrue(self.prs[0]["title"].startswith("[BLOCKED] "))
        self.assertFalse(self.prs[0]["draft"])

    def test_draft_transition_failure_names_manual_action(self):
        self.fail_ready = True
        request = self.event()
        response = self.sync(request)
        self.assertEqual(response["status"], "action_required")
        self.assertTrue(self.prs[0]["draft"])
        self.assertIn("ready for review", json.dumps(response).lower())
        self.fail_ready = False
        self.assertEqual(self.sync(request)["status"], "ok")

    def test_human_text_survives_but_edited_managed_section_requires_reconciliation(self):
        request = self.event("checkpoint")
        self.assertEqual(self.sync(request)["status"], "ok")
        self.prs[0]["title"] = "[BLOCKED] Human suffix"
        self.prs[0]["body"] = "Human introduction\n" + self.prs[0]["body"] + "\nHuman footer"
        second = self.event("ready", "phase-2")
        self.assertEqual(self.sync(second)["status"], "ok")
        self.assertEqual(self.prs[0]["title"], "[READY] Human suffix")
        self.assertTrue(self.prs[0]["body"].endswith("\nHuman footer"))
        self.prs[0]["body"] = self.prs[0]["body"].replace("Implement the fixture feature.", "Human edit inside managed section.")
        response = self.sync(second)
        self.assertEqual(response["status"], "action_required")
        self.assertIn("Human edit inside", self.prs[0]["body"])

    def test_failed_ready_demotion_pauses_that_pr_before_commit(self):
        first = self.event()
        self.assertEqual(self.sync(first)["status"], "ok")
        head = self.git(self.target, "rev-parse", "HEAD")
        (self.target / "app.txt").write_text("next phase\n")
        request = self.event("checkpoint", "phase-2")
        self.remote_failure = "metadata"
        response = self.sync(request)
        self.assertEqual(response["status"], "blocked")
        self.assertEqual(self.git(self.target, "rev-parse", "HEAD"), head)
        self.assertTrue(self.prs[0]["title"].startswith("[READY]"))

    def test_manual_confirmation_is_attributed_and_does_not_authorize_cleanup(self):
        request = self.event()
        self.remote_failure = "access"
        self.assertEqual(self.sync(request)["status"], "action_required")
        self.git(self.target, "add", "app.txt")
        self.git(self.target, "commit", "-qm", "Human publication")
        response = self.workflow.resume_operation(self.source, request["event_id"], {
            "actor": "Human user", "head": self.git(self.target, "rev-parse", "HEAD"),
            "pr_number": 7, "actions": ["publication", "metadata", "non_draft", "readiness"]}, usage=self.usage)
        self.assertEqual(response["delivery"], "user_confirmed", response)
        self.assertEqual(response["confirmation_source"], "Human user")
        self.assertTrue(self.target.exists())

    def test_confirmation_cannot_override_observed_failed_readiness(self):
        self.ready["mergeStateStatus"] = "BLOCKED"
        request = self.event()
        self.assertEqual(self.sync(request)["status"], "action_required")
        response = self.workflow.resume_operation(self.source, request["event_id"], {
            "actor": "Human", "head": self.git(self.target, "rev-parse", "HEAD"), "pr_number": 1,
            "actions": ["publication", "metadata", "non_draft", "readiness"]}, usage=self.usage)
        self.assertNotEqual(response["delivery"], "user_confirmed")
        self.assertTrue(self.prs[0]["title"].startswith("[BLOCKED]"))

    def test_confirmation_cannot_mark_uncommitted_work_delivered(self):
        request = self.event()
        self.remote_failure = "access"
        self.sync(request)
        response = self.workflow.resume_operation(self.source, request["event_id"], {
            "actor": "Human", "head": self.git(self.target, "rev-parse", "HEAD"), "pr_number": 1,
            "actions": ["publication", "metadata", "non_draft", "readiness"]}, usage=self.usage)
        self.assertNotEqual(response["delivery"], "user_confirmed")

    def test_commit_hook_worktree_change_blocks_push(self):
        request = self.event()
        original = self.workflow.git
        def change_after_commit(root, *args, **kwargs):
            response = original(root, *args, **kwargs)
            if args[0] == "commit":
                (self.target / "app.txt").write_text("changed by post-commit hook\n")
            return response
        with patch.object(self.workflow, "git", side_effect=change_after_commit):
            response = self.sync(request)
        self.assertEqual(response["status"], "blocked")
        self.assertEqual(self.prs, [])
        self.assertEqual(self.git(self.remote, "for-each-ref", "--format=%(objectname)", "refs/heads/" + self.request["branch"]), "")

    def test_malformed_publication_files_return_structured_failure(self):
        request = self.event()
        request["files"] = [{}]
        response = self.sync(request)
        self.assertEqual(response["status"], "blocked")
        self.assertEqual(self.prs, [])

    def test_unknown_creation_with_no_observed_pr_never_retries_creation(self):
        request = self.event()
        self.lost_create = True
        self.assertEqual(self.sync(request)["status"], "action_required")
        self.prs = []
        self.assertEqual(self.sync(request)["status"], "action_required")
        self.assertEqual(sum(endpoint.endswith("/pulls") and method == "POST" for endpoint, method, _, _ in self.calls), 1)

    def test_multiple_or_closed_pr_matches_never_create_another(self):
        request = self.event("checkpoint")
        self.assertEqual(self.sync(request)["status"], "ok")
        another = copy.deepcopy(self.prs[0])
        another["number"] = 2
        self.prs.append(another)
        response = self.sync(request)
        self.assertEqual(response["status"], "action_required")
        self.prs.pop()
        self.prs[0]["state"] = "closed"
        response = self.sync(request)
        self.assertEqual(response["cleanup"], "pending", response)
        self.assertNotIn("pending_cleanup", response)
        self.assertTrue(self.target.exists())
        self.assertEqual(self.git(self.remote, "for-each-ref", "--format=%(objectname)",
                                  "refs/heads/" + self.request["branch"]), self.prs[0]["head"]["sha"])
        self.assertEqual(sum(endpoint.endswith("/pulls") and method == "POST" for endpoint, method, _, _ in self.calls), 1)

    def test_divergent_remote_refuses_force_push(self):
        self.git(self.source, "checkout", "-qb", "remote-work")
        (self.source / "remote.txt").write_text("other work\n")
        self.git(self.source, "add", "remote.txt")
        self.git(self.source, "commit", "-qm", "remote work")
        self.git(self.source, "push", str(self.remote), "HEAD:refs/heads/" + self.request["branch"])
        before = self.git(self.remote, "rev-parse", self.request["branch"])
        response = self.sync(self.event())
        self.assertEqual(response["status"], "action_required")
        self.assertEqual(self.git(self.remote, "rev-parse", self.request["branch"]), before)
        self.assertEqual(self.prs, [])

    def test_false_local_acceptance_and_changed_evidence_cannot_reach_ready(self):
        request = self.event()
        request["validation"]["review"]["outcome"] = "failed"
        self.assertEqual(self.sync(request)["status"], "blocked")
        request = self.event()
        self.evidence.write_text("changed result\n")
        self.assertEqual(self.sync(request)["status"], "blocked")
        self.assertEqual(self.prs, [])

    def test_remote_readback_mismatch_remains_pending(self):
        request = self.event()
        original = self.api
        def changed(publication, endpoint, method="GET", payload=None, paginate=False):
            result = original(publication, endpoint, method, payload, paginate)
            if method == "PATCH" and payload.get("title", "").startswith("[READY]"):
                self.prs[0]["body"] += "\nConcurrent human edit"
            return result
        with patch.object(self.workflow, "gh_api", side_effect=changed):
            response = self.sync(request)
        self.assertEqual(response["delivery"], "pending")
        self.assertIn("Concurrent human edit", self.prs[0]["body"])
