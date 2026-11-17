"""TEST-ONLY deterministic stand-in for an independent Art Vault critic.

This is NOT a host-native agent and is NOT evidence of agent independence.
It proves that the harness signs and accepts actual gate-by-gate outcomes.
"""
import json
import sys
from pathlib import Path


artifact = json.loads(Path(sys.argv[1]).read_text())
bar = json.loads(Path(sys.argv[2]).read_text())
reference = json.loads(Path(sys.argv[3]).read_text())
_prompt = sys.stdin.read()  # harness supplies an artifact and quality bar packet
gates = bar['tasks']['framing']['gates']
assert [gate['id'] for gate in gates] == ['G1', 'G2', 'G3', 'G4', 'G5']
checks = [
    (artifact.get('original_sha256') == reference['original_sha256'],
     'Original SHA compared with immutable input reference'),
    (artifact.get('mat_px') == 17, 'Mat measured against 17px specification'),
    (artifact.get('frame_px') == 10, 'Frame measured against 10px specification'),
    (artifact.get('gallery_image') == 'framed_copy', 'Gallery uses framed working copy'),
    (artifact.get('promotion_image') == 'framed_copy', 'Promotions uses framed working copy'),
]
results = {gate['id']: {'verdict': 'PASS' if passed else 'FAIL', 'evidence': evidence}
           for gate, (passed, evidence) in zip(gates, checks)}
print('GATE_RESULTS:', json.dumps(results))
print('VERDICT:', 'PASS' if all(passed for passed, _ in checks) else 'FAIL')
