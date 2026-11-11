# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Recovery parity; real client normalization, no installed operations or database."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest

from .agents.torrenter.client import publication_status

WORKSPACE_JS = Path(__file__).resolve().parent / "torrenter_workspace" / "workspace.js"
UUID4 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


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


class WorkspaceOperationKeyTests(unittest.TestCase):
    """Over plain HTTP from a LAN address the browser has no crypto.randomUUID."""

    def source(self):
        return WORKSPACE_JS.read_text(encoding="utf-8")

    def test_every_mutation_key_comes_from_the_fallback_helper(self):
        text = self.source()
        self.assertEqual(text.count("crypto.randomUUID()"), 1)  # only inside operationKey
        self.assertIn("typeof crypto.randomUUID === 'function'", text)
        self.assertGreaterEqual(text.count("operationKey()"), 10)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_key_is_a_v4_uuid_without_a_secure_context(self):
        helper = re.search(r"function operationKey\(\) \{.*?\n\}", self.source(), re.S).group(0)
        script = (
            "const vm = require('vm'); const nodeCrypto = require('crypto');"
            "const context = {crypto: {getRandomValues: a => nodeCrypto.randomFillSync(a)}};"
            "vm.runInNewContext(" + json.dumps(helper) + ", context);"
            "const keys = Array.from({length: 64}, () => vm.runInNewContext('operationKey()', context));"
            "console.log(JSON.stringify(keys));"
        )
        run = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True, timeout=60,
                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        keys = json.loads(run.stdout)
        self.assertEqual(len(set(keys)), 64)
        for key in keys:
            self.assertRegex(key, UUID4)


if __name__ == '__main__':
    unittest.main(verbosity=2)
