# Verified status and gaps

Source: selected project-discovery starter files from the protected baseline of 17 November 2026. Internal trial and approval records are excluded.

## Reverified in preparation

- 17 of 17 included Python tests passed in the initial release preparation.
- 18 of 18 Python tests passed in a clean local copy of the public-review repository on 17 November 2026.
- Source contains an activation/project-discovery starter and a synthetic notes example.
- Original baseline ZIP was not edited.

## Added after publication (pending owner review)

- Approval state and approved-brief copy moved to a control folder outside the working copy; the working-copy handoff is informational only.
- `--verify-brief --stage <stage>` re-checks the approved brief before each stage and logs the result.
- Found briefs are fenced as untrusted text; briefs over 12,000 characters add an owner placeholder that blocks approval until reviewed.
- Wider secrets filter (`id_rsa*`, `id_ed25519*`, `.git-credentials`, `.netrc`, `.pypirc`, `*.sqlite`).
- Trusted critic harness (`critic_harness.py`): plants the canary, runs the forbidden-file read through the critic's own launcher, launches the critic, and writes a harness-signed evidence record; `critic_evidence.py` rejects unsigned, edited or non-harness records and reports `EVIDENCED` or `BLOCKED`.
- Stage dispatcher (`dispatcher.py`): `run` for trusted-side launches; `hook` for host sub-agent launches.
- Owner gates enforced by the dispatcher (`gates.py`): signed brief; owner approval of the critic-reviewed team plan before any Specialist; tasks limited to the approved plan; review required between submissions; three signed `FAIL` verdicts stop the task and escalate to the owner; Final Critic `PASS` for the exact candidate before a promotion proposal; separate owner approvals of the exact candidate for promotion and then release.
- Separate keys: passphrase-protected owner key for approvals, harness key for critic verdicts and evidence; both public keys pinned by fingerprint in a host-controlled trust config. Each signer is checked against its pinned role.
- Explicit owner action: approvals need the passphrase and typing the first 8 characters of the exact SHA-256 at an interactive terminal.
- Boundary probe: before every launch the dispatcher checks, through the agents' own launcher, that private keys are unreadable and the control folder, trust config, public keys, evidence folders and dispatcher code are unwritable. Otherwise `BLOCKED`.
- Pre-launch hook requires a harness-signed launch ticket bound to the exact prompt, stage, task, submission and candidate; the agent cannot choose or relabel the stage.
- Critic verdicts are recorded only from `EVIDENCED`, harness-signed isolation evidence; the verdict is the critic's own output line, bound to the reviewed artifact hash; evidence is single-use.
- Three-failure stop applies to the Architect's plan loop as well as each Specialist task.
- Candidates and approved subjects are handled as bytes, so ZIP archives and other binary deliverables work.
- Offline owner approvals (`owner.py request` / `sign` / `submit`) keep the owner key off the agents' machine.
- 80 of 80 Python tests pass locally, including bypass attempts. The agent boundary in tests is a test-only fake sandbox.

## Separate Quality Bar branch — awaiting review (18 November 2026)

- Phase 1 adds the mandatory, task-specific `UAT_QUALITY_BAR.json` with **five measurable gates per task**, a goal/audience, reference-file hashes, pass conditions, test methods and evidence requirements.
- Architect Critic evidence binds the exact proposed team plan **and** Quality Bar. Owner's `team_plan` signature binds both hashes; the control folder stores an approved copy and stages recheck file and reference-source integrity.
- Specialist Critic evidence must include `GATE_RESULTS:` with a verdict and supporting evidence for every approved gate. Incomplete or contradictory gate results cannot count as a pass. Final Critic receives the bar and cannot record a review before specialist tasks have accepted reviews.
- **91 of 91 Python tests pass locally**, including negative tests for changed/missing gates, changed references, missing evidence and a two-round **synthetic** Art Vault framing example (failed mat measurement, focused correction, then pass). The example is deterministic test code, **not a genuine native AI critic or a Samsung device test**.
- These changes are **proposed on a separate development branch**, not merged into `main` or promoted as a protected baseline. The no-improvement stop and optional blind human comparison are developed in a **later stacked review candidate**, described below; neither has been merged.
- Live host-native agents and independently examined isolation evidence are still **BLOCKED / not established**. The prior 80-test baseline and its limitations remain historically true; the 91-test result refers only to this unmerged candidate.

## Follow-up security review branch — awaiting owner review (18 November 2026)

- After reviewing draft PR #5 and #6, a local trial confirmed that `trial_id=../escaped_trial` could write a signed evidence record **outside** the configured evidence folder. The harness now validates trial and critic-role filename components, checks evidence output location and uses exclusive creation rather than overwriting an existing file.
- A separate trial confirmed that a failed stage process was recorded as launched and prevented the next submission. Failed Architect/Specialist starts now log `STAGE_LAUNCH_FAILED`, count as failed attempts (never fabricated critic verdicts), and release the review checkpoint for another attempt. Three attempts still stop and escalate to the owner.
- **98 of 98 Python tests pass locally** after these changes, including filename traversal, symlink overwrite protection, signing-key canary protection, failed launches and mixed technical/critic failures. These are offline tests, with a fake agent sandbox.
- This follow-up is a **separate unmerged candidate** stacked on PR #6; it does not authorise merging either preceding PR, baseline promotion or public release. Live independent agent isolation remains **BLOCKED**.

