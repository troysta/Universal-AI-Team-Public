"""Safe, one-command entry point for trying Universal AI Team on a project.

No files in the original project are changed. This is *preparation*, not an
installer for native sub-agents or an enforcement boundary.
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent
CONTROLLER = REPO / 'controller'


def doctor():
    """Report observable local prerequisites, never claim agent isolation."""
    python_ok = sys.version_info >= (3, 9)
    controller_ok = all((CONTROLLER / name).is_file() for name in (
        'start.py', 'activate_personal.py', 'control_record.py',
        'project_discovery.py', 'signing.py'))
    crypto_ok = importlib.util.find_spec('cryptography') is not None
    return {
        'status': 'PREVIEW_AVAILABLE' if python_ok and controller_ok else 'BLOCKED',
        'python': f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}',
        'python_3_9_plus': python_ok,
        'controller_files_present': controller_ok,
        'cryptography_for_enforced_mode': 'AVAILABLE' if crypto_ok else 'NOT_INSTALLED',
        'native_agent_dispatch': 'NOT_TESTED',
        'agent_file_isolation': 'NOT_TESTED',
        'authenticated_owner_approval': 'NOT_TESTED',
        'note': 'A preview-ready machine is not a verified native-agent or security environment.',
    }


def prepare_project(project, *, create=False, goal=None, output=None, control=None):
    if sys.version_info < (3, 9):
        raise ValueError('Python 3.9 or newer is required')
    if not doctor()['controller_files_present']:
        raise ValueError('Controller files are missing; download the complete repository')
    # The starter's existing validated workflow is the single implementation
    # of inventory, secrets exclusions and copy protection.
    sys.path.insert(0, str(CONTROLLER))
    from start import start
    return start(project, goal, create=create, output=output, control=control)


def _friendly(result):
    status = result['status']
    if status == 'BLOCKED':
        return f"STOPPED: {result['reason']}\nNo project changes made by this command if it failed during preview."
    if status == 'PREVIEW_ONLY':
        return ('PREVIEW ONLY — no files changed.\n'
                f"Project: {result['project']}\n"
                f"Safe files to copy: {result['included_file_count']}\n"
                f"Working copy: {result['working_copy']}\n"
                f"Separate control record: {result['control_record_folder']}\n"
                'Secrets and private folders are excluded by the starter filter; review its list.\n'
                'Next: repeat the same command with --create after checking the paths.')
    if status == 'WORKING_COPY_PREPARED':
        return ('WORKING COPY PREPARED — original project left untouched.\n'
                f"Working copy: {result['working_copy']}\n"
                f"Brief to review: {Path(result['working_copy']) / 'UAT_PROJECT_BRIEF_DRAFT.md'}\n"
                f"AI Host handoff: {result['start_here']}\n"
                f"Control record (keep agents away): {result['control_record_folder']}\n"
                'Next: review and approve the exact completed brief before launching an Architect.\n'
                'Native agents, isolation and authenticated approval are NOT established by setup.')
    return json.dumps(result, indent=2, sort_keys=True)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Try Universal AI Team in a separate, reversible project working copy')
    parser.add_argument('--project', help='Path to your existing project')
    parser.add_argument('--goal', help='Short goal (optional; owner can complete the brief later)')
    parser.add_argument('--create', action='store_true', help='Create the reviewed separate working copy')
    parser.add_argument('--output', help='Advanced: different working-copy destination')
    parser.add_argument('--control', help='Advanced: trusted control record destination')
    parser.add_argument('--doctor', action='store_true', help='Read-only check of local prerequisites')
    parser.add_argument('--json', action='store_true', help='Print the complete machine-readable result')
    args = parser.parse_args(argv)
    try:
        if args.doctor:
            if args.create:
                raise ValueError('--doctor cannot create anything')
            result = doctor()
        elif not args.project:
            raise ValueError('Give --project /path/to/your-project, or use --doctor')
        else:
            result = prepare_project(args.project, create=args.create, goal=args.goal,
                                     output=args.output, control=args.control)
    except (OSError, RuntimeError, ValueError) as exc:
        result = {'status': 'BLOCKED', 'reason': str(exc)}
    print(json.dumps(result, indent=2, sort_keys=True) if args.json or args.doctor
          else _friendly(result))
    raise SystemExit(2 if result['status'] == 'BLOCKED' else 0)


if __name__ == '__main__':
    main()
