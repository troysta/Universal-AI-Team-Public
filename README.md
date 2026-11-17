# Universal AI Team

**Experimental supervised AI-team starter — not production-ready.**

Universal AI Team aims to help a host AI understand a project, prepare an owner-approved brief, coordinate an Architect and specialists, obtain independent reviews, and enforce separate owner approval gates.

This public-review package contains the Python project-discovery starter, unit tests, a synthetic offline notes demonstration, and proposed review/safeguard protocols. It deliberately excludes internal trial records, personal handoff records, and protected baseline promotion history.

## Folders

- `controller/` — Python starter; read `controller/START_HERE.md`.
- `agents/` — proposed agent roles, not automatic dispatch.
- `critics/` — independent review requirements.
- `safeguards/` — approval and baseline rules.
- `tests/` — starter unit tests.
- `docs/` — current verified status and limitations.
- `examples/` — generic offline notes demonstration.

## Run the tests

From the repository root with Python 3:

```bash
PYTHONPATH=controller python3 -m unittest discover -s tests -p 'test_*.py' -v
```

These tests do not prove authenticated owner identity, enforced agent isolation, or automatic native-agent dispatch. See `docs/STATUS.md`.

Public release needs a separate explicit owner decision. Review all files and existing repository contents before any commit.