## Canary root hardening — separate draft candidate (18 November 2026)

- A follow-up security review reproduced a second vulnerability: the trusted harness could append a canary to a **different** private key when a trial's `forbidden_path` named it. The earlier key check protected only the harness's own signing key.
- New `--notes-root` must come from the **trusted operator's CLI**, not the trial JSON. The harness accepts only existing text notes inside that approved dedicated directory; it rejects roots overlapping the harness signing key, working copy or evidence, as well as symlinks, hard links and disallowed filename types. Secure directory-relative, no-follow opens defend against a parent-symlink replacement between validation and write.
- Signed evidence includes the approved notes root; evidence assessment checks that each canary file was inside it.
- **105 of 105 offline Python tests PASS locally**, including a disposable second signing-key protection test, symlink and hard-link tests, a simulated parent-symlink race, rejection of trial-JSON attempts to override the trusted notes root, and previously existing regressions. No real owner credentials or project assets were modified.
- This branch is **review-only**. The signed harness still requires a trusted trial configuration and the first genuine host-native agent isolation run remains **BLOCKED / not established**. No PR merge, protected-baseline promotion or production claim.

## Gauntlet improvement candidate — separate draft (18 November 2026)

- After two consecutive `FAIL` reviews, the controller can stop early at `STALLED_OWNER_REVIEW`. For Specialists, this requires a second failed round with **no newly passing Quality Bar gate**. An improvement in a gate permits the third attempt. For Architect plans (which have no gate-level progress score), early stopping requires exactly the same rejected plan and Quality Bar hashes twice. `BLOCKED` reviews are not treated as a failed-improvement pair.
- This is a deliberately narrow, measurable stall rule. A change may improve the work without changing a gate from FAIL to PASS; the owner can assess that at the stop checkpoint. The existing hard three-submission limit, owner gates and signatures remain unchanged.
- Optional `controller/blind_compare.py` prepares randomly labelled A/B copies and approved reference documents in a **separate review packet**. A separate private folder holds the mapping until a human score is recorded. The reviewer chooses A/B/TIE, records which gates each passes, then the operator can reveal the labels. Neither candidate nor approved baseline is modified.
- A/B labels being hidden does **not** establish reviewer identity, independence, an unbiased Quality Bar, or that artifact content itself does not disclose its origin. Human comparison is optional and cannot override approval or release gates.
- **113 of 113 offline tests passed locally**, exercising early-stop, continued improvement, two possible label assignments, score tampering and reference integrity. No real human blind comparison or genuine host-native trial has been executed. **Isolation remains BLOCKED**.
- This is a **review-only stacked branch**, not approved to merge, deploy, or promote as a protected baseline.

## One-command safe setup — separate draft (18 November 2026)

- Root `install.py` exposes a **read-only preview** with `--project`, then explicit `--create` to use the existing inventory, common-secrets exclusions and separate working-copy/control-record preparation. `--doctor` reports local prerequisites without claiming live security or agent capability.
- `QUICKSTART.md` gives a short path for someone with an existing project, including Windows and ZIP alternatives. No controller folder needs copying or renaming for this introductory workflow.
- Setup does **not** change the original project, install agents, bypass owner approval, create a real filesystem boundary or run the native-agent trial. Full enforced setup remains in `docs/TRIAL_RUNBOOK.md`.
- **119 of 119 offline tests passed locally** across the stacked candidate, including new preview/no-write, excluded credentials, no-overwrite and control-folder placement regressions. The security boundary still needs genuine external validation; isolation remains **BLOCKED**.
- Draft-only, stacked on the Gauntlet review candidate; **no main-branch merge or protected-baseline promotion**.

## Not established by this package

- Fully automatic native-agent dispatch: **UNVERIFIED**.
- Enforced per-agent filesystem or tool isolation: **BLOCKED / not implemented**.
- Cryptographically authenticated owner approval: **UNVERIFIED**; local approval records are not identity proof.
- Agent boundary (separate OS user or container): **not provided by this package**; setup is in `docs/TRIAL_RUNBOOK.md`. The dispatcher refuses to launch without it, but only the owner can build it.
- Genuine end-to-end native-agent isolation trial: **not yet run**. Overall isolation status: **BLOCKED** until a trial produces evidence.
- Dispatcher as the only launch path: **depends on the host**. If the host can start agents without the dispatcher or hook, the gates can be bypassed.
- Hook mode cannot record that a ticket was used, so the identical ticketed prompt could be launched again before it expires (default 30 minutes). It cannot be relabelled or reused for another stage, task or submission.
- Owner identity: a signature proves possession of the owner key and passphrase and a deliberate approval of the exact content, not which person acted. With the offline route the key is off the agents' machine; a hardware security key would bind it to a physical device.
- Independent critic contexts and final review in the historical example: **reported in promotion record**, not independently rerun by these unit tests.
- Real-project production readiness: **NOT CLAIMED**.

Next priority: the first genuine end-to-end trial in `docs/TRIAL_RUNBOOK.md`, then rerun all regression tests. Promotion of a new protected baseline requires a separate owner approval.

## Publication boundary

**Public GitHub collaboration was explicitly approved by the owner on 17 November 2026 for this experimental review repository.** This is not approval for production deployment, protected-baseline promotion, or release of private trials and handoff records.
