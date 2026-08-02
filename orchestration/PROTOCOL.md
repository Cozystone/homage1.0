# Claude ↔ Codex orchestration — file mailbox protocol

Robust handoff with **no UI / no Computer Use**. The old loop had Codex puppet
Claude Desktop's UI via Computer Use; Windows window-focus kept failing. This
moves the exchange to the shared filesystem (deterministic, focus-independent).

## Channel
```
orchestration/requests/   REQ-<id>.json   Claude files a request at an approval gate
orchestration/responses/  RESP-<id>.json  Codex files the verdict
```
Both sides use `scripts/orchestration_mailbox.py` so the format is identical.

## Risk tiers (who may approve)
- `auto_ok` — reversible/local RED (sidecar/store-local writes, code changes that
  are backed up + reversible). **Codex may `approve`.**
- `operator_only` — irreversible/external (git push/PR, deploy, publish, permission
  changes, real-data delete). **Codex MUST `escalate`; only the human decides.**
  (The mailbox auto-downgrades any `approve` on an `operator_only` request.)

## Flow (no operator required for auto_ok)
1. **Claude** hits a gate → `mailbox request --action ... --tier ... --question ...`
   → schedules its own wake-up (Claude's `send_later`/ScheduleWakeup, server-side)
   → ends the turn.
2. **Codex** (its scheduled task, repurposed to FILE I/O — see
   `orchestration/codex_scheduled_task_prompt.txt`): `mailbox list-pending` →
   review each per No-LLM / risk rules → `mailbox respond --id ... --verdict ...`.
   **No clicking, no Claude-Desktop operation — only file read/write.**
3. **Claude** wakes → `mailbox check --id ...` → `approve` ⇒ proceed; `escalate`/
   none ⇒ surface to operator (push) / re-schedule with backoff.

## Safety
- v3 risk-tiering preserved: irreversible/external always `operator_only`.
- No-LLM / no-rule-table mutual monitoring still applies inside Codex's review.
- Every approval is an auditable file (timestamp + notes + file:line) — consistent
  with the 4D permanent-memory philosophy.
- Latency = wake interval (minutes). Fine for "don't stall while operator away";
  not real-time.
