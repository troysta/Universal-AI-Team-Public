"""Optional, human-scored A/B comparison. Never changes candidate or baseline files.

The reviewer gets only the A/B packet. A randomly assigned version mapping is
kept in a separate operator-controlled directory until a score is recorded.
This is label blinding, NOT proof of reviewer independence or identity.
"""
import argparse
import hashlib
import json
import os
import secrets
import shutil
from datetime import datetime, timezone
from pathlib import Path

from control_record import write_protected
from quality_bar import load_quality_bar


RECORD_NAME = 'BLIND_COMPARISON_PRIVATE.json'
SCORE_NAME = 'HUMAN_SCORE.json'
SUPPORTED = {'.html', '.md', '.txt', '.json', '.pdf', '.png', '.jpg', '.jpeg', '.zip'}


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _inside(path, folder):
    path, folder = Path(path).resolve(), Path(folder).resolve()
    return path == folder or folder in path.parents


def _check_locations(working, packet, private):
    if (_inside(packet, working) or _inside(working, packet)
            or _inside(private, working) or _inside(working, private)
            or _inside(packet, private) or _inside(private, packet)):
        raise ValueError('Review packet and private mapping must be separate from the working copy and each other')


def _files(working, before, after):
    before, after = Path(before).resolve(), Path(after).resolve()
    if before == after or not before.is_file() or not after.is_file():
        raise ValueError('Choose two different, existing reviewable artifacts')
    if not _inside(before, working) or not _inside(after, working):
        raise ValueError('Comparison artifacts must be copies inside the working copy')
    if before.suffix.lower() not in SUPPORTED or after.suffix.lower() != before.suffix.lower():
        raise ValueError('Comparison requires matching, supported artifact file types')
    return before, after


def prepare(working_copy, before, after, task_id, packet_dir, private_dir):
    working = Path(working_copy).resolve()
    packet, private = Path(packet_dir).resolve(), Path(private_dir).resolve()
    _check_locations(working, packet, private)
    if packet.exists() or private.exists():
        raise FileExistsError('Comparison packet or private mapping already exists: refusing overwrite')
    earlier, later = _files(working, before, after)
    bar, bar_sha = load_quality_bar(working)
    if task_id not in bar['tasks']:
        raise ValueError('Comparison task is not present in the Quality Bar')
    hashes = {'before': _sha(earlier), 'after': _sha(later)}
    assignment = (('A', 'before', earlier), ('B', 'after', later)) if secrets.randbelow(2) else (
        ('A', 'after', later), ('B', 'before', earlier))
    packet.mkdir(parents=True, mode=0o755)
    private.mkdir(parents=True, mode=0o700)
    os.chmod(private, 0o700)
    extension = earlier.suffix.lower()
    labels = {}
    for label, version, source in assignment:
        dest = packet / f'{label}{extension}'
        with dest.open('xb') as out, source.open('rb') as inp:
            shutil.copyfileobj(inp, out)
        if _sha(dest) != hashes[version]:
            raise ValueError('Comparison copy failed integrity check')
        labels[label] = {'version': version, 'sha256': hashes[version]}
    rubric = packet / 'QUALITY_BAR.json'
    rubric.write_bytes((working / 'UAT_QUALITY_BAR.json').read_bytes())
    if _sha(rubric) != bar_sha:
        raise ValueError('Quality Bar changed during comparison packet creation')
    # Give the reviewer the actual quality-bar references, not a rubric whose
    # evidence is unavailable. The paths were constrained and hashed by
    # load_quality_bar; check each copy against that same approved digest.
    source_count = 0
    for ref in bar['tasks'][task_id]['references']:
        relative = Path(ref['path'])
        destination = packet / 'REFERENCES' / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(working / relative, destination)
        if _sha(destination) != ref['sha256']:
            raise ValueError(f'Reference changed while preparing review packet: {relative}')
        source_count += 1
    if _sha(earlier) != hashes['before'] or _sha(later) != hashes['after']:
        raise ValueError('Comparison source changed while preparing packet')
    gate_ids = [gate['id'] for gate in bar['tasks'][task_id]['gates']]
    (packet / 'REVIEW_INSTRUCTIONS.md').write_text(
        '# Blind A/B comparison\n\n'
        f'Task: {task_id}\n\n'
        f'Compare A{extension} and B{extension} against QUALITY_BAR.json. '
        'The labels do not indicate which version is newer.\n\n'
        f'Approved reference sources for this task are under REFERENCES/ ({source_count} files). '
        'They are copies; their original relative paths appear in QUALITY_BAR.json.\n\n'
        'Give the operator your preferred label (A, B or TIE), the gate IDs passed '
        'by each version, and a short explanation. Do not open the separate private '
        'mapping folder. File contents may still reveal their origin.\n', encoding='utf-8')
    record = {'version': 1, 'created': datetime.now(timezone.utc).isoformat(),
              'working_copy': str(working), 'packet_dir': str(packet),
              'task_id': task_id, 'quality_bar_sha256': bar_sha,
              'gate_ids': gate_ids, 'labels': labels,
              'sources': {'before': str(earlier), 'after': str(later)}}
    write_protected(private / RECORD_NAME, json.dumps(record, indent=2, sort_keys=True) + '\n')
    return {'status': 'PACKET_PREPARED', 'packet_dir': str(packet),
            'review_files': sorted(p.name for p in packet.iterdir()),
            'private_mapping': 'NOT_INCLUDED_IN_REVIEW_PACKET',
            'blindness': 'LABELS_RANDOMIZED_INDEPENDENCE_NOT_VERIFIED'}


