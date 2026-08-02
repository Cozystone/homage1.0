# Self-Grown Construction Bank v0

This package extracts reusable answer, inner-voice, and conversation
construction candidates from local, reviewed, or operator-provided material.

It is proof-only in v0:

- no external LLM or sLLM calls;
- no Local Brain write;
- no production `verified_store_v0` mutation;
- no automatic production construction promotion;
- no raw hidden chain-of-thought storage;
- every extracted construction remains a review candidate.

ASM-v0 is still not a general language model. The bank only reduces dependence
on hand-authored construction frames by collecting candidate patterns that can
later be reviewed, scored, and retrieved under explicit gates.
