import json
import tempfile
import unittest
from pathlib import Path

from activate_personal import prepare


class PersonalStarterTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.source=self.root/'fresh_project'
        self.source.mkdir()
        (self.source/'README.md').write_text('New synthetic project')
        (self.source/'app.py').write_text('print("hello")\n')
        (self.source/'.env').write_text('SYNTHETIC_DO_NOT_COPY=1')
        self.out=self.root/'working'

    def test_preview_is_read_only_and_does_not_create_target(self):
        report=prepare(self.source,self.out,'Build a tiny demo')
        self.assertEqual(report['status'],'PREVIEW_ONLY')
        self.assertFalse(self.out.exists())

    def test_one_step_create_preserves_source_and_excludes_common_secrets(self):
        before=(self.source/'README.md').read_bytes()
        report=prepare(self.source,self.out,'Build a tiny demo',create=True)
        self.assertEqual(report['status'],'WORKING_COPY_PREPARED')
        self.assertEqual((self.source/'README.md').read_bytes(),before)
        self.assertEqual((self.out/'README.md').read_bytes(),before)
        self.assertFalse((self.out/'.env').exists())
        self.assertTrue((self.out/'UAT_PERSONAL_HANDOFF.json').exists())
        text=(self.out/'UAT_START_WITH_AI_HOST.md').read_text()
        self.assertIn('owner approval',text)
        self.assertIn('AI Host',text)
        self.assertIn('Project Owner',text)
        self.assertNotIn('Harry',text)
        self.assertNotIn('PERSONAL_OWNER_NAME',text)

    def test_protected_material_and_secret_file_variants_are_excluded(self):
        excluded_dirs = ('protected_baselines', 'internal_trials', 'private_handoffs',
                         'private', 'backups')
        for folder in excluded_dirs:
            directory = self.source / folder
            directory.mkdir()
            (directory / 'record.md').write_text('SYNTHETIC_PRIVATE_RECORD')
        (self.source / '.env.local').write_text('SYNTHETIC_ENV=1')
        (self.source / '.ENV.PRODUCTION').write_text('SYNTHETIC_ENV=2')
        (self.source / 'client.key').write_text('SYNTHETIC_KEY')
        (self.source / 'certificate.PEM').write_text('SYNTHETIC_CERT')
        nested = self.source / 'nested'
        nested.mkdir()
        nested_secrets = nested / 'SECRETS'
        nested_secrets.mkdir()
        (nested_secrets / 'token.txt').write_text('SYNTHETIC_TOKEN')
        nested_baseline = nested / 'PROTECTED_BASELINES'
        nested_baseline.mkdir()
        (nested_baseline / 'record.txt').write_text('SYNTHETIC_RECORD')

        preview = prepare(self.source, self.out, 'Protect sensitive project files')
        self.assertEqual(preview['included_file_count'], 2)
        self.assertIn('.env.*', preview['excluded_patterns'])
        self.assertFalse(self.out.exists())

        prepare(self.source, self.out, 'Protect sensitive project files', create=True)
        for folder in excluded_dirs:
            self.assertFalse((self.out / folder).exists(), folder)
            self.assertTrue((self.source / folder / 'record.md').exists(), folder)
        for filename in ('.env.local', '.ENV.PRODUCTION', 'client.key',
                         'certificate.PEM'):
            self.assertFalse((self.out / filename).exists(), filename)
        self.assertFalse((self.out / 'nested' / 'SECRETS').exists())
        self.assertFalse((self.out / 'nested' / 'PROTECTED_BASELINES').exists())
        self.assertTrue((self.out / 'README.md').exists())
        self.assertTrue((self.out / 'app.py').exists())
        metadata = json.loads((self.out / 'UAT_PERSONAL_HANDOFF.json').read_text())
        self.assertEqual(metadata['file_inventory'], ['README.md', 'app.py'])

    def test_existing_output_not_overwritten(self):
        self.out.mkdir()
        with self.assertRaises(FileExistsError):
            prepare(self.source,self.out,'Any task',create=True)

    def test_nested_target_is_blocked(self):
        with self.assertRaises(ValueError):
            prepare(self.source,self.source/'working','Any task',create=True)

    def test_symlink_is_rejected(self):
        (self.source/'pointer').symlink_to(self.source/'README.md')
        with self.assertRaisesRegex(ValueError,'Symlinks'):
            prepare(self.source,self.out,'Any task',create=True)

    def test_no_goal_is_blocked(self):
        with self.assertRaises(ValueError):
            prepare(self.source,self.out,' ',create=True)


if __name__=='__main__':
    unittest.main()
