"""Stage dispatcher: the only supported way to start a stage.

Before anything launches, the dispatcher:

1. loads the host-controlled trust config and checks the pinned owner and
   harness key fingerprints (a substituted public key is rejected);
2. probes the agent boundary through the agents' own launcher: if agents could
   read a private key or write the control folder, trust config, public keys,
   evidence folders or dispatcher code, it refuses (BLOCKED);
3. runs every owner gate and checkpoint for the stage (see gates.py).

Three entry points:

* ``run``    — trusted side: launch a stage command through the launcher
  (separate OS user or container) after all checks pass.
* ``ticket`` — trusted side, for hosts that start sub-agents themselves: run
  all checks, count the submission, and issue a short-lived launch ticket
  signed with the harness key and bound to the exact prompt text, stage,
  task, submission number and candidate hash. The ticket line goes first in
  the sub-agent prompt.
* ``hook``   — runs as the agents' user (for example a Claude Code PreToolUse
  hook). Every sub-agent launch needs a valid ticket; the stage comes from the
  signed ticket, never from the agent. Any change to the prompt, an expired or
  forged ticket, or a failed gate exits 2, which blocks the launch.

Residual: the hook can't record that a ticket was used, so within its
lifetime the identical prompt could be launched again; it cannot be relabelled
or reused for another stage, task or submission. And if the host lets agents
start work without the hook, nothing here can stop it: disable the host's own
sub-agent tool for agents, or launch only with ``run``.
"""
import argparse
import base64
import hashlib
import json
import secrets
import subprocess
import sys
from pathlib import Path

from datetime import datetime, timedelta, timezone

import signing
from control_record import STAGES, default_control_dir, sha256_file
from gates import AUTHOR_STAGES, authorize, check_boundary, check_signer, load_trust, note_launch

SUBAGENT_TOOLS = ('Task', 'Agent')
NAMED_STAGES = tuple(s for s in STAGES if s != 'subagent_launch')
TICKET_PREFIX = 'UAT-TICKET: '


def _prepare(working_copy, trust_config, control, launcher):
    working = Path(working_copy).resolve()
    control = Path(control).resolve() if control else default_control_dir(working)
    trust = load_trust(trust_config, working)
    check_boundary(trust, control, launcher)
    return working, control, trust


def run_stage(working_copy, stage, command, *, trust_config, control=None, launcher=(),
              task_id=None, candidate=None, timeout=None):
    if not command:
        raise ValueError('No stage command given')
    try:
        working, control, trust = _prepare(working_copy, trust_config, control, launcher)
        authorize(stage, working, trust, control, task_id=task_id, candidate=candidate)
    except ValueError as exc:
        return {'status': 'BLOCKED', 'stage': stage, 'launched': False, 'reason': str(exc)}
    note_launch(working, control, stage, task_id)
    argv = [*launcher, *command]
    proc = subprocess.run(argv, cwd=working, timeout=timeout)
    return {'status': 'LAUNCHED', 'stage': stage, 'task_id': task_id, 'launched': True,
            'argv': argv, 'returncode': proc.returncode}


def _prompt_sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def issue_ticket(working_copy, stage, prompt, *, trust_config, harness_key, control=None,
                 launcher=(), task_id=None, candidate=None, ttl_minutes=30):
    """Trusted side: check everything, count the submission, return the ticketed prompt."""
    working, control, trust = _prepare(working_copy, trust_config, control, launcher)
    check_signer(harness_key, trust, 'harness')
    authorize(stage, working, trust, control, task_id=task_id, candidate=candidate)
    submission = note_launch(working, control, stage, task_id)
    expires = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
    payload = {'type': 'LAUNCH_TICKET', 'working_copy': str(working), 'stage': stage,
               'task_id': task_id, 'submission': submission,
               'candidate': str(Path(candidate).resolve()) if candidate else None,
               'candidate_sha256': sha256_file(candidate) if candidate else None,
               'prompt_sha256': _prompt_sha(prompt), 'expires': expires.isoformat(timespec='seconds'),
               'nonce': secrets.token_hex(8)}
    ticket = base64.b64encode(json.dumps(signing.attach(payload, harness_key),
                                         sort_keys=True).encode('utf-8')).decode('ascii')
    return TICKET_PREFIX + ticket + '\n' + prompt


