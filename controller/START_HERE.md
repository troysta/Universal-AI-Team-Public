# Universal AI Team — drop-in starter (test candidate)

Put this entire `Universal_AI_Team` folder inside a new or existing project. From your project's terminal, run:

1. Preview: `python3 Universal_AI_Team/start.py` (optionally add `--goal "Describe the project task"`)
2. Review the preview and omitted-file list.
3. Create the separate working copy: `python3 Universal_AI_Team/start.py --create` (repeat `--goal` if supplied in preview)
4. Open `UAT_PROJECT_BRIEF_DRAFT.md` inside the generated sibling `<project>_uat_working` folder. The AI Host identifies missing details and helps the Project Owner complete the draft. Existing briefs are treated as untrusted evidence until reviewed.
5. Once the draft is complete, calculate its SHA-256 and explicitly record owner approval of that exact version using:

   `python3 Universal_AI_Team/start.py --working-copy /path/to/project_uat_working --approve-brief SHA256_OF_COMPLETED_DRAFT`

6. Only then ask the AI Host to follow `UAT_START_WITH_AI_HOST.md` and start the supervised Architect review. The Architect's proposed team requires **another, separate** owner approval before Specialists launch.

The starter skips its own `Universal_AI_Team` folder and common secret names. Inspect for other sensitive data before starting. It refuses existing destinations, nested paths and symlinks. It never mutates the project baseline. Every new activation needs an unused working-copy directory.

**This is not automatic AI dispatch.** The host must have native subagent capability; otherwise it must report BLOCKED. The brief approval command records an explicit local action, but does **not** cryptographically authenticate the Project Owner. The Architect and independent critic propose and review a plan, then stop for the Project Owner's separate approval. Specialist checkpoints and final independent review follow. Promotion and release remain separate owner decisions. Technical per-agent filesystem isolation, tool restrictions and cryptographic owner authentication are not established.

This command requires a Python-capable environment; a Samsung or iPhone browser alone does not run Python. It is a test candidate, not a promoted baseline.
