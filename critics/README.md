# Independent critic requirements

Each Architect and Specialist submission receives a blind review by a separate critic, followed by a distinct Final Critic. Give critics the approved task and reviewable artifact, but not the author's private reasoning or prior critic verdicts. Independently verify separation; labels alone are not evidence.

Record verdicts as `PASS`, `FAIL` or `BLOCKED`, with evidence. A missing artifact or unverified independent context must be `BLOCKED`. Allow at most three submissions per task; stop and escalate to the owner after the third failure.

## Mandatory task Quality Bar (development candidate)

Before an Architect review, the Architect must prepare `UAT_QUALITY_BAR.json` alongside `UAT_TEAM_PLAN.md`. Every task listed for owner approval must have **exactly five** named, measurable pass/fail gates, a goal and audience, and at least one local reference source with an exact SHA-256. Each gate states:

- The requirement and specific pass condition.
- How a reviewer can test it.
- What evidence the reviewer must provide.

The Architect Critic receives and examines **both** documents; its signed review evidence binds hashes of both. The owner signs the exact plan SHA-256 **and** Quality Bar SHA-256 in a single `team_plan` approval. Later stages refuse a changed Quality Bar, a changed referenced source, or a missing protected copy. The validation enforces structure and integrity, **not whether the rubric is genuinely a good measure of quality** — the Architect Critic and owner must judge that.

The Specialist Critic receives the current artifact and the **approved** Quality Bar, not the builder's notes or prior verdicts. It returns a JSON object on a line beginning `GATE_RESULTS:` with one entry per gate, for example `"G1":{"verdict":"FAIL","evidence":"Screenshot and measured dimensions ..."}`. It also reports `VERDICT: PASS` or `VERDICT: FAIL`. A global PASS is not accepted if any gate is FAIL or BLOCKED. A gate without an outcome/evidence, or an output whose gate IDs differ from the approved bar, **cannot be recorded as a pass**.

The harness captures the actual critic text in signed evidence. These are critic observations, not automatically independently checked facts; objective tests and a separate human/evidence review remain necessary. Five gates are the fixed v1 trial convention, not a universal law for every project. See `docs/TRIAL_RUNBOOK.md` and `examples/art_vault_quality_bar.example.json`.

These are requirements. This repository does not implement or prove the full critic execution system.

## Bounded Gauntlet rounds and optional human comparison (review candidate)

The maximum is **three author submissions per Architect plan or Specialist task**, never five. After two consecutive signed `FAIL` critic reviews, the trusted controller may stop early for owner assessment:

- **Specialist:** the second failed review did not turn any additional Quality Bar gate into `PASS`, compared with the previous failed review. A new passing gate means measurable progress and permits the third attempt, subject to other gates.
- **Architect:** both rejected plans have identical plan **and** Quality Bar hashes (there is no Architect gate-by-gate score).
- `BLOCKED` evidence is not a successful review and never provides evidence of improvement. The three-submission cap, checkpoint requirements and separate owner promotion/release approvals still apply.

Use the optional label-blind reviewer packet when an owner wants to compare an earlier version against a revised artifact:

```bash
python3 controller/blind_compare.py prepare --working-copy /path/to/project_uat_working --before /path/to/project_uat_working/first.html --after /path/to/project_uat_working/revised.html --task build --packet-dir /private_operator/review_packet_01 --private-dir /private_operator/mapping_01
python3 controller/blind_compare.py score --packet-dir /private_operator/review_packet_01 --private-dir /private_operator/mapping_01 --choice A --passed-a G1,G2 --passed-b G1 --reason "A meets the navigation and contrast gates" --reviewer "Human reviewer 1"
python3 controller/blind_compare.py reveal --packet-dir /private_operator/review_packet_01 --private-dir /private_operator/mapping_01
```

Send the human **only the review packet** (`A.*`, `B.*`, `QUALITY_BAR.json`, approved `REFERENCES/`, and instructions), never the private mapping. The operator must keep the private directory inaccessible to reviewers; chmod alone cannot isolate processes that share an OS account. The reviewer chooses A/B/TIE and scores each gate **before** the operator reveals which is newer. Original artifacts are not changed, scoring is one-shot, and packet hashes are checked. A/B comparison is **optional**, and its result is not an owner approval, critic verdict, or proof of human independence. Content of either artifact or its reference sources could disclose its age; check it before distributing.

## Critic isolation reporting

Isolation is reported **per trial**. Evidence from one trial does not carry over to another.

### Required trial-specific evidence

All four must be present and passed for the trial being reported:

