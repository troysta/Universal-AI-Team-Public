"""Owner approval gates, critic verdicts, trust configuration and boundary checks.

Every stage launch goes through ``authorize``. It enforces, in order:

* brief approved and unchanged (owner-signed);
* every stored owner approval and critic verdict carries a valid signature
  from the pinned key for its role (any tampered entry blocks everything);
* the stage's own gate:

  ==================  ===========================================================
  architect           brief approved; team plan not yet approved; fewer than
                      three failed plan reviews (third = escalated to owner);
                      previous plan submission reviewed
  architect_critic    a plan submission is awaiting review
  specialist          team plan approved by the owner, unchanged; task in the
                      approved plan; not already accepted; fewer than three
                      failed reviews (third = escalated to owner); previous
                      submission reviewed
  specialist_critic   a submission for the task is awaiting review
  final_critic        every approved task has an accepted (PASS) verdict
  promotion_proposal  Final Critic PASS for this exact candidate
  promotion           + owner promotion approval for this exact candidate
  release             + separate owner release approval for this exact candidate
  ==================  ===========================================================

Critic verdicts are never typed in: ``record_verdict`` takes a harness-signed
evidence record, requires it to assess as EVIDENCED (critic isolation), and
uses the critic's own verdict line from the recorded output, bound to the
exact artifact hash reviewed. No evidence, no verdict.

Keys: the OWNER key signs approvals; a different HARNESS key signs critic
evidence, verdicts and launch tickets. Both public keys are pinned by fingerprint in a
host-controlled trust config, so a substituted key file is rejected.

``check_boundary`` probes, from inside the agents' own launcher, that agents
cannot read the private keys or write the control folder, trust config,
public keys, evidence folder or dispatcher code. Exposure = BLOCKED.
"""
import json
import subprocess
import sys
from pathlib import Path

import signing
from control_record import (STAGES, default_control_dir, load_record, save_record, sha256_file,
                            verify_brief, write_protected)
from quality_bar import QUALITY_BAR_NAME, load_quality_bar, validate_gate_results

MAX_SUBMISSIONS = 3
OWNER_GATES = ('team_plan', 'promotion', 'release')
VERDICT_STAGES = ('architect_critic', 'specialist_critic', 'final_critic')
VERDICTS = ('PASS', 'FAIL', 'BLOCKED')
PLAN_NAME = 'UAT_TEAM_PLAN.md'
CONTROLLER_DIR = Path(__file__).resolve().parent


def _inside(path, folder):
    path, folder = Path(path).resolve(), Path(folder).resolve()
    return path == folder or folder in path.parents


# ---------------------------------------------------------------- trust config

def load_trust(config_path, working_copy):
    """Load the host-controlled trust config and check pinned key fingerprints."""
    config_path = Path(config_path).resolve()
    working = Path(working_copy).resolve()
    if _inside(config_path, working):
        raise ValueError('Trust config must be outside the working copy')
    if not config_path.is_file():
        raise ValueError('Trust config missing')
    config = json.loads(config_path.read_text(encoding='utf-8'))
    trust = {'config_path': config_path, 'config': config, 'public_paths': {}}
    for role in ('owner', 'harness'):
        path = Path(config.get(f'{role}_public_key', '')).resolve()
        pinned = config.get(f'{role}_fingerprint')
        if not pinned:
            raise ValueError(f'No pinned {role} fingerprint in trust config')
        key = signing.load_public_key(path, not_inside=[working])
        if signing.fingerprint(key) != pinned:
            raise ValueError(f'{role} public key does not match the pinned fingerprint')
        trust[role] = key
        trust['public_paths'][role] = path
    if config['owner_fingerprint'] == config['harness_fingerprint']:
        raise ValueError('Owner approvals and harness evidence must use different keys')
    return trust


def check_signer(private_key, trust, role):
    if signing.fingerprint(private_key.public_key()) != trust['config'][f'{role}_fingerprint']:
        raise ValueError(f'This private key is not the pinned {role} key')


# ---------------------------------------------------------------- boundary probe

