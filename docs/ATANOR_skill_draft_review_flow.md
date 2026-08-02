# ATANOR Skill Draft Review Flow

Status: proof-only

Agentic Micro-OS can draft reusable skill ideas from public-web source clusters and tool trajectories. A skill draft is not an installed skill.

## Flow

1. Agentic loop creates a `WebSkillDraft`.
2. The draft enters Agentic Review Queue as `skill_draft`.
3. Deterministic scoring checks source references, procedure detail, duplicate overlap, risk, and confidence.
4. A human reviewer may approve as draft, reject, defer, or request more evidence.
5. Approved drafts remain `skill_registry_draft` material only.

## Boundary

The review queue does not install skills, execute generated code, alter repository files, commit, push, or change production behavior.

Any future skill promotion must pass a separate signed manifest gate and operator confirmation. The review queue only makes the draft inspectable.
