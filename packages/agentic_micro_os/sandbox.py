from __future__ import annotations

from .capabilities import FORBIDDEN_CAPABILITIES


def reject_forbidden_action(action_type: str) -> bool:
    return action_type in FORBIDDEN_CAPABILITIES or action_type in {"shell_command", "direct_dom_mutation", "unsafe_inner_html"}