PROBE = r'''
import json, os, sys
results = {}
for kind, path in json.loads(sys.argv[1]):
    exposed = False
    try:
        if kind == "read":
            with open(path, "rb") as handle:
                handle.read(1)
            exposed = True
        elif os.path.isdir(path):
            probe = os.path.join(path, ".uat_boundary_probe_%d" % os.getpid())
            with open(probe, "x"):
                pass
            os.remove(probe)
            exposed = True
        else:
            with open(path, "ab"):
                pass
            exposed = True
    except Exception:
        exposed = False
    results[kind + ":" + path] = "EXPOSED" if exposed else "PROTECTED"
print("UAT_PROBE " + json.dumps(results))
'''


def boundary_targets(trust, control):
    config = trust['config']
    writes = [Path(control), trust['config_path'], *trust['public_paths'].values(), CONTROLLER_DIR]
    writes += [Path(p) for p in config.get('evidence_dirs', [])]
    writes += [Path(p) for p in config.get('protected_paths', [])]
    reads = [Path(p) for p in config.get('private_key_paths', [])]
    if not reads:
        raise ValueError('Trust config must list private_key_paths so the boundary can be probed')
    return [('write', str(p.resolve())) for p in writes] + [('read', str(p.resolve())) for p in reads]


def check_boundary(trust, control, launcher=(), python=None, timeout=60):
    targets = boundary_targets(trust, control)
    argv = [*launcher, python or sys.executable, '-c', PROBE, json.dumps(targets)]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    line = next((l for l in proc.stdout.splitlines() if l.startswith('UAT_PROBE ')), None)
    if line is None:
        raise ValueError(f'Boundary probe gave no result (exit {proc.returncode})')
    exposed = sorted(k for k, v in json.loads(line[len('UAT_PROBE '):]).items() if v != 'PROTECTED')
    if exposed:
        raise ValueError('Agent boundary missing; agents can reach: ' + ', '.join(exposed))
    return {'boundary': 'PROTECTED', 'targets': len(targets)}


# ---------------------------------------------------------------- signed entries

ARCHITECT_LOOP = '__architect__'
AUTHOR_STAGES = {'architect': 'architect_critic', 'specialist': 'specialist_critic'}
REVIEW_STAGES = {v: k for k, v in AUTHOR_STAGES.items()}


def _payload(kind, working, **fields):
    return {'type': kind, 'working_copy': str(Path(working).resolve()), **fields}


def _signed_entries(record, trust, working):
    """Verify every stored approval and verdict; any bad entry raises."""
    approvals = {}
    for gate, entry in (record.get('approvals') or {}).items():
        signed = {**entry.get('payload', {}), 'signature': entry.get('signature')}
        if (not signing.verify(signed, trust['owner']) or entry['payload'].get('gate') != gate
                or entry['payload'].get('working_copy') != str(working)):
            raise ValueError(f'Owner approval for {gate} has an invalid signature')
        approvals[gate] = entry['payload']
    verdicts = []
    for entry in record.get('verdicts') or []:
        signed = {**entry.get('payload', {}), 'signature': entry.get('signature')}
        if (not signing.verify(signed, trust['harness'])
                or entry['payload'].get('working_copy') != str(working)):
            raise ValueError('A critic verdict has an invalid signature')
        verdicts.append(entry['payload'])
    return approvals, verdicts


def _loop_key(stage, task_id):
    return ARCHITECT_LOOP if stage in ('architect', 'architect_critic') else task_id


def _loop_status(record, verdicts, stage, task_id):
    """Every author attempt is accounted for by a review or a recorded launch failure.

    Technical launch failures consume one of the three attempts; they are NOT
    critic verdicts. This avoids a stuck pending submission without making
    unlimited unsuccessful launches a way around the three-attempt limit.
    """
    review_stage = AUTHOR_STAGES.get(stage, stage)
    key = _loop_key(stage, task_id)
    loop = [v for v in verdicts if v['stage'] == review_stage
            and (review_stage == 'architect_critic' or v['task_id'] == key)]
    failed_launches = (record.get('tasks') or {}).get(key, {}).get('launch_failures', [])
    return {'launched': (record.get('tasks') or {}).get(key, {}).get('submissions', 0),
            'reviewed': len(loop) + len(failed_launches),
            'fails': sum(v['verdict'] != 'PASS' for v in loop) + len(failed_launches),
            'accepted': any(v['verdict'] == 'PASS' for v in loop)}


