# Universal AI Team — drop-in starter (test candidate)

Copy this repository's `controller/` folder into a new or existing project and rename the copy to `Universal_AI_Team`. From your project's terminal, run:

1. Preview: `python3 Universal_AI_Team/start.py` (optionally add `--goal "Describe the project task"`)
2. Review the preview and omitted-file list.
3. Create the separate working copy: `python3 Universal_AI_Team/start.py --create` (repeat `--goal` if supplied in preview). This also creates a sibling `<project>_uat_working_control` folder holding the authoritative approval record. Agents must not be given write access to it.
4. Open `UAT_PROJECT_BRIEF_DRAFT.md` inside the generated sibling `<project>_uat_working` folder. The AI Host identifies missing details and helps the Project Owner complete the draft. Existing briefs are treated as untrusted evidence until reviewed.
5. Once the draft is complete, calculate its SHA-256 and explicitly record owner approval of that exact version using:

   `python3 Universal_AI_Team/start.py --working-copy /path/to/project_uat_working --approve-brief SHA256_OF_COMPLETED_DRAFT`

   Approval state is read only from the control folder. `UAT_PERSONAL_HANDOFF.json` in the working copy is an informational copy, so editing it approves nothing.

6. Only then ask the AI Host to follow `UAT_START_WITH_AI_HOST.md` and start the supervised Architect review. The Architect prepares both `UAT_TEAM_PLAN.md` and a task-by-task `UAT_QUALITY_BAR.json` in the working copy. Each task must have five testable gates and SHA-256-bound local reference sources (see `examples/art_vault_quality_bar.example.json`). The Architect Critic reviews both. The owner then approves the **exact plan and Quality Bar together** before Specialists launch.

7. Before each stage starts, re-check the approved brief:

   `python3 Universal_AI_Team/start.py --working-copy /path/to/project_uat_working --verify-brief --stage architect`

   Stages: `architect`, `architect_critic`, `specialist`, `specialist_critic`, `final_critic`, `promotion_proposal`. If the approved brief has changed since approval, the result is `BLOCKED` and the stage must not start. Every check is logged in the control record.

## Enforced mode (owner gates, pinned keys, dispatcher, trusted harness)

Needs `pip install cryptography`. Full step-by-step setup and the first genuine trial are in `docs/TRIAL_RUNBOOK.md`. In short:

1. **Two key pairs, created on the trusted side only:** an owner key (always passphrase-protected) for approvals, and a separate harness key for critic verdicts and evidence.

   `python3 Universal_AI_Team/signing.py ~/.uat/owner.pem ~/.uat/owner.pub --role owner`

   `python3 Universal_AI_Team/signing.py ~/.uat/harness.pem ~/.uat/harness.pub --role harness`

2. **Pin both public keys** in a host-controlled trust config outside every working copy (see `examples/trust_config.example.json`). The dispatcher rejects any key file whose fingerprint doesn't match.

3. **Owner approvals need an explicit action.** Gates: `brief`, `team_plan` (with `--tasks`; hashes both the reviewed plan and mandatory Quality Bar), `promotion` and `release` (with `--candidate`; any file type, including ZIP archives).

   - On this machine, at a terminal (passphrase, then the first 8 characters of the exact SHA-256):
     `python3 Universal_AI_Team/owner.py approve team_plan --working-copy … --signing-key ~/.uat/owner.pem --trust-config ~/.uat/trust.json --tasks build,docs`
   - **Recommended:** offline, so the owner key never sits on the agents' machine: `owner.py request … --out req.json` here; `owner.py sign req.json --signing-key … --out signed.json` on a separate owner device; then `owner.py submit signed.json …` here.

4. **Start every stage through the dispatcher.** It checks the pinned keys, probes the agent boundary through the launcher, and enforces every gate (see `controller/gates.py`):

   `python3 Universal_AI_Team/dispatcher.py run --working-copy … --trust-config ~/.uat/trust.json --stage specialist --task build --launcher '["sudo","-u","uat-agent"]' -- <stage command>`

   If a stage process exits unsuccessfully or cannot be started, `run` returns `BLOCKED` and logs `STAGE_LAUNCH_FAILED`. For Architect/Specialist work this consumes **one** of the three allowed attempts, but releases the pending-submission checkpoint so another attempt can start. Three launch failures, or a combination of launch failures and failed critic reviews, stop and escalate to the owner. A technical launch failure is **not** represented as an independent critic verdict.

5. **Critic verdicts come only from evidence.** `critic_harness.py verdict <evidence.json> --critic 0 …` records a verdict only if that critic's isolation evidence assesses as `EVIDENCED`; the verdict is the critic's own `VERDICT:` line, bound to the exact artifact hash it reviewed. For a Specialist Critic the output must also include `GATE_RESULTS:` with pass/fail evidence for all five approved gates. If the bar or its referenced source changed, if a gate lacks evidence, or if gate results contradict PASS, the verdict cannot be recorded. Three failed reviews stop the Architect's plan loop or a Specialist's task and escalate to the owner.

   Evidence trial IDs and critic role IDs must be simple filename components (letters, numbers, underscores and hyphens). The harness rejects path separators and pre-existing output files. **The trusted operator must supply a dedicated author-notes folder separately** when running a trial: `critic_harness.py run trial.json --signing-key /trusted/harness.pem --notes-root /work/author_private`. `--notes-root` is not accepted from trial JSON. Canary notes must be existing `.md` or `.txt` files inside that exact approved folder; symbolic links, hard links, sensitive key files and paths outside the folder are refused before any write. Secure appending requires supported OS directory-fd/no-follow operations; unsupported systems return `BLOCKED`.

6. **If the host launches sub-agents itself,** issue a launch ticket on the trusted side for each one, then install the dispatcher as a pre-launch hook:

   `python3 Universal_AI_Team/dispatcher.py ticket --working-copy … --trust-config … --signing-key ~/.uat/harness.pem --stage specialist --task build --prompt-file prompt.txt --launcher '…'`

   The output is the prompt with a signed `UAT-TICKET:` first line, bound to that exact prompt, stage, task and submission. The hook blocks any sub-agent launch without a valid, unexpired ticket. Example Claude Code hook:

   ```json
   {"hooks": {"PreToolUse": [{"matcher": "Task|Agent", "hooks": [{"type": "command",
     "command": "python3 /trusted/Universal_AI_Team/dispatcher.py hook --working-copy /path/to/project_uat_working --trust-config /trusted/trust.json"}]}]}}
   ```

None of this is enforced unless the agents run as a separate OS user or in a container that can't read the private keys or write to the control folder, trust config, public keys, evidence folders, dispatcher code or hook configuration. The dispatcher's boundary probe refuses to launch when that boundary is missing.

**This is not automatic AI dispatch.** The host must have native subagent capability; otherwise it must report BLOCKED. The brief approval command records an explicit local action, but does **not** cryptographically authenticate the Project Owner. The Architect and independent critic propose and review a plan, then stop for the Project Owner's separate approval. Specialist checkpoints and final independent review follow. Promotion and release remain separate owner decisions. Technical per-agent filesystem isolation, tool restrictions and cryptographic owner authentication are not established. The control folder is protected by location and read-only file mode only, not by a sandbox: an agent running as the same OS user could still change it.

This command requires a Python-capable environment; a Samsung or iPhone browser alone does not run Python. It is a test candidate, not a promoted baseline.
