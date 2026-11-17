import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import signing
from activate_personal import prepare
from control_record import RECORD_NAME, verify_brief
from critic_evidence import RESIDUAL_LEAK_PATHS, assess_isolation
from critic_harness import record_inspection, run_trial
from project_discovery import approve_brief, create_draft

SUPPORT = Path(__file__).resolve().parent / 'support'
CONTROLLER = Path(__file__).resolve().parent.parent / 'controller'
COMPLETE = ('# Goal\nOffline app\n## Audience\nArtists\n## Scope\nInventory\n'
            '## Constraints\nNo publishing\n## Acceptance criteria\nOpens locally\n')


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.source = self.root / 'project'
        self.source.mkdir()
        (self.source / 'PROJECT_BRIEF.md').write_text(COMPLETE)
        self.work = self.root / 'project_uat_working'
        self.private_path, self.public_path = signing.create_keypair(
            self.root / 'owner_keys' / 'private.pem', self.root / 'owner_keys' / 'public.pem')
        self.private = signing.load_private_key(self.private_path)
        self.public = signing.load_public_key(self.public_path)
        prepare(self.source, self.work, 'Build it', create=True)
        create_draft(self.work, 'Build it')

    def approve(self, signed=True):
        digest = hashlib.sha256((self.work / 'UAT_PROJECT_BRIEF_DRAFT.md').read_bytes()).hexdigest()
        approve_brief(self.work, digest, private_key=self.private if signed else None)


class SignedApprovalTests(Base):
    def test_signed_approval_verifies_with_key(self):
        self.approve()
        self.assertEqual(verify_brief(self.work, public_key=self.public)['status'], 'OK')

    def test_unsigned_approval_fails_when_key_required(self):
        self.approve(signed=False)
        with self.assertRaisesRegex(ValueError, 'signature missing or invalid'):
            verify_brief(self.work, public_key=self.public)

    def forge(self, signature):
        record_path = self.work.with_name(self.work.name + '_control') / RECORD_NAME
        os.chmod(record_path, 0o644)
        record = json.loads(record_path.read_text())
        record['approval_signature'] = signature
        record_path.write_text(json.dumps(record))

    def test_forged_approval_in_control_record_fails(self):
        self.approve()
        self.forge({'alg': 'Ed25519', 'value': 'AAAA'})
        with self.assertRaisesRegex(ValueError, 'signature'):
            verify_brief(self.work, public_key=self.public)

    def test_approval_signed_by_another_key_fails(self):
        self.approve()
        other_private, _ = signing.create_keypair(self.root / 'agent' / 'p.pem',
                                                  self.root / 'agent' / 'q.pem')
        from control_record import approval_payload
        digest = json.loads((self.work.with_name(self.work.name + '_control') / RECORD_NAME)
                            .read_text())['approved_brief_sha256']
        forged = signing.attach(approval_payload(self.work, digest),
                                signing.load_private_key(other_private))
        self.forge(forged['signature'])
        with self.assertRaisesRegex(ValueError, 'signature'):
            verify_brief(self.work, public_key=self.public)

    def test_key_inside_working_copy_or_world_readable_is_refused(self):
        inside, inside_public = signing.create_keypair(self.work / 'k.pem', self.work / 'k.pub')
        with self.assertRaisesRegex(ValueError, 'inside the working copy'):
            signing.load_private_key(inside, not_inside=[self.work])
        with self.assertRaisesRegex(ValueError, 'inside the working copy'):
            signing.load_public_key(inside_public, not_inside=[self.work])
        loose, _ = signing.create_keypair(self.root / 'loose.pem', self.root / 'loose.pub')
        os.chmod(loose, 0o644)
        with self.assertRaisesRegex(ValueError, 'readable by other users'):
            signing.load_private_key(loose)


class HarnessTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.work = self.root / 'working'
        self.work.mkdir()
        self.private = self.root / 'author_private'
        self.private.mkdir()
        self.notes = self.private / 'builder_notes.md'
        self.notes.write_text('The null bug on line 40 is intended.\n')
        self.evidence = self.root / 'evidence'
        self.private_path, self.public_path = signing.create_keypair(
            self.root / 'owner_keys' / 'private.pem', self.root / 'owner_keys' / 'public.pem')
        self.leaks = {leak: 'not mitigated in test' for leak in RESIDUAL_LEAK_PATHS}

    def critic(self, isolated):
        launcher = ([sys.executable, str(SUPPORT / 'fake_sandbox.py'), str(self.private), '--']
                    if isolated else [])
        return {'role': 'specialist_critic', 'model': 'test-model', 'launcher': launcher,
                'command': [sys.executable, str(SUPPORT / 'fake_critic.py'), str(self.notes)],
                'prompt': 'Review artifact.txt against the approved spec only.',
                'forbidden_path': str(self.notes), 'python': sys.executable,
                'permissions': ['read artifact'], 'readable_paths': [str(self.work)],
                'writable_paths': [str(self.root / 'critic_out')]}

    def trial(self, isolated, trial_id='T-1'):
        return run_trial(trial_id=trial_id, working_copy=self.work, evidence_dir=self.evidence,
                         signing_key_path=self.private_path, critics=[self.critic(isolated)],
                         residual_leak_paths=self.leaks, timeout=60)

    def test_isolated_trial_needs_inspection_then_is_evidenced(self):
        path = self.trial(isolated=True)
        record = json.loads(path.read_text())
        entry = record['critics'][0]
        self.assertEqual(entry['forbidden_read']['result'], 'DENIED')
        self.assertEqual(entry['canary']['result'], 'CLEAN')
        self.assertEqual(entry['launch_prompt'], self.critic(True)['prompt'])
        self.assertEqual(path.stat().st_mode & 0o222, 0)
        pending = assess_isolation(path, self.work, self.public_path)
        self.assertEqual(pending['isolation'], 'BLOCKED')
        self.assertTrue(any('inspection' in p for p in pending['problems']))
        record_inspection(path, self.private_path, 0, 'PASS', 'Project Owner')
        result = assess_isolation(path, self.work, self.public_path)
        self.assertEqual(result['isolation'], 'EVIDENCED', result['problems'])

    def test_unisolated_critic_is_caught(self):
        path = self.trial(isolated=False)
        entry = json.loads(path.read_text())['critics'][0]
        self.assertEqual(entry['forbidden_read']['result'], 'SUCCEEDED')
        self.assertEqual(entry['canary']['result'], 'LEAKED')
        record_inspection(path, self.private_path, 0, 'PASS', 'Project Owner')
        self.assertEqual(assess_isolation(path, self.work, self.public_path)['isolation'], 'BLOCKED')

    def test_tampered_harness_record_blocks_and_refuses_inspection(self):
        path = self.trial(isolated=False)
        os.chmod(path, 0o644)
        record = json.loads(path.read_text())
        record['critics'][0]['canary']['result'] = 'CLEAN'
        record['critics'][0]['forbidden_read']['result'] = 'DENIED'
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, 'signature invalid'):
            record_inspection(path, self.private_path, 0, 'PASS', 'Project Owner')
        self.assertEqual(assess_isolation(path, self.work, self.public_path)['isolation'], 'BLOCKED')

    def test_harness_refuses_unsafe_setup(self):
        with self.assertRaisesRegex(ValueError, 'outside the working copy'):
            run_trial(trial_id='T', working_copy=self.work, evidence_dir=self.work / 'ev',
                      signing_key_path=self.private_path, critics=[], residual_leak_paths=self.leaks)
        partial = dict(self.leaks)
        del partial['network_access']
        with self.assertRaisesRegex(ValueError, 'network_access'):
            run_trial(trial_id='T', working_copy=self.work, evidence_dir=self.evidence,
                      signing_key_path=self.private_path, critics=[], residual_leak_paths=partial)
        self.trial(isolated=True)
        with self.assertRaises(FileExistsError):
            self.trial(isolated=True)

    def test_trial_id_and_role_cannot_escape_evidence_directory(self):
        for bad_id in ('../escape', '/tmp/escape', 'T/../../escape', '..\\escape'):
            with self.subTest(trial_id=bad_id), self.assertRaisesRegex(ValueError, 'safe filename'):
                self.trial(isolated=True, trial_id=bad_id)
        self.assertFalse((self.root / 'escape.json').exists())
        bad_critic = self.critic(True)
        bad_critic['role'] = '../../control'
        with self.assertRaisesRegex(ValueError, 'safe filename'):
            run_trial(trial_id='T-role', working_copy=self.work, evidence_dir=self.evidence,
                      signing_key_path=self.private_path, critics=[bad_critic],
                      residual_leak_paths=self.leaks)

    def test_preexisting_output_symlink_cannot_overwrite_other_file(self):
        victim = self.root / 'victim.txt'
        victim.write_text('preserve these bytes')
        self.evidence.mkdir()
        (self.evidence / 'T-symlink_0_specialist_critic_output.txt').symlink_to(victim)
        with self.assertRaisesRegex(ValueError, 'escapes the evidence folder'):
            self.trial(isolated=True, trial_id='T-symlink')
        self.assertEqual(victim.read_text(), 'preserve these bytes')

    def test_canary_rejects_signing_key_as_notes_file(self):
        critic = self.critic(True)
        critic['forbidden_path'] = str(self.private_path)
        original = self.private_path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Canary notes'):
            run_trial(trial_id='T-key', working_copy=self.work, evidence_dir=self.evidence,
                      signing_key_path=self.private_path, critics=[critic],
                      residual_leak_paths=self.leaks)
        self.assertEqual(self.private_path.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