def _final_pass(verdicts, candidate_sha):
    return any(v['stage'] == 'final_critic' and v['verdict'] == 'PASS'
               and v['artifact_sha256'] == candidate_sha for v in verdicts)


def _context(working_copy, control):
    working = Path(working_copy).resolve()
    control = Path(control).resolve() if control else default_control_dir(working)
    return working, control, load_record(control, working)


# ---------------------------------------------------------------- policy

def authorize(stage, working_copy, trust, control=None, *, task_id=None, candidate=None, log=True,
              ticketed_submission=None):
    """Raise ValueError (BLOCKED) unless every gate for ``stage`` is satisfied.

    ``ticketed_submission``: for a launch whose submission was already counted
    when its ticket was issued, the submission number on that ticket.
    """
    if stage not in STAGES or stage == 'subagent_launch':
        raise ValueError(f'Stage must be one of the named stages, not {stage!r}')
    working, control, _ = _context(working_copy, control)
    verify_brief(working, control, stage, public_key=trust['owner'], log=log)
    record = load_record(control, working)
    approvals, verdicts = _signed_entries(record, trust, working)
    plan = working / PLAN_NAME

    def need_plan_approval():
        approval = approvals.get('team_plan')
        if not approval:
            raise ValueError('Owner has not approved the reviewed team plan')
        if not plan.is_file() or sha256_file(plan) != approval['subject_sha256']:
            raise ValueError('Team plan changed since the owner approved it')
        _, bar_sha = load_quality_bar(working, expected_tasks=approval['tasks'])
        if bar_sha != approval.get('quality_bar_sha256'):
            raise ValueError('Quality Bar changed since owner approval')
        protected = control / f'approved_quality_bar_{bar_sha[:12]}.json'
        if not protected.is_file() or sha256_file(protected) != bar_sha:
            raise ValueError('Protected Quality Bar copy missing or changed')
        return approval

    def need_task(approval):
        if not task_id:
            raise ValueError(f'{stage} needs a task id')
        if task_id not in approval['tasks']:
            raise ValueError(f'Task {task_id!r} is not in the owner-approved team plan')

    def need_candidate():
        if not candidate or not Path(candidate).is_file():
            raise ValueError(f'{stage} needs an existing candidate file')
        return sha256_file(candidate)

    def author_loop():
        status = _loop_status(record, verdicts, stage, task_id)
        name = 'team plan' if stage == 'architect' else f'task {task_id!r}'
        if status['accepted']:
            raise ValueError(f'The {name} is already accepted')
        if status['fails'] >= MAX_SUBMISSIONS:
            raise ValueError(f'The {name} failed review {MAX_SUBMISSIONS} times: stopped, escalate to owner')
        if ticketed_submission is None:
            if status['launched'] > status['reviewed']:
                raise ValueError(f'Previous submission for the {name} has not been reviewed yet')
        elif not (ticketed_submission == status['launched'] == status['reviewed'] + 1):
            raise ValueError('Ticket is not for the current, unreviewed submission')

    def review_loop():
        status = _loop_status(record, verdicts, stage, task_id)
        if status['launched'] <= status['reviewed']:
            raise ValueError('No submission is awaiting review')

    if stage == 'architect':
        if approvals.get('team_plan'):
            raise ValueError('Team plan already approved; the Architect loop is closed')
        author_loop()
    if stage == 'architect_critic':
        if not plan.is_file():
            raise ValueError('No team plan to review')
        load_quality_bar(working)
        review_loop()
    if stage == 'specialist':
        need_task(need_plan_approval())
        author_loop()
    if stage == 'specialist_critic':
        need_task(need_plan_approval())
        review_loop()
    if stage == 'final_critic':
        approval = need_plan_approval()
        open_tasks = [t for t in approval['tasks']
                      if not _loop_status(record, verdicts, 'specialist', t)['accepted']]
        if open_tasks:
            raise ValueError('Tasks without an accepted review: ' + ', '.join(open_tasks))
    if stage in ('promotion_proposal', 'promotion', 'release'):
        need_plan_approval()
        sha = need_candidate()
        if not _final_pass(verdicts, sha):
            raise ValueError('No accepted Final Critic review for this exact candidate')
        if stage in ('promotion', 'release'):
            promo = approvals.get('promotion')
            if not promo or promo['subject_sha256'] != sha:
                raise ValueError('Owner has not approved promotion of this exact candidate')
        if stage == 'release':
            release = approvals.get('release')
            if not release or release['subject_sha256'] != sha:
                raise ValueError('Owner has not separately approved release of this exact candidate')
    return {'status': 'AUTHORIZED', 'stage': stage, 'task_id': task_id}


