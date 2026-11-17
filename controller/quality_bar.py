"""Task-specific, reviewable acceptance gates bound to the owner's plan approval.

This checks the *presence and integrity* of the rubric and its local references.
It does not decide whether a real deliverable satisfies a gate; the isolated
critic must supply gate-by-gate evidence for that, and the owner remains final.
"""
import json
import re
from pathlib import Path

from control_record import sha256_file


QUALITY_BAR_NAME = 'UAT_QUALITY_BAR.json'
GATES_PER_TASK = 5
_ID = re.compile(r'^[A-Za-z][A-Za-z0-9_-]{0,63}$')
_HEX_SHA256 = re.compile(r'^[0-9a-f]{64}$')


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Quality Bar has duplicate JSON key {key!r}')
        result[key] = value
    return result


def _required_string(obj, field, where):
    value = obj.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'Quality Bar {where} needs non-empty {field}')
    return value


def load_quality_bar(working_copy, expected_tasks=None):
    """Load and verify format and exact bytes of each referenced source.

    Reference paths must be relative paths within the working copy. Symlinks
    resolving outside it, directories, missing files and changed hashes block.
    """
    working = Path(working_copy).resolve()
    path = working / QUALITY_BAR_NAME
    if path.is_symlink() or not path.resolve().is_relative_to(working):
        raise ValueError('Quality Bar must be a regular file inside the working copy')
    if not path.is_file():
        raise ValueError(f'Missing mandatory Quality Bar: {QUALITY_BAR_NAME}')
    try:
        raw = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_unique_keys)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f'Invalid Quality Bar JSON: {exc}') from exc
    if not isinstance(raw, dict) or raw.get('schema_version') != 1:
        raise ValueError('Quality Bar schema_version must be 1')
    tasks = raw.get('tasks')
    if not isinstance(tasks, dict) or not tasks:
        raise ValueError('Quality Bar needs task entries')
    if expected_tasks is not None and set(tasks) != set(expected_tasks):
        raise ValueError('Quality Bar task ids differ from owner-approved team plan tasks')
    for task_id, task in tasks.items():
        if not isinstance(task_id, str) or not _ID.fullmatch(task_id):
            raise ValueError(f'Invalid Quality Bar task id: {task_id!r}')
        if not isinstance(task, dict):
            raise ValueError(f'Quality Bar task {task_id} must be an object')
        for field in ('goal', 'audience'):
            _required_string(task, field, task_id)
        refs = task.get('references')
        if not isinstance(refs, list) or not refs:
            raise ValueError(f'Quality Bar {task_id} needs referenced source files')
        seen_refs = set()
        for ref in refs:
            if not isinstance(ref, dict):
                raise ValueError(f'Quality Bar {task_id} has malformed reference')
            relative = Path(_required_string(ref, 'path', task_id))
            digest = _required_string(ref, 'sha256', task_id)
            if relative.is_absolute() or '..' in relative.parts or not _HEX_SHA256.fullmatch(digest):
                raise ValueError(f'Quality Bar {task_id} has unsafe reference or hash')
            resolved = (working / relative).resolve()
            if not resolved.is_relative_to(working) or not resolved.is_file():
                raise ValueError(f'Quality Bar {task_id} reference unavailable/outside working copy')
            if str(resolved) in seen_refs:
                raise ValueError(f'Quality Bar {task_id} has duplicate references')
            seen_refs.add(str(resolved))
            if sha256_file(resolved) != digest:
                raise ValueError(f'Quality Bar {task_id} source changed: {relative}')
        gates = task.get('gates')
        if not isinstance(gates, list) or len(gates) != GATES_PER_TASK:
            raise ValueError(f'Quality Bar {task_id} needs exactly {GATES_PER_TASK} pass/fail gates')
        seen_gate_ids = set()
        for gate in gates:
            if not isinstance(gate, dict):
                raise ValueError(f'Quality Bar {task_id} has malformed gate')
            gate_id = _required_string(gate, 'id', task_id)
            if not _ID.fullmatch(gate_id) or gate_id in seen_gate_ids:
                raise ValueError(f'Quality Bar {task_id} gate ids must be unique and valid')
            seen_gate_ids.add(gate_id)
            for field in ('requirement', 'pass_condition', 'test_method', 'evidence_required'):
                _required_string(gate, field, f'{task_id}/{gate_id}')
    return raw, sha256_file(path)


def validate_gate_results(quality_bar, task_id, gate_results, verdict):
    """Fail closed if a specialist critic omits gate outcomes or evidence."""
    gates = quality_bar['tasks'][task_id]['gates']
    required = {gate['id'] for gate in gates}
    if not isinstance(gate_results, dict) or set(gate_results) != required:
        raise ValueError('Critic gate results missing or do not match the approved Quality Bar')
    outcomes = []
    for gate_id, result in gate_results.items():
        if not isinstance(result, dict) or result.get('verdict') not in ('PASS', 'FAIL', 'BLOCKED'):
            raise ValueError(f'Critic gate {gate_id} needs PASS, FAIL or BLOCKED')
        if not isinstance(result.get('evidence'), str) or not result['evidence'].strip():
            raise ValueError(f'Critic gate {gate_id} is missing supporting evidence')
        outcomes.append(result['verdict'])
    all_pass = all(outcome == 'PASS' for outcome in outcomes)
    if verdict == 'PASS' and not all_pass:
        raise ValueError('Critic global PASS contradicts failed or blocked Quality Bar gates')
    if verdict == 'FAIL' and all_pass:
        raise ValueError('Critic global FAIL contradicts all-passing Quality Bar gates')
    return gate_results
