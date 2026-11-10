# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Recovery parity; real client normalization, no installed operations or database."""
import unittest

from .agents.torrenter.client import publication_status


class RecoveryTests(unittest.TestCase):
    def state(self, **changes):
        return {'job_id':'a'*32, 'selected_bytes':10, 'verified_bytes':5,
                'phase':'stopped', 'desired_state':'stopped', **changes}

    def test_finished_stopped_job_does_not_offer_restart(self):
        original = self.state(completed_at=123, error='old verification failure')
        result = publication_status(original)
        self.assertEqual(result['phase'], 'completed')
        self.assertEqual(result['transfer_state'], 'stopped')
        self.assertEqual(result['desired_state'], 'stopped')
        self.assertEqual(result['previous_error'], original['error'])
        self.assertNotIn('error', result)
        self.assertIsNone(result['restart_action'])
        self.assertTrue(result['download_complete'])
        self.assertEqual(original['phase'], 'stopped')

    def test_incomplete_recovery_actions_are_state_specific(self):
        for phase, action in (('stopped','start'),('paused','resume'),('failed','recheck')):
            result = publication_status(self.state(phase=phase, error='current error'))
            self.assertEqual(result['restart_action'], action)
            self.assertEqual(result['error'], 'current error')
            self.assertTrue(result['recovery_note'])

    def test_waiting_for_peers_does_not_promise_restart_success(self):
        result = publication_status(self.state(phase='waiting_for_peers', desired_state='running', known_seeds=4, seeds=0))
        self.assertIsNone(result['restart_action'])
        self.assertTrue(result['recovery_note'])
        self.assertEqual(result['seeds'], 0)

    def test_list_normalizes_each_owned_job_without_claiming_delivery(self):
        result = publication_status({'items':[self.state(completed_at=123, delivery_state='failed', delivery_error='Disk full'), self.state()]})
        self.assertEqual(result['items'][0]['delivery_error'], 'Disk full')
        self.assertNotIn('verified', result['items'][0])
        self.assertEqual(result['items'][1]['restart_action'], 'start')

    def test_active_seeding_error_is_not_suppressed_by_completion(self):
        result = publication_status(self.state(phase='failed', completed_at=123, error='Disk offline'))
        self.assertEqual(result['error'], 'Disk offline')
        self.assertEqual(result['phase'], 'failed')
        self.assertEqual(result['restart_action'], 'recheck')
        self.assertIn('Recheck', result['recovery_note'])

    def test_stalled_retry_remains_automatic_and_normalization_is_idempotent(self):
        result = publication_status(self.state(phase='queued', desired_state='running', queue_reason='stalled_retry', retry_in_seconds=60))
        self.assertIsNone(result['restart_action'])
        self.assertEqual(publication_status(result), result)


if __name__ == '__main__':
    unittest.main(verbosity=2)