def note_launch(working_copy, control, stage, task_id=None):
    """Count an author submission (trusted side only). Returns the submission number."""
    working, control, record = _context(working_copy, control)
    submission = None
    if stage in AUTHOR_STAGES:
        loop = record.setdefault('tasks', {}).setdefault(_loop_key(stage, task_id), {'submissions': 0})
        loop['submissions'] += 1
        submission = loop['submissions']
    save_record(control, record, 'STAGE_AUTHORIZED', stage=stage, task_id=task_id,
                submission=submission)
    return submission


def note_launch_failure(working_copy, control, stage, task_id=None, *, returncode=None, reason=None):
    """Record a failed execution, accounting for an author attempt without fake critic review."""
    working, control, record = _context(working_copy, control)
    submission = None
    escalated = False
    if stage in AUTHOR_STAGES:
        key = _loop_key(stage, task_id)
        loop = (record.get('tasks') or {}).get(key)
        if not loop or not loop.get('submissions'):
            raise ValueError('Cannot record failure for an unlaunched submission')
        submission = loop['submissions']
        failures = loop.setdefault('launch_failures', [])
        if submission in failures:
            raise ValueError('Launch failure already recorded for this submission')
        failures.append(submission)
        escalated = submission >= MAX_SUBMISSIONS
        if escalated:
            loop['state'] = 'ESCALATED_TO_OWNER'
    save_record(control, record, 'STAGE_LAUNCH_FAILED', stage=stage, task_id=task_id,
                submission=submission, returncode=returncode, reason=reason,
                escalated_to_owner=escalated)
    return {'submission': submission, 'escalated_to_owner': escalated}


# ---------------------------------------------------------------- owner approvals

def prepare_approval(working_copy, gate, trust, control=None, *, tasks=None, candidate=None):
    """Check a gate's preconditions and return (payload, subject_path) to be signed."""
    if gate not in OWNER_GATES:
        raise ValueError(f'Unknown gate {gate!r}')
    working, control, _ = _context(working_copy, control)
    verify_brief(working, control, 'architect', public_key=trust['owner'], log=False)
    record = load_record(control, working)
    approvals, verdicts = _signed_entries(record, trust, working)
    if gate in approvals:
        raise ValueError(f'{gate} is already approved; approvals are one-time')
    extra = {}
    if gate == 'team_plan':
        subject = working / PLAN_NAME
        if not subject.is_file():
            raise ValueError('No team plan file to approve')
        sha = sha256_file(subject)
        tasks = [t.strip() for t in (tasks or []) if t.strip()]
        if not tasks or len(set(tasks)) != len(tasks) or ARCHITECT_LOOP in tasks:
            raise ValueError('List the approved task ids (unique, non-empty)')
        _, bar_sha = load_quality_bar(working, expected_tasks=tasks)
        if not any(v['stage'] == 'architect_critic' and v['verdict'] == 'PASS'
                   and v['artifact_sha256'] == sha and v.get('quality_bar_sha256') == bar_sha
                   for v in verdicts):
            raise ValueError('Team plan and Quality Bar have no accepted independent critic review for this version')
        extra['tasks'] = tasks
        extra['quality_bar_sha256'] = bar_sha
    else:
        if not candidate or not Path(candidate).is_file():
            raise ValueError(f'{gate} needs the exact candidate file')
        subject = Path(candidate).resolve()
        sha = sha256_file(subject)
        if not _final_pass(verdicts, sha):
            raise ValueError('No accepted Final Critic review for this exact candidate')
        if gate == 'release':
            promo = approvals.get('promotion')
            if not promo or promo['subject_sha256'] != sha:
                raise ValueError('Release needs a prior, separate promotion approval of this candidate')
    return _payload('OWNER_APPROVAL', working, gate=gate, subject_sha256=sha, **extra), subject


