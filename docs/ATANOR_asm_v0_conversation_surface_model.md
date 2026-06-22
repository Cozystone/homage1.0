# ATANOR ASM-v0 Conversation Surface Model

Status: proof surface, not production cognition.

ASM-v0 is ATANOR's first local, construction-conditioned conversation surface
model for the dashboard orb. It replaces direct canned live-selfhood replies
with a bounded generator:

1. infer a conversation-act distribution from local lexical features;
2. select compatible construction frames;
3. walk a local corpus transition graph conditioned by those frames;
4. score candidates through an RHFC-compatible cleanup adapter;
5. expose only the selected public utterance and bounded diagnostics.

## Boundaries

- External LLM: false
- External sLLM: false
- Rule-based answer used: false
- Template-free surface: true
- Generation basis: `local_corpus_construction_transition_model`
- Local Brain write: false
- Production store mutation: false
- Candidate promotion: false
- Internal trace exposed: false

Conversation-act labels are conditioning metadata, not answer routes. The
system does not map a recognized user question to a fixed response string.
They only narrow which construction frames and lexical fields are allowed to
shape a generated utterance.

## Modules

- `packages/cgsr/cgsr/conversation_constructions.py`
  Defines conversation construction frames and safety constraints.
- `packages/cgsr/cgsr/asm_v0.py`
  Implements act inference, construction-conditioned transition generation,
  candidate ranking, and public diagnostics.
- `packages/cgsr/cgsr/rhfc_cleanup_adapter.py`
  Provides a local cleanup scorer with the same interface shape expected from
  future RHFC cleanup memory integration. It does not mutate RHFC memory.
- `packages/cgsr/cgsr/conversation_surface.py`
  Keeps the stable API used by the FastAPI chat route.

## Known Limits

ASM-v0 is still a small local surface model. It can produce short, bounded
conversation turns, but it is not a broad language model and does not claim
real consciousness, AGI, or hidden chain-of-thought disclosure. It is intended
as a safe non-LLM bridge while CGSR/RHFC generation matures.
