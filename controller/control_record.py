"""Authoritative approval record kept OUTSIDE the agents' working copy.

The working copy is where agents write, so approval state there cannot be
trusted. This module keeps the authoritative state and the approved brief in a
separate control folder (default: sibling ``<working_copy>_control``) and
re-checks the approved brief before each stage.

Protection is by location plus read-only file mode. It is NOT a sandbox: an
agent running as the same OS user could still change these files. Full
protection needs agents to run under a different user or a sandbox that
cannot write to the control folder.
"""
import hashlib
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path

import signing


RECORD_NAME = 'UAT_CONTROL_RECORD.json'
APPROVED_COPY_NAME = 'APPROVED_PROJECT_BRIEF.md'
WORKING_APPROVED_NAME = 'UAT_APPROVED_PROJECT_BRIEF.md'
PROTECTION = 'OUTSIDE_WORKING_COPY_READ_ONLY_MODE_NOT_SANDBOX'
STAGES = ('architect', 'architect_critic', 'specialist', 'specialist_critic',
          'final_critic', 'promotion_proposal', 'promotion', 'release', 'subagent_launch')


def default_control_dir(working_copy):
    working = Path(working_copy).resolve()
    return working.with_name(working.name + '_control')


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def write_protected(path, data):
    """Write text or bytes and leave the file read-only (best effort, not a sandbox)."""
    path = Path(path)
    if path.exists():
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data, encoding='utf-8')
    os.chmod(path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)


def check_separate(control, *others):
    control = Path(control).resolve()
    for other in others:
        other = Path(other).resolve()
        if control == other or other in control.parents or control in other.parents:
            raise ValueError('Control record must be outside the project and working copy')
    return control


def init_record(control, working_copy, record):
    control = check_separate(control, working_copy)
    if control.exists():
        raise FileExistsError('Control folder already exists: refusing overwrite')
    control.mkdir(parents=True)
    record = {**record, 'working_copy': str(Path(working_copy).resolve()),
              'record_protection': PROTECTION, 'history': [
                  {'time': _now(), 'event': 'CONTROL_RECORD_CREATED'}]}
    write_protected(control / RECORD_NAME, json.dumps(record, indent=2, sort_keys=True) + '\n')
    return control


def load_record(control, working_copy):
    control = Path(control).resolve()
    path = control / RECORD_NAME
    if not path.is_file():
        raise ValueError('Control record missing: cannot trust approval state')
    record = json.loads(path.read_text(encoding='utf-8'))
    if record.get('working_copy') != str(Path(working_copy).resolve()):
        raise ValueError('Control record belongs to a different working copy')
    return record


def save_record(control, record, event, **details):
    record.setdefault('history', []).append({'time': _now(), 'event': event, **details})
    write_protected(Path(control) / RECORD_NAME,
                    json.dumps(record, indent=2, sort_keys=True) + '\n')


def store_approved_copy(control, text):
    write_protected(Path(control) / APPROVED_COPY_NAME, text)


def approval_payload(working_copy, digest):
    return {'type': 'BRIEF_APPROVAL', 'working_copy': str(Path(working_copy).resolve()),
            'approved_brief_sha256': digest}


def verify_brief(working_copy, control=None, stage='architect', *, public_key=None, log=True):
    """Re-check the approved brief before a stage starts. Raises ValueError -> BLOCKED.

    With ``public_key``, the owner's approval signature must also be valid.
    """
    if stage not in STAGES:
        raise ValueError(f'Unknown stage {stage!r}; expected one of {", ".join(STAGES)}')
    working = Path(working_copy).resolve()
    control = Path(control).resolve() if control else default_control_dir(working)
    record = load_record(control, working)
    expected = record.get('approved_brief_sha256')
    if record.get('brief_owner_approval') != 'OWNER_ACTION_RECORDED_NOT_AUTHENTICATED' or not expected:
        raise ValueError('No recorded owner approval of the brief in the control record')
    working_brief = working / WORKING_APPROVED_NAME
    control_brief = control / APPROVED_COPY_NAME
    problems = []
    if public_key is not None:
        signed = {**approval_payload(working, expected),
                  'signature': record.get('approval_signature')}
        if not signing.verify(signed, public_key):
            problems.append('owner approval signature missing or invalid')
    if not control_brief.is_file() or sha256_file(control_brief) != expected:
        problems.append('control copy of approved brief missing or changed')
    if not working_brief.is_file() or sha256_file(working_brief) != expected:
        problems.append('working-copy approved brief missing or changed since approval')
    result = 'BLOCKED' if problems else 'OK'
    if log:
        save_record(control, record, 'BRIEF_CHECK', stage=stage, result=result,
                    problems=problems)
    if problems:
        raise ValueError('Approved brief check failed: ' + '; '.join(problems))
    return {'status': 'OK', 'stage': stage, 'approved_brief_sha256': expected,
            'control_record': str(control / RECORD_NAME)}
