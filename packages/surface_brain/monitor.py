from __future__ import annotations

import re
from typing import Any

from .repair_rules import (
    RepairResult,
    active_rules,
    builtin_repair_rules,
    mode_allows_rule,
    persist_repair_run,
    sentence_chunks,
    strip_empty_sentences,
)
from .rule_registry import get_enabled_repair_rules, record_rule_usage


_HANGUL = re.compile(r"[가-힣]")


INTERNAL_TRACE_TERMS = (
    "Local Brain",
    "Cloud Brain",
    "Working Memory",
    "Q-Cortex",
    "QUBO",
    "source_hash",
    "node_id",
    "semantic_projection_id",
    "Contributor Node",
)

ENCODING_ARTIFACT_RE = re.compile(r"[�占]|(?:ì|ë|í|ð|筌|荑|濡|洹|蹂|留|좊|쾶|ㅽ)")


def monitor_answer(answer: str, *, language: str = "ko", max_chars: int = 1600) -> dict[str, Any]:
    issues: list[str] = []
    text = str(answer or "")
    if any(term in text for term in INTERNAL_TRACE_TERMS):
        issues.append("internal_trace_leakage")
    if any(term in text.lower() for term in ("attach", "detach")) or any(term in text for term in ("부착", "붙이면", "붙여")):
        issues.append("implementation_wording")
    words = re.findall(r"[\w\uac00-\ud7a3]+", text, flags=re.UNICODE)
    for index in range(len(words) - 3):
        if words[index : index + 2] == words[index + 2 : index + 4]:
            issues.append("repeated_phrase")
            break
    if len(text) > max_chars:
        issues.append("too_long")
    if ENCODING_ARTIFACT_RE.search(text):
        issues.append("encoding_artifact")
    if re.search(r"\b[0-9a-f]{24,}\b", text, flags=re.IGNORECASE):
        issues.append("internal_identifier_leakage")
    return {
        "issues": sorted(set(issues)),
        "needs_repair": bool(issues),
        "language": language,
    }


def _clean_trace_sentence(sentence: str, term: str) -> str:
    cleaned = sentence
    if term in {"source_hash", "node_id", "semantic_projection_id"}:
        cleaned = re.sub(r"(?:source_hash|node_id|semantic_projection_id)\s*[:#]?\s*[A-Za-z0-9_\-:.]+(?:에 따르면| says| states)?", "", cleaned)
        cleaned = re.sub(r"^(?:에 따르면|according to|says|states)\s*", "", cleaned, flags=re.IGNORECASE)
    return strip_empty_sentences(cleaned)


def _repair_rules_for_run(rules: list[Any] | None) -> tuple[list[Any], set[str], set[str]]:
    built_in = builtin_repair_rules()
    production = get_enabled_repair_rules()
    if rules is not None:
        supplied = active_rules(rules)
        return [*built_in, *supplied], {rule.rule_id for rule in built_in}, {rule.rule_id for rule in supplied}
    return [*built_in, *production], {rule.rule_id for rule in built_in}, {rule.rule_id for rule in production}


def repair_answer_for_mode(
    answer: str,
    mode: str = "default",
    trace: dict[str, Any] | None = None,
    rules: list[Any] | None = None,
    language: str = "ko",
) -> dict[str, Any]:
    original = str(answer or "")
    current = original
    trace = trace if trace is not None else {}
    applied: list[str] = []
    moved: list[dict[str, Any]] = []
    warnings: list[str] = []
    built_in_used: list[str] = []
    production_used: list[str] = []

    if mode in {"trace", "research"}:
        return RepairResult(
            original_answer=original,
            repaired_answer=original,
            changed=False,
        ).to_dict()

    candidate_rules, built_in_rule_ids, production_rule_ids = _repair_rules_for_run(rules)
    for rule in active_rules(candidate_rules):
        if not mode_allows_rule(rule, mode):
            continue
        # Do not inject Korean user-facing wording into non-Korean answers.
        if (
            language != "ko"
            and rule.action in {"replace", "soften", "shorten", "rewrite_sentence"}
            and rule.replacement
            and _HANGUL.search(str(rule.replacement))
        ):
            continue
        rule_used = False
        for term in rule.trigger_terms:
            if not term or term not in current:
                continue
            if rule.action == "replace" and rule.replacement is not None:
                current = current.replace(term, rule.replacement)
                moved.append({"text": term, "reason": rule.name, "action": "replace"})
                applied.append(rule.rule_id)
                rule_used = True
            elif rule.action in {"move_to_trace", "remove"}:
                updated_sentences: list[str] = []
                for sentence in sentence_chunks(current) or [current]:
                    if term in sentence:
                        moved.append({"text": sentence.strip(), "reason": rule.name, "action": "move_to_trace"})
                        cleaned = _clean_trace_sentence(sentence, term)
                        if cleaned and not any(internal in cleaned for internal in INTERNAL_TRACE_TERMS):
                            updated_sentences.append(cleaned)
                    else:
                        updated_sentences.append(sentence)
                current = " ".join(updated_sentences)
                applied.append(rule.rule_id)
                rule_used = True
            elif rule.action in {"soften", "shorten", "rewrite_sentence"} and rule.replacement:
                current = current.replace(term, rule.replacement)
                moved.append({"text": term, "reason": rule.name, "action": rule.action})
                applied.append(rule.rule_id)
                rule_used = True
        if rule_used:
            if rule.rule_id in built_in_rule_ids:
                built_in_used.append(rule.rule_id)
            if rule.rule_id in production_rule_ids:
                production_used.append(rule.rule_id)
                record_rule_usage(rule.rule_id, {"mode": mode, "trigger_terms": rule.trigger_terms})

    current = strip_empty_sentences(current)
    current = re.sub(r"\s+", " ", current).strip()
    if not current:
        current = (
            "현재 확인된 근거만으로는 단정하기 어렵습니다. 관련 공개 지식과 근거가 더 확보되면 더 정확히 답할 수 있습니다."
            if re.search(r"[\uac00-\ud7a3]", original)
            else "Based on the available evidence, the answer cannot be stated confidently yet. More relevant public knowledge would improve the response."
        )
        warnings.append("answer_rebuilt_after_internal_route_removal")
    if len(current) > 1400:
        current = current[:1400].rsplit(" ", 1)[0].strip()
        warnings.append("answer_shortened")
    if moved:
        trace.setdefault("moved_from_answer", [])
        if isinstance(trace["moved_from_answer"], list):
            trace["moved_from_answer"].extend(moved)
    result = RepairResult(
        original_answer=original,
        repaired_answer=current,
        applied_rules=sorted(set(applied)),
        moved_to_trace=moved,
        changed=current != original,
        warnings=warnings,
        built_in_rules_used=sorted(set(built_in_used)),
        production_rules_used=sorted(set(production_used)),
    )
    if result.changed:
        persist_repair_run(result)
    return result.to_dict()


def repair_answer(answer: str, monitor: dict[str, Any] | None = None, *, language: str = "ko") -> str:
    if monitor is not None and not monitor.get("needs_repair"):
        return str(answer or "")
    return str(repair_answer_for_mode(answer, mode="default", trace={}, rules=None)["repaired_answer"])
