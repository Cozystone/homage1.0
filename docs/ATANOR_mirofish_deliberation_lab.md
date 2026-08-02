# ATANOR MiroFish Deliberation Lab

Status: real multi-step deliberation loop (deliberation_loop.py) grounded in the
consensus-evidence ledger; the single-pass simulator (simulator.py) remains as the
fallback when no ledger is reachable and marks itself loop_used=false.

The loop is structural, not staged: role findings come from live reads of the
evidence ledger (voices, curated quarantine, promoted keys); a blocking objection in
round N triggers a from-disk resolution probe in round N+1 that resolves it with the
observed data cited in the transcript or leaves it standing; the loop stops at a
fixed point or the round cap. Contradictions resolve only by verifying isolation
(no quarantined key ever promoted); privacy and router blocks are human-only.

MiroFish Deliberation Lab models a small review chamber with fixed local roles:
skeptic, builder, domain expert, privacy guard, router, synthesis chair, and
promotion judge. The lab turns a candidate topic, evidence references,
contradictions, privacy report, and router report into a structured transcript,
objections, synthesis, a dry-run promotion recommendation, and a morning brief
candidate.

This is not a real swarm, not real P2P, and not a production promotion path. It
does not use external LLMs, private raw data, production mutation, Local Brain
writes, generated code execution, or cloud upload. Every recommendation remains
review-only and requires explicit human approval before any future production
action.
