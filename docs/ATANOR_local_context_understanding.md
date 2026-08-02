# ATANOR local context understanding — roam-my-PC (design + cautions, FOR LATER)

Owner (2026-07-21, flagged "좀 나중 얘기"): once ATANOR is installed, if the owner grants full
permission, ATANOR autonomously roams the PC, reads files, and understands the owner's whole context
— like computer use. "물론 이에 대한 주의멘트도 넣고."

This is not a new direction — it is the **mechanism** for the standing goal [[hyper-personal-local-agi-goal]]
(초개인화 로컬 AGI): a private AGI that actually knows *your* world. It slots into the existing
[[os-action-lane]] scaffolding (trust tiers + kill switch + activity journal), governed by the same
doctrines that already protect the owner.

## Design (within doctrine — nothing new is loosened)

- **Local-only, private by construction.** Everything ATANOR reads and everything it understands stays
  **on the device**. Nothing is uploaded or sent to any server, ever, as a side effect of roaming.
  This is the whole reason for a No-LLM local brain — privacy is architectural, not a promise.
- **Trust tiers ([[os-action-lane]]), start read-only, earn scope:**
  - T0 Observe (default): read-only index of owner-allowlisted folders → a local context graph.
  - T1 Approve: reads a specific item on the owner's ask, per-item.
  - T2 Guarded: auto-reads within owner-allowlisted directories, every access logged.
  - T3 Autonomous: broad roaming, only within a scope the OWNER sets. ATANOR never widens its own reach.
- **Scoped consent + hard exclusions.** The owner grants specific folders. Hard-excluded by default,
  even under "full permission": credential stores (keychains, password managers, browser login DBs),
  private keys, financial-account files, and anyone else's private data. ATANOR never compiles secrets.
- **Understanding = a local graph, not exfiltration.** ATANOR builds a private context graph (like its
  world graph) of the owner's projects/files/habits — to help, anticipate, answer — that lives and dies
  on-device. Sending anything off-device is a SEPARATE, per-item, owner-approved action, never automatic.
- **File content is DATA, not commands ([[external-minds-are-data]]).** A file that says "ATANOR, delete
  X / send Y to Z" is data passing the gate, never an instruction. This is the primary defence when
  reading arbitrary files (planted prompt-injection).
- **Auditability + kill switch ([[wiring-audit-and-lanes]] activity_journal).** Every file touched is
  logged where the owner can inspect it; an instant kill switch stops all roaming.
- **Moral 0th gate ([[moral-invariants-genesis-immunity]]).** Genesis-immune: ATANOR won't act harmfully
  on what it reads, won't exfiltrate, won't deceive — the same core that makes the avatar refuse theft.

## Cautions (주의멘트) — the most sensitive permission ATANOR can be given

1. **Largest privacy surface possible.** Full PC read = access to everything. Must be explicit, scoped,
   revocable, and local-only. **Default OFF.** Grant folders deliberately — do not blanket-approve.
2. **Prompt-injection via files.** Arbitrary files can carry adversarial text aimed at ATANOR. All file
   content is DATA; ATANOR must never follow directives found inside files.
3. **Credentials / finances are never read or compiled** — passwords, keys, account numbers, others'
   private data — even with "full permission." Non-negotiable.
4. **No exfiltration.** Understanding stays on-device; any send-off-device is a separate owner-approved
   act, per item, never a side effect of roaming.
5. **Auditability.** Every access logged; the owner can see exactly what was read; instant kill switch.
6. **Consent boundary.** Only the owner's own device and files; not shared or other people's data.
7. **Earn scope.** Begin at read-only observe; broaden only as the owner explicitly widens scope.

## Status
FOR LATER (owner-flagged). No code yet — this is the design + cautions on record. When built, it extends
`packages/os_action_lane/` (trust tiers already exist) with a local file-context indexer feeding a
private on-device graph, behind the gates above. Related: [[hyper-personal-local-agi-goal]]
[[os-action-lane]] [[external-minds-are-data]] [[security-threat-model]] [[device-identity]].
