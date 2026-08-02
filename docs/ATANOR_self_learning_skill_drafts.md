# ATANOR Self-Learning Skill Drafts

Status: draft-only skill growth.

In this context, self-learning means ATANOR can create reviewable skill drafts
from public, allowlisted observations. It does not mean malware-like
replication, automatic self-modification, production patching, or unapproved
promotion.

## SkillDraft Shape

`packages/agentic_micro_os/skill_draft.py` defines:

- `skill_id`
- `name`
- `trigger`
- `procedure_steps`
- `required_capabilities`
- `safety_notes`
- `source_refs`
- `status=draft`
- `promotion_required=true`

## Promotion Boundary

The Agentic Micro-OS may draft a skill, but cannot activate it. Promotion must
remain a separate human-reviewed process.

## Required Safety Notes

Every generated web skill draft includes boundaries such as:

- draft only,
- no private credentialed browsing,
- no Local Brain write,
- no production Cloud Brain mutation,
- no auto commit or push.

## Current Use

The Hermes Web Explorer Loop creates a skill draft when at least one public
source is collected. Source references are content hashes, not raw private data.
