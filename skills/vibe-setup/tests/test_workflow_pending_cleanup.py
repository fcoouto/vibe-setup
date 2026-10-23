"""Deferred cleanup runs only on confirmed merge or recorded supersession."""
import copy
import contextlib
import fcntl
import io
import json
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from test_workflow_lifecycle import PublicationFixture


class PendingCleanupTests(PublicationFixture):
    def record(self, task=None):
        task = task or self.task
        path = self.source / '.git/vibe-setup/lifecycle' / (task['task_id'] + '.json')
        return self.workflow.read_lifecycle(path)

    def pending(self, kind='git'):
        event = self.event(kind='checkpoint')
        self.assertEqual(self.sync(event)['status'], 'ok')
        pr = next(pr for pr in self.prs if pr['head']['ref'] == self.request['branch'])
        pr.update(state='closed', merged_at='2026-10-23T00:00:00Z', draft=False)
        original = self.workflow.git
        def interrupted(root, *args, **kwargs):
            if args[:2] == ('worktree', 'remove'):
                raise ValueError('Disposable removal interruption')
            return original(root, *args, **kwargs)
        with patch.object(self.workflow, 'git', side_effect=interrupted):
            response = self.workflow.cleanup_worktree({**self.task, 'source': str(self.source),
                'usage': {**self.usage, 'kind': kind}})
        self.assertEqual(response['cleanup'], 'pending', response)
        self.assertTrue(self.target.exists())
        return copy.deepcopy(self.task)

    def start_new(self, name, source=None):
        request = {'task_id': str(uuid4()), 'worktree': str(self.home / name),
                   'branch': 'task/' + name, 'base': 'main'}
        response = self.workflow.start_task(source or self.source, request)
        self.assertEqual(response['status'], 'ok', response)
        return request, response

    def close_new(self, name, source=None, supersede=False):
        saved = self.request, self.task, self.target, self.publication
        try:
            request, _ = self.start_new(name, source)
            self.request = request
            self.task = {key: request[key] for key in ('task_id', 'worktree')}
            self.target = Path(request['worktree'])
            self.publication = {**self.publication, 'branches': [request['branch']]}
            (self.target / 'app.txt').write_text(name + '\n')
            event = self.event(kind='checkpoint')
            self.assertEqual(self.sync(event)['status'], 'ok')
            if supersede:
                successor, _ = self.start_new(name + '-replacement')
                response = self.workflow.supersede_task(self.source, {
                    'task_id': request['task_id'], 'successor': successor['task_id'], 'usage': self.usage})
            else:
                pr = next(p for p in self.prs if p['head']['ref'] == request['branch'])
                pr.update(state='closed', merged_at='2026-10-23T00:00:00Z', draft=False)
                response = self.workflow.cleanup_worktree({**self.task, 'source': str(self.source), 'usage': self.usage})
            return request, response
        finally:
            self.request, self.task, self.target, self.publication = saved

    def test_start_never_processes_pending_cleanup_or_contacts_github(self):
        previous = self.pending()
        before = self.record(previous)
        self.calls.clear()
        _, response = self.start_new('next')
        self.assertTrue(Path(previous['worktree']).exists(), response)
        self.assertEqual(self.record(previous), before)
        self.assertEqual(self.calls, [])
        self.assertNotIn('pending_cleanup', response)

    def second_pending(self, name):
        # Preparing another task must not consume any queued candidate.
        request, _ = self.start_new(name)
        self.request = request
        self.task = {key: request[key] for key in ('task_id', 'worktree')}
        self.target = Path(request['worktree'])
        self.publication['branches'] = [request['branch']]
        (self.target / 'app.txt').write_text(name + '\n')
        return self.pending()

    def test_merge_cleans_pending_and_preserves_local_ref_without_old_evidence(self):
        previous = self.pending()
        head = self.git(self.target, 'rev-parse', 'HEAD')
        self.evidence.unlink()
        self.evidence = self.home / 'next-task-checks.log'
        self.evidence.write_text('Only the new task uses these checks.\n')
        request, result = self.close_new('next')
        self.assertFalse(Path(previous['worktree']).exists(), result)
        self.assertEqual(self.record(previous)['cleanup']['state'], 'complete')
        self.assertEqual(self.git(self.source, 'rev-parse', 'task/example'), head)
        self.assertFalse(Path(request['worktree']).exists())

    def test_managed_removal_stays_pending_and_cannot_be_downgraded(self):
        previous = self.pending(kind='managed')
        self.close_new('next')
        self.assertTrue(Path(previous['worktree']).exists())
        response = self.workflow.cleanup_worktree({**previous, 'source': str(self.source), 'usage': self.usage})
        self.assertEqual(response['cleanup'], 'pending', response)
        self.assertTrue(Path(previous['worktree']).exists())

    def test_restart_revokes_handoff_before_any_later_closure(self):
        previous = self.pending()
        self.assertEqual(self.workflow.start_task(self.source, self.request)['status'], 'ok')
        self.close_new('next')
        self.assertTrue(Path(previous['worktree']).exists())
        self.assertEqual(self.record(previous)['cleanup'].get('deferred'), {'kind': 'git', 'state': 'cancelled'})

    def test_failed_handoff_cancellation_blocks_task_reuse(self):
        previous = self.pending()
        with patch.object(self.workflow, 'save_lifecycle', side_effect=OSError('write interrupted')):
            response = self.workflow.start_task(self.source, self.request)
        self.assertNotEqual(response['status'], 'ok', response)
        self.assertNotEqual(response['implementation'], 'worktree_verified')
        self.assertTrue(Path(previous['worktree']).exists())
        self.assertEqual(self.record(previous)['cleanup']['deferred']['state'], 'ready')
        self.assertEqual(self.workflow.start_task(self.source, self.request)['status'], 'ok')
        self.assertEqual(self.record(previous)['cleanup']['deferred']['state'], 'cancelled')

    def test_malformed_source_lifecycle_blocks_reuse_before_writers_resume(self):
        previous = self.pending()
        path = self.source / '.git/vibe-setup/lifecycle' / (previous['task_id'] + '.json')
        path.write_text('{broken')
        request = {'task_id': str(uuid4()), 'worktree': str(self.home / 'next'),
                   'branch': 'task/next', 'base': 'main'}
        response = self.workflow.start_task(Path(previous['worktree']), request)
        self.assertNotEqual(response['status'], 'ok', response)
        self.assertTrue(Path(previous['worktree']).exists())

    def retained_handoff(self):
        previous = self.pending()
        self.policy('[task_lifecycle]\ndelete_worktrees = false\n')
        self.close_new('retaining')
        self.assertEqual(self.record(previous)['cleanup']['state'], 'complete')
        self.assertTrue(Path(previous['worktree']).exists())
        return previous

    def test_completed_retained_task_revokes_handoff_on_reuse(self):
        previous = self.retained_handoff()
        self.assertEqual(self.workflow.start_task(self.source, self.request)['status'], 'ok')
        self.assertEqual(self.record(previous)['cleanup']['deferred']['state'], 'cancelled')

    def test_running_writer_cancels_completed_retained_handoff(self):
        previous = self.retained_handoff()
        response = self.workflow.cleanup_worktree({**previous, 'source': str(self.source),
            'usage': {**self.usage, 'writers': [{'id': 'writer', 'state': 'running'}]}})
        self.assertEqual(response['cleanup'], 'pending')
        self.policy('[task_lifecycle]\n')
        self.close_new('later')
        self.assertTrue(Path(previous['worktree']).exists())
        self.assertEqual(self.record(previous)['cleanup']['deferred']['state'], 'cancelled')

    def test_next_closure_recovers_locked_candidate_without_startup_polling(self):
        previous = self.pending()
        self.git(self.source, 'worktree', 'lock', previous['worktree'])
        self.close_new('next')
        self.git(self.source, 'worktree', 'unlock', previous['worktree'])
        request, _ = self.start_new('unrelated')
        self.assertEqual(self.workflow.start_task(self.source, request)['status'], 'ok')
        self.assertTrue(Path(previous['worktree']).exists())
        self.close_new('later')
        self.assertFalse(Path(previous['worktree']).exists())

    def test_one_closure_processes_all_candidates_despite_malformed_and_managed_items(self):
        first = self.pending()
        self.git(self.source, 'worktree', 'lock', first['worktree'])
        second = self.second_pending('second')
        self.git(self.source, 'worktree', 'lock', second['worktree'])
        third_request, _ = self.start_new('managed')
        self.request = third_request
        self.task = {key: third_request[key] for key in ('task_id', 'worktree')}
        self.target = Path(third_request['worktree'])
        self.publication['branches'] = [third_request['branch']]
        (self.target / 'app.txt').write_text('managed\n')
        third = self.pending(kind='managed')
        directory = self.source / '.git/vibe-setup/lifecycle'
        (directory / '00000000-0000-0000-0000-000000000000.json').write_text('{broken')
        self.git(self.source, 'worktree', 'unlock', first['worktree'])
        self.git(self.source, 'worktree', 'unlock', second['worktree'])
        _, response = self.close_new('next')
        self.assertFalse(Path(first['worktree']).exists(), response)
        self.assertFalse(Path(second['worktree']).exists(), response)
        self.assertTrue(Path(third['worktree']).exists())
        self.assertEqual(len(response['pending_cleanup']['tasks']), 4)
        self.assertEqual(self.record(first)['cleanup']['state'], 'complete')
        self.assertEqual(self.record(second)['cleanup']['state'], 'complete')
        self.assertEqual(self.record(third)['cleanup']['state'], 'pending')

    def test_current_source_reuse_cancels_retirement(self):
        previous = self.pending()
        self.start_new('next', source=Path(previous['worktree']))
        self.close_new('later')
        self.assertTrue(Path(previous['worktree']).exists())
        self.assertEqual(self.record(previous)['cleanup']['deferred']['state'], 'cancelled')

    def test_existing_unmarked_pending_record_never_grants_git_removal(self):
        previous = self.pending()
        state = self.record(previous)
        state['cleanup'].pop('deferred', None)
        self.workflow.save_lifecycle(state)
        self.close_new('next')
        self.assertTrue(Path(previous['worktree']).exists())

    def test_legacy_managed_archive_is_reconciled_only_after_native_removal(self):
        previous = self.pending(kind='managed')
        state = self.record(previous)
        state['cleanup'].pop('deferred', None)
        self.workflow.save_lifecycle(state)
        self.close_new('next')
        self.assertTrue(Path(previous['worktree']).exists())
        # Simulate the native owner; production queue processing must never do this itself.
        self.git(self.source, 'worktree', 'remove', previous['worktree'])
        self.close_new('later')
        self.assertEqual(self.record(previous)['cleanup']['state'], 'complete')

    def test_explicit_running_writer_revokes_previous_handoff(self):
        previous = self.pending()
        response = self.workflow.cleanup_worktree({**previous, 'source': str(self.source),
            'usage': {**self.usage, 'writers': [{'id': 'writer', 'state': 'running'}]}})
        self.assertEqual(response['cleanup'], 'pending')
        self.close_new('next')
        self.assertTrue(Path(previous['worktree']).exists())

    def test_reopened_pr_revokes_handoff_even_when_sync_cannot_publish(self):
        previous = self.pending()
        self.prs[0].update(state='open', merged_at=None)
        self.remote_failure = 'access'
        self.sync(self.event(kind='reopen'))
        self.remote_failure = None
        self.prs[0].update(state='closed', merged_at='2026-10-23T00:00:00Z')
        self.close_new('next')
        self.assertTrue(Path(previous['worktree']).exists())

    def test_other_repository_closure_cannot_consume_pending_cleanup(self):
        previous = self.pending()
        self.source = self.make_repo('other-project')
        self.git(self.source, 'remote', 'add', 'origin', 'https://github.com/fixture/project.git')
        self.close_new('next')
        self.assertTrue(Path(previous['worktree']).exists())

    def test_pending_foreign_binding_or_symlink_never_redirects_deletion(self):
        previous = self.pending()
        path = self.source / '.git/vibe-setup/lifecycle' / (previous['task_id'] + '.json')
        original = path.read_text()
        state = json.loads(original)
        state['binding']['common_dir'] = str(self.make_repo('foreign') / '.git')
        path.write_text(json.dumps(state))
        self.close_new('next')
        self.assertTrue(Path(previous['worktree']).exists())
        external = self.home / 'external.json'
        external.write_text(original)
        path.unlink()
        path.symlink_to(external)
        self.close_new('later')
        self.assertTrue(Path(previous['worktree']).exists())
        self.assertEqual(external.read_text(), original)

    def test_lifecycle_lock_prevents_task_reuse_races_without_waiting(self):
        previous = self.pending()
        lock_path = self.source / '.git/vibe-setup/lifecycle.lock'
        with lock_path.open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            request = {'task_id': str(uuid4()), 'worktree': str(self.home / 'next'),
                       'branch': 'task/next', 'base': 'main'}
            response = self.workflow.start_task(self.source, request)
        self.assertEqual(response['status'], 'action_required')
        self.assertFalse(Path(request['worktree']).exists())
        self.assertTrue(Path(previous['worktree']).exists())

    def test_source_opt_out_does_not_consume_retirement_or_change_settings(self):
        previous = self.pending()
        policy = self.policy('[task_lifecycle]\nauto_cleanup = false\n')
        config = self.source / '.codex/config.toml'
        config.write_text('model = "keep-model"\nmodel_provider = "keep-provider"\nmodel_reasoning_effort = "high"\n')
        before = config.read_bytes()
        self.close_new('next')
        self.assertTrue(Path(previous['worktree']).exists())
        self.assertEqual(config.read_bytes(), before)
        self.assertEqual(policy.read_text(), '[task_lifecycle]\nauto_cleanup = false\n')

    def test_closure_rechecks_dirty_head_remote_and_per_worktree_policy(self):
        previous = self.pending()
        private = Path(previous['worktree']) / 'untracked'
        private.write_text('keep')
        self.close_new('dirty')
        self.assertTrue(private.exists())
        private.unlink()
        self.policy('[task_lifecycle]\ndelete_worktrees = false\n', Path(previous['worktree']))
        self.close_new('opted-out')
        self.assertTrue(Path(previous['worktree']).exists())
        (Path(previous['worktree']) / '.codex/vibe-workflow.toml').unlink()
        self.git(self.source, 'push', str(self.remote), 'task/example:refs/heads/task/example')
        self.close_new('recreated')
        self.assertTrue(Path(previous['worktree']).exists())

    def test_cli_start_preserves_pending_queue_for_app_and_vscode(self):
        for client in ('app', 'vscode'):
            with self.subTest(client=client):
                previous = self.pending()
                request = {'task_id': str(uuid4()), 'worktree': str(self.home / client),
                           'branch': 'task/' + client, 'base': 'main'}
                output = io.StringIO()
                with patch('sys.stdin', io.StringIO(json.dumps(request))), contextlib.redirect_stdout(output):
                    code = self.workflow.main(['start', str(self.source), '--client', client])
                self.assertEqual(code, 0, output.getvalue())
                self.assertTrue(Path(previous['worktree']).exists())
                self.assertNotIn('pending_cleanup', json.loads(output.getvalue()))
                self.request = request
                self.task = {key: request[key] for key in ('task_id', 'worktree')}
                self.target = Path(request['worktree'])
                self.publication['branches'] = [request['branch']]
                (self.target / 'app.txt').write_text(client + '\n')

    def test_supersession_processes_prior_pending_worktrees(self):
        previous = self.pending()
        _, response = self.close_new('superseding', supersede=True)
        self.assertEqual(response['delivery'], 'superseded', response)
        self.assertFalse(Path(previous['worktree']).exists())

    def test_open_closed_unmerged_and_title_only_do_not_trigger_queue(self):
        previous = self.pending()
        request, _ = self.start_new('open')
        self.request = request
        self.task = {key: request[key] for key in ('task_id', 'worktree')}
        self.target = Path(request['worktree'])
        self.publication['branches'] = [request['branch']]
        (self.target / 'app.txt').write_text('open\n')
        self.assertEqual(self.sync(self.event(kind='checkpoint'))['status'], 'ok')
        pr = self.prs[-1]
        for update in ({}, {'state': 'closed'}, {'title': '[SUPERSEDED] title only'}):
            pr.update(update)
            response = self.workflow.cleanup_worktree({**self.task, 'source': str(self.source), 'usage': self.usage})
            self.assertTrue(Path(previous['worktree']).exists(), response)
            self.assertTrue(self.target.exists())
            self.assertNotIn('pending_cleanup', response)

    def test_completed_receipt_does_not_trigger_queue_without_fresh_confirmation(self):
        request, _ = self.close_new('completed')
        previous = self.pending()
        self.remote_failure = 'access'
        response = self.workflow.cleanup_worktree({'task_id': request['task_id'], 'worktree': request['worktree'],
            'source': str(self.source), 'usage': self.usage})
        self.assertTrue(Path(previous['worktree']).exists(), response)

    def test_dangling_lifecycle_link_blocks_reuse(self):
        previous = self.pending()
        path = self.source / '.git/vibe-setup/lifecycle' / (previous['task_id'] + '.json')
        path.unlink()
        path.symlink_to(self.home / 'missing-record.json')
        response = self.workflow.start_task(self.source, self.request)
        self.assertNotEqual(response['status'], 'ok', response)
        self.assertTrue(Path(previous['worktree']).exists())

    def test_sync_and_resume_closures_process_queue(self):
        for via in ('sync', 'resume'):
            with self.subTest(via=via):
                previous = self.pending()
                request, _ = self.start_new(via)
                self.request = request
                self.task = {key: request[key] for key in ('task_id', 'worktree')}
                self.target = Path(request['worktree'])
                self.publication['branches'] = [request['branch']]
                (self.target / 'app.txt').write_text(via + '\n')
                event = self.event(kind='checkpoint')
                self.assertEqual(self.sync(event)['status'], 'ok')
                self.prs[-1].update(state='closed', merged_at='2026-10-23T00:00:00Z', draft=False)
                # Native owner action keeps this task available for the next loop.
                usage = {**self.usage, 'kind': 'managed'}
                if via == 'sync':
                    response = self.sync({**event, 'usage': usage})
                else:
                    response = self.workflow.resume_lifecycle(self.source, event['event_id'], usage=usage)
                self.assertFalse(Path(previous['worktree']).exists(), response)
                # Prepare a separate ordinary task for the next queued fixture.
                request, _ = self.start_new(via + '-pending')
                self.request = request
                self.task = {key: request[key] for key in ('task_id', 'worktree')}
                self.target = Path(request['worktree'])
                self.publication['branches'] = [request['branch']]
                (self.target / 'app.txt').write_text('pending\n')

    def test_closure_lock_contention_preserves_queue(self):
        previous = self.pending()
        lock_path = self.source / '.git/vibe-setup/lifecycle.lock'
        with lock_path.open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            response = self.workflow.cleanup_worktree({**previous, 'source': str(self.source), 'usage': self.usage})
        self.assertEqual(response['status'], 'action_required')
        self.assertTrue(Path(previous['worktree']).exists())
