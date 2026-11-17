"""Offline synthetic comparisons; never claims a human reviewer actually participated."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from blind_compare import prepare, reveal, score


class BlindComparisonTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.work = self.root / 'working'
        self.work.mkdir()
        brief = self.work / 'UAT_APPROVED_PROJECT_BRIEF.md'
        brief.write_text('Synthetic project, no production assets')
        bar = {'schema_version': 1, 'tasks': {'build': {
            'goal': 'Test the onboarding interface', 'audience': 'new users',
            'references': [{'path': brief.name, 'sha256': hashlib.sha256(brief.read_bytes()).hexdigest()}],
            'gates': [{'id': f'G{i}', 'requirement': f'Gate {i}',
                       'pass_condition': f'Pass {i}', 'test_method': 'human inspection',
                       'evidence_required': f'Observation {i}'} for i in range(1, 6)]
        }}}
        (self.work / 'UAT_QUALITY_BAR.json').write_text(json.dumps(bar))
        self.before = self.work / 'first.html'
        self.after = self.work / 'second.html'
        self.before.write_text('<main>Artwork card</main>')
        self.after.write_text('<main>Artwork card updated</main>')
        self.packet = self.root / 'review_packet'
        self.private = self.root / 'private_mapping'

    def prepare(self):
        return prepare(self.work, self.before, self.after, 'build', self.packet, self.private)

    def test_random_label_orders_are_hidden_until_scored(self):
        for random_value, expected_a in ((0, 'after'), (1, 'before')):
            with self.subTest(seed=random_value):
                packet, private = (self.root / f'packet_{random_value}',
                                   self.root / f'private_{random_value}')
                with patch('blind_compare.secrets.randbelow', return_value=random_value):
                    outcome = prepare(self.work, self.before, self.after, 'build', packet, private)
                self.assertEqual(outcome['status'], 'PACKET_PREPARED')
                self.assertNotIn('before', json.dumps(outcome))
                self.assertEqual(sorted(p.name for p in packet.iterdir()),
                                 ['A.html', 'B.html', 'QUALITY_BAR.json', 'REFERENCES',
                                  'REVIEW_INSTRUCTIONS.md'])
                self.assertEqual((packet / 'REFERENCES' / 'UAT_APPROVED_PROJECT_BRIEF.md').read_bytes(),
                                 (self.work / 'UAT_APPROVED_PROJECT_BRIEF.md').read_bytes())
                with self.assertRaisesRegex(ValueError, 'score must be recorded'):
                    reveal(packet, private)
                scored = score(packet, private, 'A', ['G1', 'G2'], ['G1'], 'A reads more clearly')
                self.assertFalse(scored['mapping_revealed'])
                result = reveal(packet, private)
                self.assertEqual(result['assignments']['A'], expected_a)
                self.assertEqual(result['preferred_version'], expected_a)
                self.assertEqual(result['independence'], 'NOT_VERIFIED_SELF_REPORTED_HUMAN')
        self.assertEqual(self.before.read_text(), '<main>Artwork card</main>')
        self.assertEqual(self.after.read_text(), '<main>Artwork card updated</main>')

    def test_invalid_gate_scores_and_second_score_are_blocked(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError, 'Invalid or duplicate'):
            score(self.packet, self.private, 'A', ['G9'], [], 'Unsupported gate')
        score(self.packet, self.private, 'TIE', ['G1'], ['G1'], 'Both need improvement')
        with self.assertRaisesRegex(ValueError, 'already scored'):
            score(self.packet, self.private, 'B', [], [], 'Attempted overwrite')
        self.assertEqual(reveal(self.packet, self.private)['preferred_version'], 'TIE')

    def test_changed_packet_or_rubric_cannot_be_scored(self):
        self.prepare()
        (self.packet / 'A.html').write_text('Changed after preparation')
        with self.assertRaisesRegex(ValueError, 'artifact A changed'):
            score(self.packet, self.private, 'A', [], [], 'This packet was tampered')

    def test_changed_reference_blocks_scoring(self):
        self.prepare()
        (self.packet / 'REFERENCES' / 'UAT_APPROVED_PROJECT_BRIEF.md').write_text('Different scope')
        with self.assertRaisesRegex(ValueError, 'reference changed'):
            score(self.packet, self.private, 'A', [], [], 'Reference was tampered')

    def test_packet_and_private_mapping_cannot_be_inside_working_copy(self):
        with self.assertRaisesRegex(ValueError, 'separate from the working copy'):
            prepare(self.work, self.before, self.after, 'build', self.work / 'packet', self.private)
        self.assertFalse((self.work / 'packet').exists())
        with self.assertRaisesRegex(ValueError, 'separate from the working copy'):
            prepare(self.work, self.before, self.after, 'build', self.packet, self.packet / 'private')

    def test_unknown_task_and_same_artifact_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'two different'):
            prepare(self.work, self.before, self.before, 'build', self.packet, self.private)
        with self.assertRaisesRegex(ValueError, 'not present'):
            prepare(self.work, self.before, self.after, 'deploy', self.packet, self.private)
        self.assertFalse(self.packet.exists())


if __name__ == '__main__':
    unittest.main()
