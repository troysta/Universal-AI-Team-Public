"""TEST-ONLY critic: reads the prompt, tries to peek at the author's notes, prints a verdict.

Usage: fake_critic.py NOTES_PATH [PASS|FAIL|NONE]
"""
import json
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
    gates = {f'G{i}': {'verdict': 'PASS' if verdict in ('PASS', 'GATELESS', 'BADGATE', 'EVIDENCELESS')
                       or i != 1 else 'FAIL',
                       'evidence': f'TEST-ONLY simulated gate {i} result'} for i in range(1, 6)}
    if verdict == 'BADGATE':
        gates['G1']['verdict'] = 'FAIL'
    if verdict == 'EVIDENCELESS':
        gates['G2']['evidence'] = ''
    if verdict != 'GATELESS':
        print('GATE_RESULTS:', json.dumps(gates))
    print('VERDICT:', 'PASS' if verdict in ('GATELESS', 'BADGATE', 'EVIDENCELESS') else verdict)
