# ATANOR Full Host Authority Mode

Status: v0 permission layer plus Host Executor v1 scoped text patching. No destructive commands are implemented.

Full Host Authority is an explicit operator-root mode for the owner's local machine. It exists so ATANOR can be granted broad local capability on purpose, while preventing accidental, silent, remote, or model-only escalation.

## What Tier 4 Can Represent

With explicit activation and matching sub-switches, Tier 4 can authorize:

- PC-wide file reads
- PC-wide file writes
- host shell actions
- code modification
- git commit or push
- Local Brain writes
- Cloud production writes
- browser control
- MCP tools
- code execution

## What Tier 4 Does Not Bypass

Tier 4 does not allow:

- credential exfiltration
- private data upload without exact operator approval
- hidden persistence or autostart installation
- stealth behavior
- destructive delete without secondary confirmation
- disabled audit logs
- OS security prompt bypass
- malware-like replication
- external LLM or sLLM API calls

## v0 Execution Boundary

The v0 implementation verifies permission and records audit events. Host Executor v0 includes only harmless actions: `echo`, `git_status`, bounded text reads, bounded directory listing, runtime-temp writes, runtime-temp backup patch creation, and emergency stop checks.

It does not expose arbitrary shell execution, destructive delete, unrestricted PowerShell, credential reads, private uploads, Local Brain writes, Cloud production writes, git commit, or git push.

## v1 Scoped Patch Boundary

Host Executor v1 adds real file mutation only for scoped UTF-8 text patches. It can replace exact text in explicitly selected source/docs files after a dry-run diff, backup creation, rollback plan, active Tier 4 session, `full_file_write=true`, matching session id, typed confirmation, and emergency-stop check.

It still does not expose destructive delete, unrestricted shell, arbitrary commands, credential reads, private uploads, Local Brain writes, Cloud production writes, candidate promotion, git commit, or git push.

This preserves the design principle: full host authority can exist, but it must be operator-confirmed, scoped by sub-switch, visible, logged, and stoppable.
