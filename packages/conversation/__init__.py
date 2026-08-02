# -*- coding: utf-8 -*-
"""conversation — the engagement layer that makes ATANOR TALK, not just answer.

An ATANOR citizen grounds honest answers (mechanism reasoning, perceived place/activity, graph facts,
its own felt state) but voices them tersely, so an honest abstention reads as incompetence. This
package composes those grounded sub-answers into warm, in-character, multi-sentence turns — acknowledge
-> grounded content -> an offer/question back — WITHOUT fabricating: every content word traces to the
grounding or a closed conversational vocabulary (verify_grounded proves it), and anything ungrounded
falls back to the terse answer. Kill-switch ATANOR_ENGAGE=0 restores the terse behaviour byte-for-byte.
"""
from packages.conversation.engage import (
    CONVERSATIONAL_VOCAB,
    GroundedReply,
    Register,
    REGISTERS,
    compose_engagement,
    mechanism_certificate,
    verify_grounded,
)

__all__ = [
    "CONVERSATIONAL_VOCAB",
    "GroundedReply",
    "Register",
    "REGISTERS",
    "compose_engagement",
    "mechanism_certificate",
    "verify_grounded",
]
