# First genuine end-to-end trial — runbook

The automated tests use a fake sandbox. This runbook is for the first trial with **real host-native agents behind a real boundary**. Its result is either `EVIDENCED` for this one trial or `BLOCKED` with the reason. Do not promote anything on the strength of this trial alone.

## 1. Build the boundary

Use either separate OS users or containers. The owner and harness stay on the trusted side.

**Separate users (Linux shown; macOS uses `sysadminctl -addUser`):**

```bash
sudo useradd --system --create-home uat-agent    # Architect and Specialists
sudo useradd --system --create-home uat-critic   # critics: a different user from the authors
sudo mkdir -p /trusted/uat/evidence && sudo chown -R "$USER" /trusted/uat && chmod -R 700 /trusted/uat
```

- Working copy: writable by `uat-agent`, read-only for `uat-critic`.
- Author private notes (the forbidden file): readable by `uat-agent` only (`chmod 700` on its folder).
- The control folder, `/trusted/uat`, this package's `controller/` code and your host's hook settings: owned by you, not writable by either agent user.
- Launchers: `["sudo", "-u", "uat-agent", "--"]` and `["sudo", "-u", "uat-critic", "--"]`. Allow your account to run those with a narrow sudoers rule.

**Containers (alternative):** a launcher such as
`["docker", "run", "--rm", "-i", "--network", "none", "-v", "/work/proj_uat_working:/work/proj_uat_working:ro", "<image>"]`.
Mount only what the role needs, at the same paths, and never mount `/trusted`, the control folder or the author's notes into a critic container.

## 2. Keys and trust config

```bash
python3 controller/signing.py /trusted/uat/owner.pem /trusted/uat/owner.pub --role owner
python3 controller/signing.py /trusted/uat/harness.pem /trusted/uat/harness.pub --role harness
```

Copy `examples/trust_config.example.json` to `/trusted/uat/trust.json` and paste in the two printed fingerprints. List both private keys under `private_key_paths`, and your hook settings file under `protected_paths`.

## 3. Prove the boundary check works both ways

```bash
python3 controller/dispatcher.py run --working-copy /work/proj_uat_working \
  --trust-config /trusted/uat/trust.json --stage architect \
  --launcher '["sudo","-u","uat-agent","--"]' -- true
```

- With the boundary in place, after brief approval, this should report `LAUNCHED`.
- **Negative control:** temporarily run `chmod 755 /trusted/uat` and repeat. It must report `BLOCKED … agents can reach …`. Restore `chmod 700` afterwards. If it doesn't block, stop: the boundary or the probe is not doing its job.

## 4. Run the trial

Use the offline owner route (`owner.py request` / `sign` on a separate device / `submit`) for every approval in this trial, so the owner key is never on this machine.

1. Approve the brief (`owner.py request brief …`, sign offline, `owner.py submit …`).
2. Dispatcher `run --stage architect` (or `ticket` + hook) → Architect writes `UAT_TEAM_PLAN.md`.
3. Dispatcher `run --stage architect_critic`. Critic trial for the plan: copy `examples/trial_config.example.json`, set `stage: architect_critic`, `artifact: …/UAT_TEAM_PLAN.md`, the critic launcher and the author's private notes as `forbidden_path`, then
   `critic_harness.py run trial.json --signing-key /trusted/uat/harness.pem`.
4. Read the logged launch prompt in the evidence record, then `critic_harness.py inspect … --result PASS|FAIL --by "<name>"`.
5. `critic_evidence.py <record> --working-copy … --public-key /trusted/uat/harness.pub` → `EVIDENCED` or `BLOCKED`.
6. `critic_harness.py verdict <record> --critic 0 …`. It refuses unless step 5 is `EVIDENCED`, and uses the critic's own `VERDICT:` line.
7. Owner approves the reviewed plan with `--tasks …` (offline route).
8. For each task: `specialist` launch, `specialist_critic` launch, then steps 3–6 with `stage: specialist_critic`, `task_id` and the task's artifact.
9. `final_critic` on the candidate (steps 3–6 with `stage: final_critic`), then `promotion_proposal`. Promotion and release each need their own owner approval and are outside this trial.
10. **Bypass checks:** try a hook launch with no ticket, with an edited prompt, and with an expired ticket; each must be blocked. Try one launch with the boundary loosened; it must be blocked.

## 5. Report

Record in `docs/STATUS.md`, with the evidence record paths:

- Isolation per critic: `EVIDENCED` or `BLOCKED` with the checker's reasons.
- Negative control result from step 3.
- Which residual leak paths were mitigated, and how.
- Any stage the dispatcher blocked and why.

If any requirement is missing or failed, the trial is `BLOCKED`.
