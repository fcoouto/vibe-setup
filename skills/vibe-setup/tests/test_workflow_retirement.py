"""Terminal task transitions use disposable repositories and a fake GitHub boundary."""
import copy
import json
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from test_workflow_lifecycle import PublicationFixture


class RetirementTests(PublicationFixture):
    def publish(self, merged=False):
        self.event_request = self.event()
        self.assertEqual(self.sync(self.event_request)['status'], 'ok')
        self.head = self.git(self.target, 'rev-parse', 'HEAD')
        if merged:
            self.prs[0].update(state='closed', merged_at='2026-10-23T00:00:00Z', draft=False)

    def cleanup(self, **extra):
        return self.workflow.cleanup_worktree({**self.task, 'source': str(self.source),
                                              'usage': self.usage, **extra})

    def remote_exists(self):
        return bool(self.git(self.remote, 'for-each-ref', '--format=%(objectname)',
                             'refs/heads/' + self.request['branch']))

    def record(self):
        common = Path(self.workflow.repository(self.source)['common_dir'])
        return json.loads((common / 'vibe-setup/lifecycle' / (self.task['task_id'] + '.json')).read_text())

    def successor(self):
        request = {'task_id': str(uuid4()), 'branch': 'task/successor',
                   'worktree': str(self.home / 'successor'), 'base': 'main'}
        self.assertEqual(self.workflow.start_task(self.source, request)['status'], 'ok')
        return request['task_id']

    def supersede(self, successor, **extra):
        return self.workflow.supersede_task(self.source, {
            'task_id': self.task['task_id'], 'successor': successor, 'usage': self.usage, **extra})

    def test_independent_options_default_on_and_legacy_opt_out_wins(self):
        policy = self.workflow.policy_values(self.source)
        self.assertTrue(policy['delete_remote_branches'])
        self.assertTrue(policy['delete_worktrees'])
        for key in ('delete_remote_branches', 'delete_worktrees'):
            self.policy('[task_lifecycle]\n' + key + ' = "false"\n')
            with self.assertRaises(ValueError):
                self.workflow.policy_values(self.source)
        self.policy('[task_lifecycle]\nauto_cleanup = false\ndelete_remote_branches = true\ndelete_worktrees = true\n')
        self.assertFalse(self.workflow.load_cleanup_policy(self.source))

    def test_all_independent_opt_out_combinations(self):
        self.publish(merged=True)
        self.policy('[task_lifecycle]\ndelete_remote_branches = false\ndelete_worktrees = false\n')
        self.assertEqual(self.cleanup()['cleanup'], 'disabled')
        self.assertTrue(self.remote_exists())
        self.assertTrue(self.target.exists())
        self.policy('[task_lifecycle]\ndelete_worktrees = false\n')
        result = self.cleanup()
        self.assertEqual(result['cleanup'], 'complete', result)
        self.assertFalse(self.remote_exists())
        self.assertTrue(self.target.exists())
        self.policy('[task_lifecycle]\n')
        self.assertEqual(self.cleanup()['cleanup'], 'complete')
        self.assertFalse(self.target.exists())

    def test_remote_opt_out_allows_local_removal_even_if_remote_protected(self):
        self.publish(merged=True)
        self.policy('[task_lifecycle]\ndelete_remote_branches = false\n')
        self.protected.add(self.request['branch'])
        result = self.cleanup()
        self.assertEqual(result['cleanup'], 'complete', result)
        self.assertTrue(self.remote_exists())
        self.assertFalse(self.target.exists())
        self.assertEqual(self.git(self.source, 'rev-parse', self.request['branch']), self.head)

    def test_closed_unmerged_deletes_remote_but_keeps_worktree_and_local_ref(self):
        self.publish()
        self.prs[0]['state'] = 'closed'
        result = self.cleanup()
        self.assertEqual(result['cleanup'], 'complete', result)
        self.assertEqual(result['delivery'], 'closed')
        self.assertFalse(self.remote_exists())
        self.assertTrue(self.target.exists())
        self.assertEqual(self.git(self.source, 'rev-parse', self.request['branch']), self.head)

    def test_superseded_replaces_prefix_closes_pr_and_preserves_human_text(self):
        self.publish()
        successor = self.successor()
        self.prs[0]['body'] = 'Human introduction\n' + self.prs[0]['body'] + '\nHuman footer'
        result = self.supersede(successor)
        self.assertEqual(result['cleanup'], 'complete', result)
        self.assertEqual(result['delivery'], 'superseded')
        self.assertEqual(self.prs[0]['title'], '[SUPERSEDED] Fixture feature')
        self.assertEqual(self.prs[0]['state'], 'closed')
        self.assertIn(successor, self.prs[0]['body'])
        self.assertTrue(self.prs[0]['body'].startswith('Human introduction'))
        self.assertTrue(self.prs[0]['body'].endswith('Human footer'))
        self.assertFalse(self.remote_exists())
        self.assertFalse(self.target.exists())
        self.assertEqual(self.git(self.source, 'rev-parse', self.request['branch']), self.head)
        self.assertEqual(self.supersede(successor)['cleanup'], 'complete')

    def test_title_alone_does_not_authorize_supersession_cleanup(self):
        self.publish()
        self.prs[0].update(title='[SUPERSEDED] Fixture feature', state='closed')
        self.assertEqual(self.cleanup()['cleanup'], 'complete')
        self.assertTrue(self.target.exists())

    def test_managed_cleanup_returns_native_action_then_verifies_removal(self):
        self.publish(merged=True)
        self.usage = {**self.usage, 'kind': 'managed'}
        result = self.cleanup()
        self.assertEqual(result['cleanup'], 'pending', result)
        self.assertFalse(self.remote_exists())
        self.assertTrue(self.target.exists())
        self.assertEqual(result['native_action']['tool'], 'archive_worktree')
        self.assertEqual(self.record()['cleanup']['local'], 'archive_requested')
        self.git(self.source, 'worktree', 'remove', str(self.target))
        self.assertEqual(self.cleanup()['cleanup'], 'complete')

    def test_pending_reason_is_durable_and_open_shared_pr_prevents_deletion(self):
        self.publish(merged=True)
        other = copy.deepcopy(self.prs[0]); other.update(number=2, state='open', merged_at=None)
        self.prs.append(other)
        result = self.cleanup()
        self.assertEqual(result['cleanup'], 'pending')
        self.assertIn('last_error', self.record()['cleanup'])
        self.assertTrue(self.remote_exists())
        self.assertTrue(self.target.exists())

    def test_supersession_survives_lost_close_response(self):
        self.publish()
        successor = self.successor()
        original = self.api
        lost = [False]
        def api(publication, endpoint, method='GET', payload=None, paginate=False):
            result = original(publication, endpoint, method, payload, paginate)
            if method == 'PATCH' and payload.get('state') == 'closed' and not lost[0]:
                lost[0] = True
                raise self.workflow.RemoteFailure('unknown', 'Lost close response')
            return result
        with patch.object(self.workflow, 'gh_api', side_effect=api):
            self.assertEqual(self.supersede(successor)['cleanup'], 'pending')
        self.assertEqual(self.supersede(successor)['cleanup'], 'complete')
        closes = [c for c in self.calls if c[1] == 'PATCH' and c[2].get('state') == 'closed']
        self.assertEqual(len(closes), 1)

    def test_unpublished_superseded_task_retains_local_commits(self):
        self.git(self.target, 'add', 'app.txt')
        self.git(self.target, 'commit', '-qm', 'unpublished work')
        head = self.git(self.target, 'rev-parse', 'HEAD')
        result = self.supersede(self.successor(), publication=self.publication)
        self.assertEqual(result['cleanup'], 'complete', result)
        self.assertFalse(self.target.exists())
        self.assertEqual(self.git(self.source, 'rev-parse', self.request['branch']), head)
        self.assertEqual(self.prs, [])

    def test_supersession_rejects_self_and_does_not_discard_dirty_work(self):
        self.publish()
        self.assertNotEqual(self.supersede(self.task['task_id'])['status'], 'ok')
        (self.target / 'app.txt').write_text('unfinished\n')
        result = self.supersede(self.successor())
        self.assertEqual(result['cleanup'], 'pending')
        self.assertTrue(self.target.exists())
        self.assertEqual((self.target / 'app.txt').read_text(), 'unfinished\n')

    def test_worktree_remote_opt_out_survives_removal_and_retries(self):
        self.policy('[task_lifecycle]\ndelete_remote_branches = false\n', self.target)
        event = self.event(files=['app.txt', '.codex/vibe-workflow.toml'])
        self.assertEqual(self.sync(event)['status'], 'ok')
        self.prs[0].update(state='closed', merged_at='2026-10-23T00:00:00Z', draft=False)
        self.assertEqual(self.cleanup()['cleanup'], 'complete')
        self.assertFalse(self.target.exists())
        self.assertTrue(self.remote_exists())
        self.assertEqual(self.cleanup()['cleanup'], 'complete')
        self.assertTrue(self.remote_exists())

    def test_supersession_closes_even_when_master_cleanup_is_disabled(self):
        self.publish()
        self.policy('[task_lifecycle]\nauto_cleanup = false\n')
        result = self.supersede(self.successor())
        self.assertEqual(result['cleanup'], 'disabled', result)
        self.assertEqual(self.prs[0]['state'], 'closed')
        self.assertTrue(self.prs[0]['title'].startswith('[SUPERSEDED] '))
        self.assertTrue(self.target.exists())
        self.assertTrue(self.remote_exists())

    def test_lifecycle_disable_prevents_supersession_mutation(self):
        self.publish()
        successor = self.successor()
        self.policy('[task_lifecycle]\nenabled = false\n')
        self.assertEqual(self.supersede(successor)['cleanup'], 'disabled')
        self.assertEqual(self.prs[0]['state'], 'open')

    def test_same_repository_pr_successor_and_closed_successor_rejection(self):
        self.publish()
        successor = copy.deepcopy(self.prs[0])
        successor.update(number=2, title='Replacement', state='closed', merged_at=None)
        successor['head']['ref'] = 'task/replacement'
        self.prs.append(successor)
        url = 'https://github.com/fixture/project/pull/2'
        self.assertNotEqual(self.supersede(url)['status'], 'ok')
        self.assertEqual(self.prs[0]['state'], 'open')
        successor['state'] = 'open'
        self.assertEqual(self.supersede(url)['cleanup'], 'complete')
        self.assertEqual(successor['state'], 'open')

    def test_reopened_superseded_pr_never_reclosed_or_cleaned_on_retry(self):
        self.publish()
        self.usage = {**self.usage, 'kind': 'managed'}
        successor = self.successor()
        self.assertEqual(self.supersede(successor)['cleanup'], 'pending')
        self.prs[0]['state'] = 'open'
        result = self.supersede(successor)
        self.assertEqual(result['cleanup'], 'pending')
        self.assertEqual(self.prs[0]['state'], 'open')
        self.assertTrue(self.target.exists())

    def test_reopen_race_before_remote_deletion_preserves_resources(self):
        self.publish(merged=True)
        original = self.workflow.save_lifecycle
        def reopen(state):
            original(state)
            if state['cleanup'].get('heads'):
                self.prs[0].update(state='open', merged_at=None)
        with patch.object(self.workflow, 'save_lifecycle', side_effect=reopen):
            self.assertEqual(self.cleanup()['cleanup'], 'pending')
        self.assertTrue(self.remote_exists())
        self.assertTrue(self.target.exists())

    def test_supersession_retry_rechecks_authenticated_actor_before_mutation(self):
        self.publish()
        successor = self.successor()
        original = self.api
        def deny_close(publication, endpoint, method='GET', payload=None, paginate=False):
            if method == 'PATCH':
                raise self.workflow.RemoteFailure('access', 'Unavailable')
            return original(publication, endpoint, method, payload, paginate)
        with patch.object(self.workflow, 'gh_api', side_effect=deny_close):
            self.assertEqual(self.supersede(successor)['cleanup'], 'pending')
        self.actor = 'different-account'
        self.assertEqual(self.supersede(successor)['cleanup'], 'pending')
        self.assertEqual(self.prs[0]['state'], 'open')
        self.assertFalse(self.prs[0]['title'].startswith('[SUPERSEDED] '))

    def test_supersession_never_rewrites_merged_predecessor(self):
        self.publish(merged=True)
        self.assertNotEqual(self.supersede(self.successor())['status'], 'ok')
        self.assertFalse(self.prs[0]['title'].startswith('[SUPERSEDED] '))

    def test_superseded_prefix_validation(self):
        title, _ = self.workflow.render_pr('[READY] Human title', '', self.task['task_id'], 'SUPERSEDED', 'Replacement recorded')
        self.assertEqual(title, '[SUPERSEDED] Human title')
        for title in ('[SUPERSEDED][READY] Bad', '[SUPERSEDED] [READY] Bad'):
            with self.assertRaises(ValueError):
                self.workflow.render_pr(title, '', self.task['task_id'], 'SUPERSEDED', 'Replacement recorded')

    def test_retry_after_removal_preserves_branch_used_by_another_worktree(self):
        self.publish(merged=True)
        self.policy('[task_lifecycle]\ndelete_remote_branches = false\n')
        self.assertEqual(self.cleanup()['cleanup'], 'complete')
        other = self.home / 'other-checkout'
        self.git(self.source, 'worktree', 'add', str(other), self.request['branch'])
        self.policy('[task_lifecycle]\n')
        result = self.cleanup()
        self.assertEqual(result['cleanup'], 'pending', result)
        self.assertTrue(self.remote_exists())
        self.assertTrue(other.exists())

    def test_task_successor_rejects_closed_unmerged_publication(self):
        self.publish()
        successor = self.successor()
        original_task, original_target, original_publication = self.task, self.target, self.publication
        self.target = self.home / 'successor'
        self.task = {'task_id': successor, 'worktree': str(self.target)}
        self.publication = {**self.publication, 'branches': ['task/successor']}
        (self.target / 'app.txt').write_text('replacement\n')
        self.assertEqual(self.sync(self.event('checkpoint'))['status'], 'ok')
        self.task, self.target, self.publication = original_task, original_target, original_publication
        self.prs[1]['state'] = 'closed'
        result = self.supersede(successor)
        self.assertNotEqual(result['status'], 'ok', result)
        self.assertEqual(self.prs[0]['state'], 'open')
        self.assertTrue(self.remote_exists())
        self.assertTrue(self.target.exists())
        self.prs[1]['state'] = 'open'
        self.assertEqual(self.supersede(successor)['cleanup'], 'complete')
