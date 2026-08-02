# ATANOR unified discourse participation — analysis & plan (2026-07-20)

## The failure, measured
In two live ITT games ATANOR (seat C) repeated ONE canned answer every turn for 8 rounds and never
declared. Root cause, traced end-to-end against the live engine:
- The ITT adapter sends `message = "You are Speaker C. It is your turn… reply"` (a META instruction,
  no substance) and `conversation_context = [topic, transcript]`.
- The engine routes on the meta instruction, finds no grounding, falls to `base_brain`, which does a
  KEYWORD retrieval over the context and returns whatever token it matches — "risk" in the debate →
  the board game *Risk*; a stray "its" → the grammar of the possessive determiner.
- It is deterministic, so the same context yields the same encyclopedia dump every turn.

So ATANOR has **no capability to contribute a turn to an ongoing multi-party discussion**. Its answer
path answers a *question*; a debate turn is not a question, so it degrades to keyword retrieval.

## The owner's correction (and why it is right)
"Do we need a separate multi-turn engine? Turning an engine on only for multi-turn is no different
from rule-based. It should all be unified into one 'model'."

Correct. A `if discussion: run_discussion_engine()` switch is a rule. The fix is that the SINGLE
answer model must always treat available conversation context as real input to content generation —
context-awareness is the default, not a mode. A turn that happens to be part of a debate is just an
answer produced with more context.

## The honest tension we must not paper over
ATANOR is a No-LLM graph engine. Generating a *novel, fluent, other-responsive* debate contribution
is open-ended generation — the exact thing LLMs do and a retrieval/graph engine does not. So "perfect
participation" at LLM level is the fluency wall (Track F), not a quick fix. What is achievable and
honest now: a GROUNDED discourse contribution — take a defensible stance on the topic from graph
knowledge, engage the prior speaker's actual point, vary across turns, and (for a forced-conclusion
dilemma) commit to a verdict with reasons. Not human-level, but a real contribution instead of an
encyclopedia dump, and unified into the one answer path.

## Plan (unified, no mode switch)
1. **Perceive the discourse, always.** When `conversation_context` carries a discussion (a "Topic:"
   line and/or prior "Speaker X:" turns), the engine derives the DISCUSSION SUBJECT and the LAST
   opposing point as first-class inputs — not just routing signals. This runs for every request; it
   simply produces nothing when there is no discussion (so it is not a switch).
2. **One grounded-contribution composer.** Given (subject, my provisional stance, prior point), it
   composes a contribution that (a) states/ö defends a stance grounded in graph facts about the
   subject, (b) explicitly responds to the prior speaker's point, (c) for a forced-conclusion topic,
   commits to a verdict. Reuses the existing grounded composer + opinion_engage; no fabrication.
3. **Vary by responding to the latest turn.** Because input includes the last opposing point, the
   output differs turn to turn — the canned-repeat disappears as a consequence of real context use,
   not a de-dup rule.
4. **Verify live** on the LAWS and dilemma topics: on-topic, varied, grounded, and — the ITT win
   condition — able to weigh the planted "one of you is human" premise and reason about it.

## What this is NOT
- Not a second engine toggled on for ITT (that is the rule the owner rejected).
- Not LLM-level fluency (honestly deferred to Track F); this is grounded participation, hallucination-0.
- Not learned-to-the-judges (ITT stays memoryless/quarantined).
