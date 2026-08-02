"""Verified Cloud Brain ingestion pipeline.

The ingestion package turns licensed raw text into provenance-carrying
concepts, relations, and case frames for ``verified_store_v0``.  It is a
deterministic pipeline: no external LLM or sLLM calls are used.
"""

from .accumulator import AccumulationResult, VerifiedStore
from .decomposer import DecompositionResult, decompose_sentence
from .source_reader import SourceSentence, make_source_sentences
from .verification_gate import VerificationDecision, verify_sentence

__all__ = [
    "AccumulationResult",
    "DecompositionResult",
    "SourceSentence",
    "VerificationDecision",
    "VerifiedStore",
    "decompose_sentence",
    "make_source_sentences",
    "verify_sentence",
]
