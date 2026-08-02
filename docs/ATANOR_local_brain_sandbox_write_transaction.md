# ATANOR Local Brain Sandbox Write Transaction

Status: proof-only, temp-sandbox only.

The Local Brain Sandbox Write Transaction proof is the first place where memory
write plans are actually applied, but only inside a temporary fake Local Brain
store. It never touches real user memory or production Local Brain files.

## Purpose

The previous gate produced a non-applying write plan. This proof checks the next
property: if a future approved memory write is attempted, ATANOR can back up the
store, apply the planned writes, validate the hash change, roll back, and verify
that the original hash is restored.

## Temp Sandbox Only

Sandbox stores are JSON fixtures created under temp directories. Paths that look
like real Local Brain storage, including `data/memory`, `homage.db`,
`homage_memory.sqlite3`, or `canonical_concepts.sqlite3`, are rejected.

## Transaction Model

The transaction records:

- sandbox path
- source write plan id
- store hash before
- store hash after
- backup path
- applied state
- rolled-back state
- `real_local_brain_write=false`

## Backup

The sandbox backup is a real copy of the temp sandbox store only. It is not a
backup of real Local Brain.

## Rollback

Rollback restores the temp backup into the temp sandbox and verifies that the
post-rollback hash matches the pre-transaction hash.

## Sensitive And Raw Voice Restrictions

The sandbox store rejects raw sensitive text and raw voice transcript markers.
Voice-derived or sensitive memories must arrive as approved, edited summaries
from earlier gates.

## Future Production Gates

Production Local Brain writes remain blocked until future gates provide:

- explicit user confirmation
- real backup creation
- rollback verified on real target
- local transaction lock
- audit log
- operator confirmation
- pre/post real Local Brain hash checks

## Relation To Selfhood Runtime

Selfhood Runtime may eventually request this proof path for a reviewed memory
write plan. It must not bypass approval, write real memory, or enable automatic
memory.

## Relation To Local Brain Memory Approval Gate

Only approved manifest-derived write plans are eligible for sandbox proof. This
package does not classify memories or approve them; it only proves transactional
safety after approval and dry-run planning.
