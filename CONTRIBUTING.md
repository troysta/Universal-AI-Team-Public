# Contributing to Universal AI Team

Thanks for helping improve Universal AI Team. This is an **experimental, supervised starter**, not a production-ready multi-agent system.

## Start here

1. Read [README.md](README.md), [docs/STATUS.md](docs/STATUS.md), and [controller/START_HERE.md](controller/START_HERE.md).
2. Look for a GitHub issue labelled **good first issue**, or open an issue to discuss a small change.
3. Fork the repository or create a separate branch. Make one focused change per pull request.
4. Run the Python unit tests from the repository root:

   ```bash
   PYTHONPATH=controller python3 -m unittest discover -s tests -p 'test_*.py' -v
   ```

5. Open a pull request explaining what changed, why, which tests ran, and what remains unverified. Include a link to the relevant issue.

## Safety and review rules

- Do **not** commit passwords, tokens, credentials, personal information, private handoff records, internal trials, backups, or protected baselines. A `.gitignore` helps but does not make already-tracked files safe.
- Work in separate test copies. Do not alter a project owner's original baseline without explicit approval.
- Keep the distinction between **proposed**, **available**, **executed**, **passed**, and **blocked** capabilities. Do not claim real native-agent dispatch, enforced isolation, or independent critic reviews without evidence.
- Preserve owner approval gates and the three-submission stop. No automatic promotion or release.
- Avoid introducing paid APIs, new credentials, or external services without discussing them in an issue first.
- Make tests deterministic and use synthetic examples rather than real project or user data.

## A good pull request includes

- A short summary and a linked issue.
- Exact test commands and results, plus any tests not run.
- Any changed permissions, files, external dependencies, or security assumptions.
- Clear limitations and follow-up work.

Contributions are reviewed by the repository owner before merging. Please only submit material you have the right to contribute under this repository's [MIT licence](LICENSE).
