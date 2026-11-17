"""Minimal drop-in entry point. Prepares a handoff, never launches agents."""
import argparse
import json
from pathlib import Path

from activate_personal import prepare
from project_discovery import create_draft, approve_brief

UNSPECIFIED_GOAL = 'UNSPECIFIED_PENDING_OWNER_INPUT'


def start(project, goal=None, *, create=False, output=None):
    root = Path(project).resolve()
    target = Path(output).resolve() if output else root.with_name(root.name + '_uat_working')
    goal = goal.strip() if isinstance(goal, str) and goal.strip() else UNSPECIFIED_GOAL
    result = prepare(root, target, goal, create=create)
    if create:
        result['brief_discovery'] = create_draft(target, goal)
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
    parser.add_argument('--working-copy', help='Existing working copy to approve')
    args = parser.parse_args(argv)
    try:
        if args.approve_brief:
            if not args.working_copy:
                raise ValueError('--working-copy is required for --approve-brief')
            result = approve_brief(args.working_copy, args.approve_brief)
        else:
            result = start(args.project, args.goal, create=args.create, output=args.output)
        print(json.dumps(result, indent=2, sort_keys=True))
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({'status': 'BLOCKED', 'reason': str(exc)}, indent=2))
        raise SystemExit(2)


if __name__ == '__main__':
    main()
