"""ATANOR glossary locks for Korean surface realization."""

from __future__ import annotations


GLOSSARY_LOCKS: dict[str, str] = {
    "Local Brain": "로컬 브레인",
    "Cloud Brain": "클라우드 브레인",
    "Working Memory": "Working Memory",
    "RHFC": "RHFC",
    "CGSR": "CGSR",
    "Surface Brain": "Surface Brain",
    "Q-Cortex": "Q-Cortex",
    "Semantic Graph": "Semantic Graph",
    "Graph Cartridge": "Graph Cartridge",
    "verified_store_v0": "verified_store_v0",
    "false-confident": "false-confident",
    "forgetting": "forgetting",
}


def apply_glossary_locks(text: str) -> str:
    """Apply deterministic glossary replacements without adding claims."""

    value = str(text or "")
    for source, target in GLOSSARY_LOCKS.items():
        value = value.replace(source, target)
    return value


def glossary_violations(korean_text: str) -> list[str]:
    """Return glossary terms that are missing their locked Korean form."""

    value = str(korean_text or "")
    violations = []
    for source, target in GLOSSARY_LOCKS.items():
        if source in value and target not in value:
            violations.append(source)
    return violations