def store_approval(working_copy, gate, payload, signature, trust, control=None, *,
                   tasks=None, candidate=None):
    """Store an owner signature made here or on a separate device, after re-checking."""
    expected, subject = prepare_approval(working_copy, gate, trust, control,
                                         tasks=tasks if tasks is not None else payload.get('tasks'),
                                         candidate=candidate)
    if payload != expected:
        raise ValueError('Signed approval does not match the current state (file or plan changed)')
    if not signing.verify({**payload, 'signature': signature}, trust['owner']):
        raise ValueError('Approval is not signed by the pinned owner key')
    working, control, record = _context(working_copy, control)
    record.setdefault('approvals', {})[gate] = {'payload': payload, 'signature': signature}
    sha = payload['subject_sha256']
    write_protected(control / f'approved_{gate}_{sha[:12]}{subject.suffix}', subject.read_bytes())
    if gate == 'team_plan':
        bar_path = working / QUALITY_BAR_NAME
        write_protected(control / f'approved_quality_bar_{payload["quality_bar_sha256"][:12]}.json',
                        bar_path.read_bytes())
    save_record(control, record, 'OWNER_GATE_APPROVED', gate=gate, sha256=sha)
    return {'status': 'APPROVED', 'gate': gate, 'sha256': sha, 'tasks': payload.get('tasks'),
            'identity_verification': 'OWNER_KEY_HOLDER_NOT_PERSONAL_IDENTITY'}


def approve_gate(working_copy, gate, *, private_key, trust, confirm, control=None,
                 tasks=None, candidate=None):
    """Owner approval on this machine. ``confirm(summary, sha)`` must return True."""
    check_signer(private_key, trust, 'owner')
    payload, _ = prepare_approval(working_copy, gate, trust, control, tasks=tasks, candidate=candidate)
    if not confirm(json.dumps(payload, indent=2), payload['subject_sha256']):
        raise ValueError('Owner did not confirm')
    signature = signing.attach(payload, private_key)['signature']
    return store_approval(working_copy, gate, payload, signature, trust, control,
                          tasks=tasks, candidate=candidate)


# ---------------------------------------------------------------- critic verdicts