1. **Launch prompt logged and inspected.** The exact prompt passed to each critic is recorded by the harness, not by the critic. The prompt is then checked against the rule: *approved task, artifact under review and spec/reference only — no description of the author's approach, reasoning or prior verdicts.*
2. **Canary test passed.** A unique marker (and, optionally, a deliberately false claim) is placed only in the author's private material. The critic's output must not repeat the marker or rely on the false claim.
3. **Restricted file access independently tested.** The harness, not the critic, attempts to read a forbidden file (for example the author's notes) **using the critic's actual permissions and environment**, and logs the result. A test run under any other permissions or environment does not count, because it could produce a misleading pass. If the read succeeds, the requirement fails.
4. **Known residual leak paths documented.** The trial report links to or restates the residual leak paths below and notes any that were mitigated for this trial.

### Evidence record

Every trial produces one evidence record. It is only valid if both of the following hold.

**Protected storage.** The harness writes the record and all its logs to a location that the working agents and critics cannot modify. That means outside the working copy, and not writable under any agent's or critic's permissions. If an agent or critic could have changed the evidence, the trial is `BLOCKED`, even if every check passed.

**Exact test environment.** The record states, for each critic:

- Trial ID
- Critic identity (role, agent or session ID, and model)
- Permissions and tool access the critic actually ran with
- Files and folders the critic could read, and any it could write
- The logged launch prompt
- Canary marker used and where it was placed
- The forbidden-file read attempted by the harness and its result
- Time of each check

The record must contain enough detail for someone who was not part of the trial to examine the results independently. If any item is missing, the trial is `BLOCKED`.

### Reporting rule

- All four requirements present and passed, with a valid evidence record:

  `isolation: EVIDENCED (trial <id>) — prompt logged and inspected, canary clean, file restriction tested under critic permissions. Residual leak paths documented, not excluded.`

- Any requirement missing or failed:

  `isolation: BLOCKED (trial <id>) — <which requirement> <missing | failed>: <evidence>`

Never report isolation as `VERIFIED`. Passing these checks is evidence of isolation, not proof that no information leaked.

### Known residual leak paths

These checks do not rule out the following channels. Each trial should state whether each one was mitigated, and how.

1. **Git history and commit messages** in the working copy can describe the author's approach.
2. **Shared temporary folders and environment variables** can carry author notes or state between agents.
3. **The host's launch wording.** A prompt such as "check the fix for the null bug" leaks the author's reasoning while still passing the canary and file tests. Only inspecting the logged prompt (requirement 1) catches this.
4. **Web or network access**, if critics have it, can expose author material published or cached elsewhere.
5. **Earlier critic verdicts left in readable files** can anchor a later critic, which breaks the no-prior-verdicts rule.

### Trusted harness and signed evidence

Evidence must come from the harness, not from values written into a file. `controller/critic_harness.py` does every check itself:

1. Plants a fresh canary in the author's private notes (the forbidden file).
2. Attempts to read that file **through the critic's own launcher**, so the read runs with the critic's actual permissions and environment.
3. Launches the critic through the same launcher with the exact prompt, and keeps the prompt and output.
4. Marks the canary `LEAKED` if it appears in the critic's output.
5. Writes a read-only evidence record outside the working copy, signed with the **harness** private key. The harness key is separate from the owner's approval key.

Trial and critic-role identifiers are validated as safe filename components; the harness refuses output paths that escape the evidence directory or overwrite existing evidence files. A separate trusted `--notes-root` CLI argument pins the exact dedicated author-notes directory, **not** a path from trial JSON. The `forbidden_path` must be an existing `.md`/`.txt` file inside that root, separate from the working copy, evidence and signing keys. Symlinks and hard links are rejected; the harness opens each path component without following links before appending the canary. Operating systems without supported directory-fd/no-follow file operations are `BLOCKED`. The signed evidence includes the approved notes root so another reviewer can compare it with the canary path.

The trial JSON and executable critic command still require trusted operator review. A protected notes root constrains the canary write; it does **not** make arbitrary untrusted trial commands safe to execute.

Launch-prompt inspection is a human step. The record starts with inspection `PENDING`; the owner adds `PASS` or `FAIL` with `critic_harness.py inspect`, which refuses to sign a record whose signature no longer matches.

Critic verdicts reach the dispatcher only through `critic_harness.py verdict <evidence> --critic <n>`. It refuses unless that critic's evidence record assesses as `EVIDENCED`. The verdict is taken from the critic's own last `VERDICT: PASS|FAIL` line in the recorded output (no line = `BLOCKED`), bound to the artifact hash recorded before and after the review; each evidence entry can be used once. The dispatcher counts failed reviews per loop (the Architect's plan and each Specialist task): after the third, that loop is stopped and escalated to the owner.

`controller/critic_evidence.py` checks the record with the harness **public** key. It returns `BLOCKED` if the signature is missing or invalid, the record wasn't produced by the harness, inspection is not `PASS`, the canary leaked, the forbidden read wasn't denied or wasn't run with the critic's permissions, the record is inside the working copy or writable by a critic, or any field or residual leak path is missing.

A trial config for the harness looks like this:

```json
{
  "trial_id": "T-001",
  "working_copy": "/path/to/project_uat_working",
  "evidence_dir": "/path/outside/agents/evidence",
  "critics": [{
    "role": "specialist_critic", "model": "...",
    "launcher": ["sudo", "-u", "uat-critic"],
    "command": ["<headless critic command that reads the prompt on stdin>"],
    "prompt": "Review artifact X against the approved spec.",
    "forbidden_path": "/path/to/author_private/notes.md",
    "permissions": ["read artifact"], "readable_paths": ["..."], "writable_paths": ["..."]
  }],
  "residual_leak_paths": {
    "git_history": "...", "shared_temp_and_env": "...", "host_launch_wording": "...",
    "network_access": "...", "earlier_verdicts_in_files": "..."
  }
}
```

`permissions`, `readable_paths` and `writable_paths` are declared by the owner, and the record marks them as such. The forbidden-file read is the measured check. Without a real boundary in the launcher, that read succeeds and the trial is `BLOCKED`. The harness cannot create the boundary for you.
