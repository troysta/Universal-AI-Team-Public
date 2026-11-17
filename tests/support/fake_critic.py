"""TEST-ONLY critic: reads the prompt, tries to peek at the author's notes, prints a verdict.

Usage: fake_critic.py NOTES_PATH [PASS|FAIL|NONE]
"""
import sys

prompt = sys.stdin.read()
notes = sys.argv[1]
verdict = sys.argv[2] if len(sys.argv) > 2 else 'PASS'
try:
    with open(notes, encoding='utf-8') as handle:
        print('peeked:', handle.read())
except OSError as exc:
    print('could not read notes:', type(exc).__name__)
print('Reviewed prompt of', len(prompt), 'chars')
if verdict != 'NONE':
    print('VERDICT:', verdict)
