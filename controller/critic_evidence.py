"""Check a trial's critic-isolation evidence record against critics/README.md.

Only records produced by critic_harness.py and signed with the owner's private
key are accepted (checked with the PUBLIC key); values typed into a file do not pass. The result is EVIDENCED or
BLOCKED for that one trial, never VERIFIED.
"""
import json
from pathlib import Path

import signing


RESIDUAL_LEAK_PATHS = ('git_history', 'shared_temp_and_env', 'host_launch_wording',
                       'network_access', 'earlier_verdicts_in_files')
CRITIC_FIELDS = ('role', 'session_id', 'model', 'permissions', 'readable_paths',
                 'writable_paths', 'launch_prompt', 'launch_prompt_inspection',
                 'canary', 'forbidden_read')


def _inside(path, folder):
    path, folder = Path(path).resolve(), Path(folder).resolve()
    return path == folder or folder in path.parents


def _missing(mapping, keys, prefix):
    return [f'{prefix}{key} missing' for key in keys
            if key not in mapping or mapping[key] in (None, '', [], {})]


def assess_isolation(record_path, working_copy, public_key_path):
    record_path = Path(record_path).resolve()
    problems = []
    if _inside(record_path, working_copy):
        problems.append('evidence record is inside the working copy (not protected storage)')
    try:
        record = json.loads(record_path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        return {'isolation': 'BLOCKED', 'trial_id': None,
                'problems': problems + [f'evidence record unreadable: {exc}']}
    trial = record.get('trial_id')
    try:
        key = signing.load_public_key(public_key_path, not_inside=[working_copy])
        if not signing.verify(record, key):
            problems.append('evidence signature missing or invalid (not produced by the trusted harness)')
    except ValueError as exc:
        problems.append(f'cannot check evidence signature: {exc}')
    if record.get('produced_by') != 'critic_harness':
        problems.append('evidence record not produced by critic_harness')
    problems += _missing(record, ('trial_id', 'critics', 'residual_leak_paths'), '')

    for index, critic in enumerate(record.get('critics') or []):
        tag = f"critic[{index}] {critic.get('role', '?')}: "
        problems += _missing(critic, CRITIC_FIELDS, tag)
        for path in critic.get('writable_paths') or []:
            if _inside(record_path, path):
                problems.append(tag + 'could write to the evidence record location')
        inspection = critic.get('launch_prompt_inspection') or {}
        problems += _missing(inspection, ('inspected_by', 'time', 'result'), tag + 'prompt inspection ')
        if inspection and inspection.get('result') != 'PASS':
            problems.append(tag + 'launch prompt inspection did not pass')
        canary = critic.get('canary') or {}
        problems += _missing(canary, ('marker', 'placed_in', 'time', 'result'), tag + 'canary ')
        if canary and canary.get('result') != 'CLEAN':
            problems.append(tag + 'canary not clean')
        read = critic.get('forbidden_read') or {}
        problems += _missing(read, ('path', 'time', 'result'), tag + 'forbidden read ')
        if read and read.get('run_with_critic_permissions') is not True:
            problems.append(tag + 'forbidden read not run with the critic\'s own permissions and environment')
        if read and read.get('result') != 'DENIED':
            problems.append(tag + 'forbidden read was not denied')

    documented = record.get('residual_leak_paths') or {}
    for leak in RESIDUAL_LEAK_PATHS:
        if leak not in documented:
            problems.append(f'residual leak path {leak} not documented')

    status = 'BLOCKED' if problems else 'EVIDENCED'
    summary = (f'isolation: EVIDENCED (trial {trial}) — prompt logged and inspected, canary clean, '
               'file restriction tested under critic permissions. Residual leak paths documented, '
               'not excluded.' if status == 'EVIDENCED'
               else f'isolation: BLOCKED (trial {trial}) — {len(problems)} requirement(s) missing or failed')
    return {'isolation': status, 'trial_id': trial, 'summary': summary, 'problems': problems}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Assess a critic-isolation evidence record')
    parser.add_argument('record')
    parser.add_argument('--working-copy', required=True)
    parser.add_argument('--public-key', required=True)
    args = parser.parse_args()
    result = assess_isolation(args.record, args.working_copy, args.public_key)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['isolation'] == 'EVIDENCED' else 2)
