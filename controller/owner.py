"""Owner approval commands.

Two ways to approve a gate (brief, team_plan, promotion, release):

* ``approve`` — on this machine, at an interactive terminal: owner key
  passphrase, then typing the first 8 characters of the exact SHA-256 shown.
* ``request`` -> ``sign`` -> ``submit`` — OFFLINE. ``request`` writes the exact
  approval to a file after checking every precondition. The owner carries it to
  a separate device that holds the owner key (for example a laptop that never
  runs agents), reviews it and runs ``sign`` there. ``submit`` stores the
  signature after re-checking the state and the pinned owner key. With this
  route the owner's private key never exists on the machine the agents use.

Either way, a signature proves someone held the owner key (and passphrase) and
deliberately approved this exact content. It does not prove which person did.
"""
import argparse
import getpass
import hashlib
import json
import sys
from pathlib import Path

import signing
from control_record import approval_payload, default_control_dir, load_record
from gates import OWNER_GATES, approve_gate, check_signer, load_trust, prepare_approval, store_approval
from project_discovery import approve_brief

GATES = ('brief',) + OWNER_GATES


def terminal_confirm(summary, sha, *, stdin=sys.stdin, ask=input):
    if not stdin.isatty():
        raise ValueError('Owner approval must be given at an interactive terminal')
    print(summary)
    return ask('Type the first 8 characters of the SHA-256 above to approve: ').strip() == sha[:8]


def _passphrase(passphrase):
    if passphrase is not None:
        return passphrase
    if not sys.stdin.isatty():
        raise ValueError('Owner approval must be given at an interactive terminal')
    return getpass.getpass('Owner key passphrase: ').encode('utf-8')


def unlock_owner_key(path, *, not_inside=(), passphrase=None):
    return signing.load_private_key(path, not_inside=not_inside, passphrase=_passphrase(passphrase),
                                    require_encrypted=True)


def _brief_payload(working_copy, trust, control):
    working = Path(working_copy).resolve()
    record = load_record(Path(control).resolve() if control else default_control_dir(working), working)
    if record.get('state') != 'AWAITING_OWNER_BRIEF_APPROVAL':
        raise ValueError('Brief is not awaiting approval')
    draft = working / 'UAT_PROJECT_BRIEF_DRAFT.md'
    if '[OWNER TO COMPLETE' in draft.read_text(encoding='utf-8'):
        raise ValueError('Complete all owner-input placeholders before approval')
    return approval_payload(working, hashlib.sha256(draft.read_bytes()).hexdigest())


def request(working_copy, gate, *, trust_config, control=None, tasks=None, candidate=None):
    """Return the exact payload the owner must sign (all preconditions checked)."""
    trust = load_trust(trust_config, working_copy)
    if gate == 'brief':
        payload = _brief_payload(working_copy, trust, control)
    else:
        payload, _ = prepare_approval(working_copy, gate, trust, control, tasks=tasks,
                                      candidate=candidate)
    return {'gate': gate, 'payload': payload, 'candidate': str(candidate) if candidate else None}


def sign_request(request_doc, *, signing_key, passphrase=None, confirm=terminal_confirm):
    """Run on the owner's separate device. Needs only the request and the owner key."""
    key = unlock_owner_key(signing_key, passphrase=passphrase)
    payload = request_doc['payload']
    sha = payload.get('subject_sha256') or payload.get('approved_brief_sha256')
    if not confirm(json.dumps(payload, indent=2), sha):
        raise ValueError('Owner did not confirm')
    return {**request_doc, 'signature': signing.attach(payload, key)['signature']}


def submit(working_copy, signed_doc, *, trust_config, control=None):
    trust = load_trust(trust_config, working_copy)
    gate, payload, signature = signed_doc['gate'], signed_doc['payload'], signed_doc['signature']
    if gate == 'brief':
        if payload != _brief_payload(working_copy, trust, control):
            raise ValueError('Signed approval does not match the current brief draft')
        if not signing.verify({**payload, 'signature': signature}, trust['owner']):
            raise ValueError('Approval is not signed by the pinned owner key')
        return approve_brief(working_copy, payload['approved_brief_sha256'], control,
                             approval_signature=signature)
    return store_approval(working_copy, gate, payload, signature, trust, control,
                          tasks=payload.get('tasks'), candidate=signed_doc.get('candidate'))


