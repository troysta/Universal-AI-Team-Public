"""Offline first-run checks for the one-command supervised starter."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


INSTALLER = Path(__file__).resolve().parents[1] / 'install.py'


class QuickInstallTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.project = self.root / 'MyArtProject'
        self.project.mkdir()
        (self.project / 'README.md').write_text('Art Vault test project')
        (self.project / '.env').write_text('TEST_ONLY=PLACEHOLDER')
        (self.project / 'id_rsa').write_text('NOT_A_REAL_KEY')
        self.working = self.root / 'MyArtProject_uat_working'
        self.control = self.root / 'MyArtProject_uat_working_control'

    def run_installer(self, *flags):
        return subprocess.run([sys.executable, str(INSTALLER), *flags],
                              capture_output=True, text=True, check=False)

    def test_doctor_reports_security_unverified(self):
        result = self.run_installer('--doctor')
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['native_agent_dispatch'], 'NOT_TESTED')
        self.assertEqual(report['agent_file_isolation'], 'NOT_TESTED')
        self.assertEqual(report['authenticated_owner_approval'], 'NOT_TESTED')

    def test_preview_creates_nothing_and_excludes_sensitive_files(self):
        result = self.run_installer('--project', str(self.project), '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        preview = json.loads(result.stdout)
        self.assertEqual(preview['status'], 'PREVIEW_ONLY')
        self.assertEqual(preview['included_file_count'], 1)
        self.assertFalse(self.working.exists())
        self.assertFalse(self.control.exists())
        self.assertEqual((self.project / '.env').read_text(), 'TEST_ONLY=PLACEHOLDER')

    def test_create_keeps_original_and_places_control_outside(self):
        result = self.run_installer('--project', str(self.project), '--create',
                                    '--goal', 'Inspect artwork card', '--json')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        prepared = json.loads(result.stdout)
        self.assertEqual(prepared['status'], 'WORKING_COPY_PREPARED')
        self.assertTrue((self.working / 'README.md').is_file())
        self.assertFalse((self.working / '.env').exists())
        self.assertFalse((self.working / 'id_rsa').exists())
        self.assertTrue((self.working / 'UAT_PROJECT_BRIEF_DRAFT.md').is_file())
        host_guide = (self.working / 'UAT_START_WITH_AI_HOST.md').read_text()
        self.assertIn('Before launching any agent', host_guide)
        self.assertIn(str(INSTALLER.parent / 'controller' / 'start.py'), host_guide)
        self.assertLess(host_guide.index('Before launching any agent'),
                        host_guide.index('launch a dedicated native Architect'))
        self.assertTrue((self.control / 'UAT_CONTROL_RECORD.json').is_file())
        self.assertEqual((self.project / 'README.md').read_text(), 'Art Vault test project')
        self.assertFalse((self.project / 'UAT_START_WITH_AI_HOST.md').exists())

    def test_refuse_overwrite_after_initial_creation(self):
        args = ('--project', str(self.project), '--create', '--json')
        self.assertEqual(self.run_installer(*args).returncode, 0)
        retry = self.run_installer(*args)
        self.assertEqual(retry.returncode, 2)
        self.assertIn('refusing overwrite', json.loads(retry.stdout)['reason'])

    def test_missing_project_is_explicitly_blocked(self):
        result = self.run_installer('--json')
        self.assertEqual(result.returncode, 2)
        self.assertIn('--project', json.loads(result.stdout)['reason'])
        self.assertFalse(self.working.exists())

    def test_original_project_cannot_be_output(self):
        result = self.run_installer('--project', str(self.project), '--create',
                                    '--output', str(self.project), '--json')
        self.assertEqual(result.returncode, 2)
        self.assertIn('separate', json.loads(result.stdout)['reason'])
        self.assertEqual((self.project / 'README.md').read_text(), 'Art Vault test project')


if __name__ == '__main__':
    unittest.main()
