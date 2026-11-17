# Universal AI Team — start with your existing project

This is an **experimental supervised development candidate**, not a production AI-team service. You can preview and prepare a separate working copy in two commands. Your original project is not edited, and no agent is launched during setup.

## 1. Get the starter

On a computer with **Python 3.9+** (Windows, macOS or Linux), open a terminal:

```bash
git clone https://github.com/troysta/Universal-AI-Team-Public.git
cd Universal-AI-Team-Public
python3 install.py --doctor
```

On Windows use `py -3` instead of `python3` if needed. Alternatively download GitHub's ZIP, extract it and open a terminal in the extracted folder. No API key is needed for the preview. A Samsung phone browser alone **cannot** run the Python installer.

## 2. Preview what would be copied

```bash
python3 install.py --project /path/to/your-existing-project
```

This inventories project files and shows where a **separate working copy** and an **outside control folder** would go. It excludes common credential and private folders, but this is a filter, not a guarantee that every sensitive file is recognized. **Read the preview and check your source before continuing.** There are no writes during preview.

## 3. Create the supervised working copy

```bash
python3 install.py --project /path/to/your-existing-project --create
```

For a more focused first task, add `--goal "Improve the artwork card display"` to both commands. The command refuses to overwrite an existing destination. It **never installs code into, edits, or deletes the original project**. You will see:

- `<project>_uat_working` — disposable working copy with `UAT_PROJECT_BRIEF_DRAFT.md` and `UAT_START_WITH_AI_HOST.md`.
- `<project>_uat_working_control` — separate authoritative records; working agents must not be able to write here.

## 4. Give your AI Host one bounded instruction

First, **review and finish `UAT_PROJECT_BRIEF_DRAFT.md` together**. Approve the exact completed draft using the owner-controlled approval procedure in `controller/START_HERE.md`. Do not treat the presence of the draft, or a hash alone, as identity-authenticated consent.

Only once the brief is approved, tell your AI Host:

> Work only inside the generated `_uat_working` copy. Read `UAT_START_WITH_AI_HOST.md` and the approved brief. Propose a minimal team plan and a five-gate Quality Bar. Have a separate Architect Critic review them. Show me the reviewed plan and wait for my explicit approval before launching Specialists. Do not change my original project or publish anything. Report any missing native-agent isolation or enforcement capability as BLOCKED.

The optional A/B reviewer tool and Gauntlet early-stop rule are described in `critics/README.md`.

## What the two commands do **not** do

- They do **not** connect or launch independent agents automatically.
- They do **not** prove that a critic cannot read builder notes or that the owner is authenticated.
- They do **not** install an OS-user/container boundary; enforced mode requires extra trusted setup from `docs/TRIAL_RUNBOOK.md` and `pip install -r requirements.txt`.
- They do **not** promote a baseline or approve publication, deployment, spending, deletion or release.

All control records and security rules are proposals until run in a real, independently examined trial. Current evidence is in `docs/STATUS.md`.