def _record(packet_dir, private_dir):
    private = Path(private_dir).resolve()
    record = json.loads((private / RECORD_NAME).read_text(encoding='utf-8'))
    packet = Path(packet_dir).resolve()
    if record.get('packet_dir') != str(packet) or not packet.is_dir():
        raise ValueError('Comparison packet does not match private record')
    for label, info in record['labels'].items():
        found = list(packet.glob(f'{label}.*'))
        if len(found) != 1 or _sha(found[0]) != info['sha256']:
            raise ValueError(f'Comparison artifact {label} changed after packet preparation')
    if _sha(packet / 'QUALITY_BAR.json') != record['quality_bar_sha256']:
        raise ValueError('Comparison Quality Bar changed after preparation')
    bar = json.loads((packet / 'QUALITY_BAR.json').read_text(encoding='utf-8'))
    for ref in bar['tasks'][record['task_id']]['references']:
        reference = packet / 'REFERENCES' / ref['path']
        if (not reference.resolve().is_relative_to(packet / 'REFERENCES')
                or not reference.is_file() or _sha(reference) != ref['sha256']):
            raise ValueError(f'Comparison reference changed: {ref["path"]}')
    return record, private


def score(packet_dir, private_dir, choice, passed_a, passed_b, reason, reviewer='anonymous'):
    record, private = _record(packet_dir, private_dir)
    if (private / SCORE_NAME).exists():
        raise ValueError('Comparison already scored; refusing overwrite')
    if choice not in ('A', 'B', 'TIE') or not isinstance(reason, str) or not reason.strip():
        raise ValueError('Provide A, B or TIE and a meaningful explanation')
    allowed = set(record['gate_ids'])
    for label, passing in (('A', passed_a), ('B', passed_b)):
        if not isinstance(passing, list) or len(set(passing)) != len(passing) or not set(passing) <= allowed:
            raise ValueError(f'Invalid or duplicate passing gate IDs for {label}')
    result = {'choice': choice, 'passed_a': passed_a, 'passed_b': passed_b,
              'reason': reason, 'reviewer_declared': reviewer,
              'recorded': datetime.now(timezone.utc).isoformat(),
              'independence': 'NOT_VERIFIED_SELF_REPORTED_HUMAN'}
    write_protected(private / SCORE_NAME, json.dumps(result, indent=2, sort_keys=True) + '\n')
    return {'status': 'SCORED', 'choice': choice, 'passed_a': len(passed_a),
            'passed_b': len(passed_b), 'mapping_revealed': False}


def reveal(packet_dir, private_dir):
    record, private = _record(packet_dir, private_dir)
    score_path = private / SCORE_NAME
    if not score_path.is_file():
        raise ValueError('A human score must be recorded before revealing labels')
    result = json.loads(score_path.read_text(encoding='utf-8'))
    choice = result['choice']
    return {'status': 'REVEALED', 'comparison': record['task_id'],
            'assignments': {label: item['version'] for label, item in record['labels'].items()},
            'human_preference': result['choice'],
            'preferred_version': 'TIE' if choice == 'TIE' else record['labels'][choice]['version'],
            'gate_passes': {'A': result['passed_a'], 'B': result['passed_b']},
            'independence': result['independence']}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Optional blind A/B human comparison')
    sub = parser.add_subparsers(dest='action', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--working-copy', required=True)
    prep.add_argument('--before', required=True)
    prep.add_argument('--after', required=True)
    prep.add_argument('--task', required=True)
    for name in ('prepare', 'score', 'reveal'):
        p = prep if name == 'prepare' else sub.add_parser(name)
        p.add_argument('--packet-dir', required=True)
        p.add_argument('--private-dir', required=True)
        if name == 'score':
            p.add_argument('--choice', choices=('A', 'B', 'TIE'), required=True)
            p.add_argument('--passed-a', default='', help='Comma-separated passing gate IDs')
            p.add_argument('--passed-b', default='', help='Comma-separated passing gate IDs')
            p.add_argument('--reason', required=True)
            p.add_argument('--reviewer', default='anonymous')
    args = parser.parse_args(argv)
    try:
        if args.action == 'prepare':
            result = prepare(args.working_copy, args.before, args.after, args.task,
                             args.packet_dir, args.private_dir)
        elif args.action == 'score':
            result = score(args.packet_dir, args.private_dir, args.choice,
                           [s for s in args.passed_a.split(',') if s],
                           [s for s in args.passed_b.split(',') if s], args.reason, args.reviewer)
        else:
            result = reveal(args.packet_dir, args.private_dir)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        result = {'status': 'BLOCKED', 'reason': str(exc)}
    print(json.dumps(result, indent=2))
    raise SystemExit(2 if result['status'] == 'BLOCKED' else 0)


if __name__ == '__main__':
    main()