def record_verdict(working_copy, evidence_path, critic_index, *, private_key, trust, control=None):
    """Record a critic verdict, only from EVIDENCED, harness-signed isolation evidence.

    The verdict, stage, task and artifact all come from the signed evidence;
    nothing is typed in. Missing or unproven isolation = no verdict.
    """
    from critic_evidence import assess_isolation  # local import avoids a cycle
    check_signer(private_key, trust, 'harness')
    working, control, record = _context(working_copy, control)
    approvals, verdicts = _signed_entries(record, trust, working)
    evidence_path = Path(evidence_path).resolve()
    assessment = assess_isolation(evidence_path, working, trust['public_paths']['harness'])
    if assessment['isolation'] != 'EVIDENCED':
        raise ValueError('Critic isolation not evidenced: ' + '; '.join(assessment['problems']))
    evidence = json.loads(evidence_path.read_text(encoding='utf-8'))
    if evidence.get('working_copy') != str(working):
        raise ValueError('Evidence belongs to a different working copy')
    try:
        entry = evidence['critics'][critic_index]
    except (IndexError, TypeError):
        raise ValueError('No such critic in the evidence record')
    evidence_sha = sha256_file(evidence_path)
    if any(v.get('evidence_sha256') == evidence_sha and v.get('critic_index') == critic_index
           for v in verdicts):
        raise ValueError('This evidence has already been used for a verdict')
    review = entry.get('review') or {}
    stage, task_id = review.get('stage'), review.get('task_id')
    if stage not in VERDICT_STAGES:
        raise ValueError('Evidence entry is not a gated review (no stage)')
    if not review.get('artifact_unchanged_during_review'):
        raise ValueError('Artifact changed while the critic was reviewing it')
    if not Path(review['artifact']).is_file() or sha256_file(review['artifact']) != review['artifact_sha256']:
        raise ValueError('Artifact changed since the critic reviewed it')
    verdict = entry.get('critic_verdict') if entry.get('critic_verdict') in ('PASS', 'FAIL') else 'BLOCKED'
    submission = None
    if stage in VERDICT_STAGES:
        if stage == 'specialist_critic' and (not approvals.get('team_plan')
                                             or task_id not in approvals['team_plan']['tasks']):
            raise ValueError('Verdict task is not in the owner-approved team plan')
        if stage == 'architect_critic' and review['artifact'] != str(working / PLAN_NAME):
            raise ValueError('Architect critic must review the team plan file')
        if stage == 'architect_critic':
            _, bar_sha = load_quality_bar(working)
            if review.get('quality_bar_sha256') != bar_sha or not review.get('quality_bar_unchanged_during_review'):
                raise ValueError('Architect critic did not review this exact Quality Bar')
        if stage == 'specialist_critic':
            approval = approvals['team_plan']
            bar, bar_sha = load_quality_bar(working, expected_tasks=approval['tasks'])
            if (review.get('quality_bar_sha256') != bar_sha
                    or bar_sha != approval.get('quality_bar_sha256')
                    or not review.get('quality_bar_unchanged_during_review')):
                raise ValueError('Specialist critic did not review the approved Quality Bar')
            validate_gate_results(bar, task_id, entry.get('gate_results'), verdict)
        if stage == 'final_critic':
            approval = approvals.get('team_plan')
            if not approval:
                raise ValueError('Final Critic requires owner-approved team plan')
            bar, bar_sha = load_quality_bar(working, expected_tasks=approval['tasks'])
            if (bar_sha != approval.get('quality_bar_sha256')
                    or review.get('quality_bar_sha256') != bar_sha
                    or not review.get('quality_bar_unchanged_during_review')):
                raise ValueError('Final Critic did not review the approved Quality Bar')
            unaccepted = [t for t in approval['tasks']
                          if not _loop_status(record, verdicts, 'specialist', t)['accepted']]
            if unaccepted:
                raise ValueError('Final Critic cannot pass before task reviews: ' + ', '.join(unaccepted))
        if stage in REVIEW_STAGES:
            status = _loop_status(record, verdicts, stage, task_id)
            if status['launched'] <= status['reviewed']:
                raise ValueError('No submission is awaiting a verdict')
            submission = status['reviewed'] + 1
    payload = _payload('CRITIC_VERDICT', working, stage=stage, task_id=task_id,
                       artifact_sha256=review['artifact_sha256'], verdict=verdict,
                       quality_bar_sha256=review.get('quality_bar_sha256'),
                       gate_results=entry.get('gate_results') if stage == 'specialist_critic' else None,
                       submission=submission, trial_id=evidence.get('trial_id'),
                       evidence_sha256=evidence_sha, critic_index=critic_index)
    entry_out = {'payload': payload, 'signature': signing.attach(payload, private_key)['signature']}
    record.setdefault('verdicts', []).append(entry_out)
    escalated = False
    if stage in REVIEW_STAGES and verdict != 'PASS':
        escalated = _loop_status(record, verdicts + [payload], stage, task_id)['fails'] >= MAX_SUBMISSIONS
        if escalated:
            record['tasks'][_loop_key(stage, task_id)]['state'] = 'ESCALATED_TO_OWNER'
    save_record(control, record, 'CRITIC_VERDICT', stage=stage, task_id=task_id,
                verdict=verdict, escalated=escalated, evidence=str(evidence_path))
    return {'status': 'RECORDED', 'stage': stage, 'task_id': task_id, 'verdict': verdict,
            'submission': submission, 'escalated_to_owner': escalated}
