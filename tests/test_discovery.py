import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from control_record import init_record
from project_discovery import inspect, create_draft, approve_brief


class ProjectDiscoveryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.work = self.root / 'working'
        self.work.mkdir()
        init_record(self.root / 'working_control', self.work, {'state': 'AWAITING_ARCHITECT'})
        (self.work / 'UAT_PERSONAL_HANDOFF.json').write_text(json.dumps({'state': 'AWAITING_ARCHITECT'}))
        (self.work / 'UAT_START_WITH_AI_HOST.md').write_text('AI Host prepares Architect.\n')

    def test_empty_project(self):
        self.assertEqual(inspect(self.work)['discovery'], 'NO_BRIEF_FOUND')
        result = create_draft(self.work, 'Build a tiny app')
        self.assertEqual(result['state'], 'AWAITING_OWNER_BRIEF_APPROVAL')
        self.assertIn('[OWNER TO COMPLETE', (self.work / 'UAT_PROJECT_BRIEF_DRAFT.md').read_text())
        self.assertIn('Do not launch agents', (self.work / 'UAT_START_WITH_AI_HOST.md').read_text())

    def test_no_brief_but_code(self):
        (self.work / 'app.js').write_text('const idea = true;\n')
        self.assertEqual(inspect(self.work)['discovery'], 'NO_BRIEF_FOUND')

    def test_incomplete_overview(self):
        (self.work / 'README.md').write_text('# Idea\nSomething to build.\n')
        result = create_draft(self.work, 'Try an idea')
        self.assertEqual(result['discovery'], 'INCOMPLETE_OR_UNVERIFIED_BRIEF')
        self.assertIn('Something to build', (self.work / 'UAT_PROJECT_BRIEF_DRAFT.md').read_text())

    def test_partial_brief_does_not_pass(self):
        (self.work / 'PROJECT_BRIEF.md').write_text('# Goal\nA tiny app\n## Audience\n\n')
        self.assertEqual(inspect(self.work)['discovery'], 'INCOMPLETE_OR_UNVERIFIED_BRIEF')

    def test_complete_brief_still_awaits_owner(self):
        (self.work / 'PROJECT_BRIEF.md').write_text(
            '# Goal\nOffline app\n## Audience\nArtists\n## Scope\nInventory\n'
            '## Constraints\nNo publishing\n## Acceptance criteria\nOpens locally\n')
        result = create_draft(self.work, 'Start project')
        self.assertEqual(result['discovery'], 'COMPLETE_BRIEF_FOUND')
        self.assertEqual(result['state'], 'AWAITING_OWNER_BRIEF_APPROVAL')
        self.assertNotIn('[OWNER TO COMPLETE', (self.work / 'UAT_PROJECT_BRIEF_DRAFT.md').read_text())

    def test_approval_hash_and_placeholder_gate(self):
        create_draft(self.work, 'Build a tiny app')
        draft = self.work / 'UAT_PROJECT_BRIEF_DRAFT.md'
        initial = hashlib.sha256(draft.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, 'Complete all owner-input'):
            approve_brief(self.work, initial)
        content = draft.read_text().replace('[OWNER TO COMPLETE: Who is this for?]', 'Local artists')
        content = content.replace('[OWNER TO COMPLETE: What features and deliverables are included?]', 'A simple list')
        content = content.replace('[OWNER TO COMPLETE: What must not change, and which files are protected?]', 'README is protected')
        content = content.replace('[OWNER TO COMPLETE: How will we know it works?]', 'Open locally and add one item')
        draft.write_text(content)
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            approve_brief(self.work, initial)
        new_hash = hashlib.sha256(draft.read_bytes()).hexdigest()
        result = approve_brief(self.work, new_hash)
        self.assertEqual(result['state'], 'AWAITING_ARCHITECT')
        self.assertEqual(json.loads((self.work / 'UAT_PERSONAL_HANDOFF.json').read_text())['brief_owner_approval'],
                         'OWNER_ACTION_RECORDED_NOT_AUTHENTICATED')
        with self.assertRaises(ValueError):
            approve_brief(self.work, new_hash)


if __name__ == '__main__':
    unittest.main()
