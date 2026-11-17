import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from shutil import copytree


PACKAGE = Path(__file__).resolve().parent.parent / 'controller'


class DropInActivationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name) / 'fresh_project'
        self.project.mkdir()
        (self.project / 'README.md').write_text('Synthetic project only\n')
        (self.project / '.env').write_text('FAKE_TOKEN=excluded\n')
        copytree(PACKAGE, self.project / 'Universal_AI_Team')
        self.target = self.project.with_name('fresh_project_uat_working')

    def run_start(self, *args):
        r = subprocess.run([sys.executable, str(self.project / 'Universal_AI_Team' / 'start.py'),
                            '--goal', 'Build an offline task-list', *args],
                           cwd=self.project, capture_output=True, text=True)
        return r, json.loads(r.stdout)

    def test_preview_does_not_write(self):
        result, data = self.run_start()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(data['status'], 'PREVIEW_ONLY')
        self.assertEqual(data['included_file_count'], 1)
        self.assertFalse(self.target.exists())

    def test_create_handoff_and_protect_source(self):
        before = (self.project / 'README.md').read_bytes()
        result, data = self.run_start('--create')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(data['status'], 'WORKING_COPY_PREPARED')
        self.assertEqual((self.project / 'README.md').read_bytes(), before)
        self.assertEqual((self.target / 'README.md').read_bytes(), before)
        self.assertFalse((self.target / '.env').exists())
        self.assertFalse((self.target / 'Universal_AI_Team').exists())
        handoff = (self.target / 'UAT_START_WITH_AI_HOST.md').read_text()
        self.assertIn('Project Owner', handoff)
        self.assertNotIn('Harry', handoff)
        self.assertNotIn('PERSONAL_OWNER_NAME', handoff)
        state = json.loads((self.target / 'UAT_PERSONAL_HANDOFF.json').read_text())
        self.assertEqual(state['plan_owner_approval'], 'REQUIRED')
        self.assertFalse(state['native_agents_launched'])

    def test_refuse_overwrite(self):
        self.assertEqual(self.run_start('--create')[0].returncode, 0)
        again, data = self.run_start('--create')
        self.assertEqual(again.returncode, 2)
        self.assertEqual(data['status'], 'BLOCKED')

    def test_nested_output_rejected(self):
        result, data = self.run_start('--create', '--output', 'inside')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(data['status'], 'BLOCKED')

    def test_activation_without_goal_creates_questioned_brief(self):
        r = subprocess.run([sys.executable, str(self.project / 'Universal_AI_Team' / 'start.py'),
                            '--create'], cwd=self.project, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        handoff = json.loads((self.target / 'UAT_PERSONAL_HANDOFF.json').read_text())
        self.assertEqual(handoff['state'], 'AWAITING_OWNER_BRIEF_APPROVAL')
        draft = (self.target / 'UAT_PROJECT_BRIEF_DRAFT.md').read_text()
        self.assertIn('[OWNER TO COMPLETE: What are you trying to build?]', draft)
        self.assertFalse((self.target / 'UAT_APPROVED_PROJECT_BRIEF.md').exists())


if __name__ == '__main__':
    unittest.main()