def approve_brief_as_owner(working_copy, *, signing_key, trust_config, control=None,
                           passphrase=None, confirm=terminal_confirm):
    doc = request(working_copy, 'brief', trust_config=trust_config, control=control)
    trust = load_trust(trust_config, working_copy)
    key = unlock_owner_key(signing_key, not_inside=[working_copy], passphrase=passphrase)
    check_signer(key, trust, 'owner')
    sha = doc['payload']['approved_brief_sha256']
    if not confirm(json.dumps(doc['payload'], indent=2), sha):
        raise ValueError('Owner did not confirm')
    return approve_brief(working_copy, sha, control, private_key=key)


def approve_as_owner(working_copy, gate, *, signing_key, trust_config, control=None, tasks=None,
                     candidate=None, passphrase=None, confirm=terminal_confirm):
    trust = load_trust(trust_config, working_copy)
    key = unlock_owner_key(signing_key, not_inside=[working_copy], passphrase=passphrase)
    check_signer(key, trust, 'owner')
    return approve_gate(working_copy, gate, private_key=key, trust=trust, confirm=confirm,
                        control=control, tasks=tasks, candidate=candidate)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Universal AI Team owner approvals')
    sub = parser.add_subparsers(dest='mode', required=True)
    for name in ('approve', 'request'):
        p = sub.add_parser(name)
        p.add_argument('gate', choices=GATES)
        p.add_argument('--working-copy', required=True)
        p.add_argument('--trust-config', required=True)
        p.add_argument('--control')
        p.add_argument('--tasks', help='Comma-separated task ids (team_plan only)')
        p.add_argument('--candidate', help='Exact candidate file (promotion and release)')
    sub.choices['approve'].add_argument('--signing-key', required=True)
    sub.choices['request'].add_argument('--out', required=True)
    sig = sub.add_parser('sign', help='On the owner\'s separate device')
    sig.add_argument('request_file')
    sig.add_argument('--signing-key', required=True)
    sig.add_argument('--out', required=True)
    sbm = sub.add_parser('submit')
    sbm.add_argument('signed_file')
    sbm.add_argument('--working-copy', required=True)
    sbm.add_argument('--trust-config', required=True)
    sbm.add_argument('--control')
    args = parser.parse_args(argv)
    try:
        tasks = (getattr(args, 'tasks', None) or '').split(',') if getattr(args, 'tasks', None) else None
        if args.mode == 'approve' and args.gate == 'brief':
            result = approve_brief_as_owner(args.working_copy, signing_key=args.signing_key,
                                            trust_config=args.trust_config, control=args.control)
        elif args.mode == 'approve':
            result = approve_as_owner(args.working_copy, args.gate, signing_key=args.signing_key,
                                      trust_config=args.trust_config, control=args.control,
                                      tasks=tasks, candidate=args.candidate)
        elif args.mode == 'request':
            doc = request(args.working_copy, args.gate, trust_config=args.trust_config,
                          control=args.control, tasks=tasks, candidate=args.candidate)
            Path(args.out).write_text(json.dumps(doc, indent=2) + '\n', encoding='utf-8')
            result = {'status': 'REQUEST_WRITTEN', 'file': args.out,
                      'next_step': 'Review and sign it on the owner device, then submit.'}
        elif args.mode == 'sign':
            doc = sign_request(json.loads(Path(args.request_file).read_text(encoding='utf-8')),
                               signing_key=args.signing_key)
            Path(args.out).write_text(json.dumps(doc, indent=2) + '\n', encoding='utf-8')
            result = {'status': 'SIGNED', 'file': args.out}
        else:
            result = submit(args.working_copy,
                            json.loads(Path(args.signed_file).read_text(encoding='utf-8')),
                            trust_config=args.trust_config, control=args.control)
    except (OSError, ValueError, KeyError) as exc:
        result = {'status': 'BLOCKED', 'reason': str(exc)}
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result.get('status') != 'BLOCKED' else 2)


if __name__ == '__main__':
    main()
