# ATANOR User-facing vs Internal Surfaces

Status: UI separation policy.

Users should experience ATANOR as a proactive assistant that briefs, suggests, and asks for approval. They should not need to inspect heartbeat, spark metrics, scheduler ticks, or proof invariants unless they enter Lab/Developer mode.

## Normal User-facing UI

- main chat and text input
- optional voice controls
- ATANOR Status
- Morning Brief, Evening Brief, and status summaries
- current suggestions
- pending approvals
- simple settings
- simple safety copy: no memory or knowledge is changed without approval

## Advanced / Operator UI

- memory approval details
- promotion review details
- candidate review
- operator confirmation
- Local Brain write dry-run preview
- simplified graph and ontology inspection

These views can be exposed behind an Advanced or Lab mode. They should not look like ordinary consumer product tabs.

## Lab / Developer UI

- Life Signs Monitor
- Live Scheduler internals
- Spark metrics
- Freedom Budget
- raw heartbeat and tick views
- proof package status
- release mock audit output
- raw safety invariant booleans
- source hashes, internal node IDs, and store IDs
- daemon and stop-marker controls
- debug and proof panels

These tools remain valuable for development and safety verification, but they are not normal user-facing product features.

## Why Life Signs Is Lab-only

Life Signs is an observability layer for ATANOR's functional selfhood loop. It reports heartbeat, rhythm, wake reason, spark, proposals, briefs, approvals, and safety blocks. It does not prove real consciousness or AGI, and it should not be framed as something ordinary users must inspect.

## What Users See Instead

The product surface should use `ATANOR Status` copy:

- Ready
- Thinking
- Resting
- Waiting for your approval

It should summarize proposals and approvals in natural language:

- "Review prepared proposals before anything changes."
- "No memory or knowledge is changed without your approval."

Text input remains primary. Voice remains optional. Safety gates remain active even when their raw invariant tables are hidden from normal navigation.