def read_ticket(full_prompt, trust, working):
    first, _, body = (full_prompt or '').partition('\n')
    if not first.startswith(TICKET_PREFIX):
        raise ValueError('Sub-agent prompt has no UAT launch ticket')
    try:
        ticket = json.loads(base64.b64decode(first[len(TICKET_PREFIX):].strip(), validate=True))
    except ValueError:
        raise ValueError('Launch ticket unreadable')
    if not signing.verify(ticket, trust['harness']) or ticket.get('type') != 'LAUNCH_TICKET':
        raise ValueError('Launch ticket signature invalid')
    if ticket.get('working_copy') != str(working):
        raise ValueError('Launch ticket is for a different working copy')
    if datetime.fromisoformat(ticket['expires']) < datetime.now(timezone.utc):
        raise ValueError('Launch ticket expired')
    if ticket.get('prompt_sha256') != _prompt_sha(body):
        raise ValueError('Prompt was changed after the ticket was issued')
    return ticket


def hook(stdin_text, working_copy, trust_config, control=None, probe_launcher=()):
    """Return (exit_code, message). Exit 2 blocks the host's launch."""
    try:
        event = json.loads(stdin_text or '{}')
    except ValueError:
        return 2, 'BLOCKED: hook input unreadable'
    if event.get('tool_name') not in SUBAGENT_TOOLS:
        return 0, ''
    try:
        working, control, trust = _prepare(working_copy, trust_config, control, probe_launcher)
        ticket = read_ticket((event.get('tool_input') or {}).get('prompt', ''), trust, working)
        candidate = ticket.get('candidate')
        if candidate and (not Path(candidate).is_file()
                          or sha256_file(candidate) != ticket.get('candidate_sha256')):
            raise ValueError('Ticketed candidate changed or missing')
        authorize(ticket['stage'], working, trust, control, task_id=ticket.get('task_id'),
                  candidate=candidate, log=False,
                  ticketed_submission=ticket['submission'] if ticket['stage'] in AUTHOR_STAGES else None)
    except (ValueError, OSError, KeyError) as exc:
        return 2, f'BLOCKED by Universal AI Team dispatcher: {exc}'
    return 0, ''


def main(argv=None):
    parser = argparse.ArgumentParser(description='Universal AI Team stage dispatcher')
    sub = parser.add_subparsers(dest='mode', required=True)
    for name in ('run', 'hook', 'ticket'):
        p = sub.add_parser(name)
        p.add_argument('--working-copy', required=True)
        p.add_argument('--trust-config', required=True,
                       help='Host-controlled trust config with pinned key fingerprints')
        p.add_argument('--control')
    for name in ('run', 'ticket'):
        p = sub.choices[name]
        p.add_argument('--stage', required=True, choices=NAMED_STAGES)
        p.add_argument('--task')
        p.add_argument('--candidate')
        p.add_argument('--launcher', default='[]',
                       help='JSON list prefix that puts agents inside their boundary')
    sub.choices['run'].add_argument('command', nargs=argparse.REMAINDER,
                                    help='-- then the stage command')
    tick = sub.choices['ticket']
    tick.add_argument('--prompt-file', required=True)
    tick.add_argument('--signing-key', required=True, help='Harness private key')
    tick.add_argument('--ttl-minutes', type=int, default=30)
    args = parser.parse_args(argv)

    if args.mode == 'ticket':
        try:
            key = signing.load_private_key(args.signing_key, not_inside=[args.working_copy])
            print(issue_ticket(args.working_copy, args.stage,
                               Path(args.prompt_file).read_text(encoding='utf-8'),
                               trust_config=args.trust_config, harness_key=key, control=args.control,
                               launcher=json.loads(args.launcher), task_id=args.task,
                               candidate=args.candidate, ttl_minutes=args.ttl_minutes), end='')
        except (OSError, ValueError) as exc:
            print(json.dumps({'status': 'BLOCKED', 'reason': str(exc)}), file=sys.stderr)
            raise SystemExit(2)
        return

    if args.mode == 'hook':
        code, message = hook(sys.stdin.read(), args.working_copy, args.trust_config, args.control)
        if message:
            print(message, file=sys.stderr)
        raise SystemExit(code)

    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    try:
        launcher = json.loads(args.launcher)
        if not isinstance(launcher, list) or not all(isinstance(x, str) for x in launcher):
            raise ValueError('--launcher must be a JSON list of strings')
        result = run_stage(args.working_copy, args.stage, command, trust_config=args.trust_config,
                           control=args.control, launcher=launcher, task_id=args.task,
                           candidate=args.candidate)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        result = {'status': 'BLOCKED', 'launched': False, 'reason': str(exc)}
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['status'] == 'LAUNCHED' else 2)


if __name__ == '__main__':
    main()
