"""Minimal drop-in entry point. Prepares a handoff, never launches agents."""
import argparse
import json
from pathlib import Path

from activate_personal import prepare
from control_record import STAGES, default_control_dir, verify_brief
from project_discovery import create_draft, approve_brief
from signing import load_private_key, load_public_key

UNSPECIFIED_GOAL = 'UNSPECIFIED_PENDING_OWNER_INPUT'


def start(project, goal=None, *, create=False, output=None, control=None):
    root = Path(project).resolve()
    target = Path(output).resolve() if output else root.with_name(root.name + '_uat_working')
    control = Path(control).resolve() if control else default_control_dir(target)
    goal = goal.strip() if isinstance(goal, str) and goal.strip() else UNSPECIFIED_GOAL
    result = prepare(root, target, goal, create=create, control=control)
    if create:
        result['brief_discovery'] = create_draft(target, goal, control)
    result['next_step'] = (
        'Review and complete UAT_PROJECT_BRIEF_DRAFT.md; record owner approval before the Architect may start.'
        if create else 'Check the preview, then rerun with --create to prepare a separate working copy.'
    )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='Universal AI Team drop-in supervised activation')
    parser.add_argument('--project', default='.', help='Project directory (default: current directory)')
    parser.add_argument('--goal', help='Optional project idea; the Brief Builder asks the owner if absent')
    parser.add_argument('--output', help='Separate output directory (default: sibling <project>_uat_working)')
    parser.add_argument('--create', action='store_true', help='Create the working copy after preview')
    parser.add_argument('--approve-brief', metavar='SHA256',
                        help='Record explicit owner approval for this exact completed draft (not identity authentication)')
    parser.add_argument('--working-copy', help='Existing working copy to approve or verify')
    parser.add_argument('--control', help='Control record folder (default: sibling <working copy>_control)')
    parser.add_argument('--verify-brief', action='store_true',
                        help='Re-check the approved brief against the control record before a stage')
    parser.add_argument('--signing-key', help='Owner PRIVATE key: signs the brief approval (with --approve-brief)')
    parser.add_argument('--public-key', help='Owner PUBLIC key: approval signature must verify (with --verify-brief)')
    parser.add_argument('--stage', choices=STAGES, default='architect',
                        help='Stage about to start (used with --verify-brief)')
    args = parser.parse_args(argv)
    try:
        if (args.approve_brief or args.verify_brief) and not args.working_copy:
            raise ValueError('--working-copy is required for --approve-brief and --verify-brief')
        if args.approve_brief and args.verify_brief:
            raise ValueError('Use --approve-brief or --verify-brief, not both')
        if args.approve_brief:
            key = (load_private_key(args.signing_key, not_inside=[args.working_copy])
                   if args.signing_key else None)
            result = approve_brief(args.working_copy, args.approve_brief, args.control,
                                   private_key=key)
        elif args.verify_brief:
            key = (load_public_key(args.public_key, not_inside=[args.working_copy])
                   if args.public_key else None)
            result = verify_brief(args.working_copy, args.control, args.stage, public_key=key)
        else:
            result = start(args.project, args.goal, create=args.create, output=args.output,
                           control=args.control)
        print(json.dumps(result, indent=2, sort_keys=True))
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({'status': 'BLOCKED', 'reason': str(exc)}, indent=2))
        raise SystemExit(2)


if __name__ == '__main__':
    main()
