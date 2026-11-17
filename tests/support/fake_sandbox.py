"""TEST-ONLY stand-in for a real sandbox launcher.

Usage: fake_sandbox.py DENY_DIR[:DENY_DIR...] -- command...
Runs the command with a Python audit hook that refuses to open anything under
any DENY_DIR. It only constrains Python commands and is NOT a security boundary;
it exists so tests can exercise the harness's DENIED path without root, a
second OS user or a container.
"""
import os
import sys
import tempfile

deny = [os.path.realpath(d) for d in sys.argv[1].split(os.pathsep) if d]
command = sys.argv[3:] if sys.argv[2] == '--' else sys.argv[2:]
site = tempfile.mkdtemp(prefix='uat_fake_sandbox_')
with open(os.path.join(site, 'sitecustomize.py'), 'w') as handle:
    handle.write(
        'import os, sys\n'
        f'DENY = {deny!r}\n'
        'def _hook(event, args):\n'
        '    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):\n'
        '        path = os.path.realpath(os.fsdecode(args[0]))\n'
        '        if any(path == d or path.startswith(d + os.sep) for d in DENY):\n'
        '            raise PermissionError("fake sandbox: " + path)\n'
        'sys.addaudithook(_hook)\n')
env = dict(os.environ, PYTHONPATH=site)
os.execvpe(command[0], command, env)
