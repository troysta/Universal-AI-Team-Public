# Safeguards and permissions

- Preserve protected baseline files; conduct work in separate copies.
- Require owner approval of the project brief before Architect execution.
- Keep approval state and the approved brief in a control folder outside the working copy. Never read approval state from the working copy.
- Re-check the approved brief against the control record before every stage; a changed or missing brief is `BLOCKED`.
- Store critic-isolation evidence where working agents and critics cannot modify it.
- Owner approvals (brief, team plan, promotion, release) are signed with a passphrase-protected owner key and need an explicit confirmation at a terminal. Critic verdicts and evidence use a separate harness key. Both public keys are pinned by fingerprint in a host-controlled trust config.
- Record critic verdicts only from `EVIDENCED` isolation evidence; never type a verdict in.
- Prefer offline owner approvals so the owner key never sits on the agents' machine.
- Start every stage through the dispatcher (or its pre-launch hook with signed launch tickets). It enforces every gate in `controller/gates.py`: approved brief, owner-approved reviewed team plan before Specialists, three-failure stop, accepted Final Critic review before promotion proposals, and separate owner approvals of the exact candidate for promotion and release.
- The dispatcher probes the agent boundary before each launch and refuses if agents can read a private key or write trusted files.
- Run agents under a separate OS user or container. Without that boundary, none of the above is enforced.
- Require a separate owner gate for the reviewed Architect team plan before dispatch.
- Require independent final review before any promotion proposal.
- Treat promotion and public release as **separate owner decisions** about an exact candidate.
- Stop after three failed submissions and escalate to the owner.
- Do not represent local approval metadata as cryptographically authenticated identity.

Internal approval records and protected baseline promotion history are deliberately excluded from this public-review package. These safeguards are requirements, not proof of full technical enforcement.
