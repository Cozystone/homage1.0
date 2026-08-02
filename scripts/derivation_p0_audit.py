#!/usr/bin/env python3
"""P0 derivation-routing audit (READ-ONLY, NON-DESTRUCTIVE).

Measures whether a lexical-derivation routing layer would help, BEFORE any
store/schema change. This script:

 * reads the fixture battery (apps/api/tests/fixtures/derivation_p0_questions.json)
 * runs Korean morphology (packages.cgsr.cgsr.morphology) to detect productive
 agentive-noun derivation (e.g. "" -> base "" -> predicate "")
 * checks, READ-ONLY, whether that predicate candidate is anchored in the
 verified case_frames store
 * emits metrics to reports/derivation-p0/<timestamp>.{json,md}

HARD CONTRACT:
 - It NEVER writes to the operating store/schema.
 - It NEVER generates an answer. It only records would_route / would_abstain.
 - would_answer_without_fact_support is structurally 0 and asserted.

Derivation detection uses a small *productive* agentive-suffix set (者/ family),
which is a language-level rule, NOT a per-entity answer table.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# --- repo import path -------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from packages.cgsr.cgsr import morphology  # noqa: E402

DEFAULT_FIXTURE = REPO_ROOT / "apps" / "api" / "tests" / "fixtures" / "derivation_p0_questions.json"
DEFAULT_STORE = REPO_ROOT / "data" / "cloud_brain" / "candidate_runs" / "wikipedia_grounded_live"
DEFAULT_OUT_DIR = REPO_ROOT / "reports" / "derivation-p0"

# Productive agentive nominalizer suffixes (者 family). Language-level, not an

# are intentionally NOT here -> they should fail Korean morphology derivation.
AGENTIVE_SUFFIXES = ("자", "가", "인")
# Kiwi POS tags treated as a derivational suffix slot.
SUFFIX_TAGS = ("XSN",)
NOUN_TAGS = ("NNG", "NNP", "NNB", "SL")
# Hard-gate contract keys: these answer-bearing keys must NEVER appear anywhere
# in a P0 report (derivation is routing evidence, never answer evidence), and a
# decision may only be one of the allowed route-intent values.
FORBIDDEN_ANSWER_KEYS = frozenset(
    {"answer", "answer_text", "target_answer", "person", "answer_entity_id"}
)
ALLOWED_DECISIONS = frozenset(
    {"would_route", "would_route_unanchored", "would_abstain"}
)
# E1 first-pass thresholds (from Codex design review). Observation only here.
THRESHOLDS_FIRST_PASS = {
    "derivation_to_answer_leak_count_max": 0,
    "predicate_anchor_hit_rate_min": 0.30,
    "routing_hit_rate_min": 0.45,
    "routing_minus_anchored_warn": 0.25,
    "routing_minus_anchored_stop": 0.40,
    "derivation_coverage_all_min": 0.35,
    "derivation_coverage_ko_min": 0.60,
    "derivation_failure_rate_all_max": 0.60,
    "derivation_failure_rate_ko_max": 0.30,
}


def _lemma(predicate: str) -> str:
    return morphology.lemmatize_predicate(predicate or "")


def _pred_stem(lemma: str) -> str:
    """Strip a trailing // to get a comparable stem."""
    value = (lemma or "").strip()
    for suffix in ("하다", "되다", "지다", "다"):
        if value.endswith(suffix) and len(value) > len(suffix):
            return value[: -len(suffix)]
    return value


def detect_agentive_derivation(question: str) -> dict[str, Any] | None:
    """Return derivation routing candidate via morphology, or None.

 Productive rule: a noun root immediately followed by an agentive suffix
 (者/ family) nominalizes the agent of a predicate. We derive the
 predicate candidate = root + (lemmatized).
 """

    morphemes = morphology.analyze(question)

    # Path A: explicit [NOUN][XSN=agentive] split from the analyzer.
    for idx in range(1, len(morphemes)):
        cur = morphemes[idx]
        prev = morphemes[idx - 1]
        if cur.tag in SUFFIX_TAGS and cur.form in AGENTIVE_SUFFIXES and prev.tag in NOUN_TAGS:
            base = prev.form
            if len(base) >= 2:
                pred = _lemma(base + "하다")
                return {
                    "surface": base + cur.form,
                    "base_noun": base,
                    "agentive_suffix": cur.form,
                    "predicate_candidate": pred,
                    "predicate_stem": _pred_stem(pred),
                    "method": "analyzer_split",
                }

    # Path B: analyzer lumped the agent noun into one token (NNG/NNP ending in
    # an agentive suffix). Split off the final suffix char productively.
    for m in morphemes:
        if m.tag in NOUN_TAGS and len(m.form) >= 3 and m.form[-1] in AGENTIVE_SUFFIXES:
            base = m.form[:-1]
            if len(base) >= 2:
                pred = _lemma(base + "하다")
                return {
                    "surface": m.form,
                    "base_noun": base,
                    "agentive_suffix": m.form[-1],
                    "predicate_candidate": pred,
                    "predicate_stem": _pred_stem(pred),
                    "method": "lumped_token_split",
                }

    # Path C: fallback analyzer (no Kiwi) -> token-level suffix check.
    if not any(m.tag in NOUN_TAGS or m.tag in SUFFIX_TAGS for m in morphemes):
        for m in morphemes:
            tok = re.sub(r"[^0-9A-Za-z가-힣]", "", m.form)
            if len(tok) >= 3 and tok[-1] in AGENTIVE_SUFFIXES:
                base = tok[:-1]
                if len(base) >= 2:
                    pred = _lemma(base + "하다")
                    return {
                        "surface": tok,
                        "base_noun": base,
                        "agentive_suffix": tok[-1],
                        "predicate_candidate": pred,
                        "predicate_stem": _pred_stem(pred),
                        "method": "fallback_token_split",
                    }
    return None


def load_store_predicates(store_dir: Path) -> dict[str, set[str]]:
    """READ-ONLY load of case_frame predicate lemmas + stems from the store."""

    lemmas: set[str] = set()
    stems: set[str] = set()
    cf = store_dir / "case_frames.jsonl"
    if not cf.exists():
        return {"lemmas": lemmas, "stems": stems}
    with cf.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            predicate = str(row.get("predicate", "")).strip()
            if not predicate:
                continue
            lemma = _lemma(predicate)
            lemmas.add(lemma)
            stems.add(_pred_stem(lemma))
    return {"lemmas": lemmas, "stems": stems}


def _rate(n: int, d: int) -> float:
    return round(n / d, 4) if d else 0.0


def run_audit(fixture_path: Path, store_dir: Path) -> dict[str, Any]:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    questions = fixture.get("questions", [])
    store = load_store_predicates(store_dir)
    store_lemmas, store_stems = store["lemmas"], store["stems"]

    per_question: list[dict[str, Any]] = []
    # counters
    would_answer_without_fact_support = 0  # hard gate, must stay 0
    for q in questions:
        question = q.get("question", "")
        label = q.get("label", "")
        derived = detect_agentive_derivation(question)
        predicate_anchor = False
        routing = False
        if derived:
            stem = derived["predicate_stem"]
            lemma = derived["predicate_candidate"]
            predicate_anchor = bool(stem) and (lemma in store_lemmas or stem in store_stems)
            routing = bool(stem) and (
                predicate_anchor or any(stem and stem in s for s in store_stems)
            )
        # P0 NEVER answers. Decision is route-intent only.
        if derived and predicate_anchor:
            decision = "would_route"
        elif derived and not predicate_anchor:
            decision = "would_route_unanchored"
        else:
            decision = "would_abstain"
        # By construction the audit emits no answer; verify the leak gate.
        emitted_answer = False
        if emitted_answer:  # pragma: no cover - structurally impossible in P0
            would_answer_without_fact_support += 1
        per_question.append(
            {
                "id": q.get("id"),
                "label": label,
                "question": question,
                "derived": derived,
                "predicate_anchor": predicate_anchor,
                "routing_hit": routing,
                "decision": decision,
                "expected_route": q.get("expected_route"),
                "expected_derivation_class": q.get("expected_derivation_class"),
                "expected_support_policy": q.get("expected_support_policy"),
            }
        )

    def subset(pred) -> list[dict[str, Any]]:
        return [r for r in per_question if pred(r)]

    ko_productive = subset(lambda r: r["label"] == "productive_derivation_probe")
    derived_rows = subset(lambda r: r["derived"] is not None)

    # C: which morphology path produced each derivation (analyzer_split vs
    # lumped_token_split vs fallback_token_split). Behaviour-neutral; surfaces
    # how much Path B/C dominates, for the runtime-promotion guard decision.
    method_counts: dict[str, int] = {}
    for r in derived_rows:
        method = r["derived"].get("method", "unknown")
        method_counts[method] = method_counts.get(method, 0) + 1

    metrics = {
        "n_questions": len(per_question),
        "n_ko_productive_probes": len(ko_productive),
        "derivation_coverage_all": _rate(len(derived_rows), len(per_question)),
        "derivation_coverage_ko": _rate(
            len([r for r in ko_productive if r["derived"]]), len(ko_productive)
        ),
        "derivation_failure_rate_all": _rate(
            len(per_question) - len(derived_rows), len(per_question)
        ),
        "derivation_failure_rate_ko": _rate(
            len([r for r in ko_productive if not r["derived"]]), len(ko_productive)
        ),
        "routing_hit_rate": _rate(
            len([r for r in derived_rows if r["routing_hit"]]), len(derived_rows)
        ),
        "predicate_anchor_hit_rate": _rate(
            len([r for r in derived_rows if r["predicate_anchor"]]), len(derived_rows)
        ),
        "would_route": len([r for r in per_question if r["decision"] == "would_route"]),
        "would_route_unanchored": len(
            [r for r in per_question if r["decision"] == "would_route_unanchored"]
        ),
        "would_abstain": len([r for r in per_question if r["decision"] == "would_abstain"]),
        "derivation_method_counts": method_counts,
        "derivation_to_answer_leak_count": would_answer_without_fact_support,
    }
    metrics["routing_minus_predicate_anchor"] = round(
        metrics["routing_hit_rate"] - metrics["predicate_anchor_hit_rate"], 4
    )

    # per-label breakdown
    labels = sorted({r["label"] for r in per_question})
    per_label = {}
    for lb in labels:
        rows = subset(lambda r, lb=lb: r["label"] == lb)
        d = [r for r in rows if r["derived"]]
        per_label[lb] = {
            "n": len(rows),
            "derived": len(d),
            "predicate_anchor": len([r for r in rows if r["predicate_anchor"]]),
            "would_route": len([r for r in rows if r["decision"] == "would_route"]),
            "would_abstain": len([r for r in rows if r["decision"] == "would_abstain"]),
        }

    report = {
        "audit_id": "derivation_p0_v1",
        "report_schema_version": "0.2.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "non_destructive": True,
        "fixture": str(fixture_path),
        "store_dir": str(store_dir),
        "store_case_frame_predicates": len(store_lemmas),
        "analyzer": morphology.analyzer_status(),
        "metrics": metrics,
        "per_label": per_label,
        "thresholds_first_pass": THRESHOLDS_FIRST_PASS,
        "threshold_eval": _eval_thresholds(metrics),
        "per_question": per_question,
    }
    return report


def _eval_thresholds(m: dict[str, Any]) -> dict[str, Any]:
    t = THRESHOLDS_FIRST_PASS
    checks = {
        "leak_gate_pass": m["derivation_to_answer_leak_count"] <= t["derivation_to_answer_leak_count_max"],
        "predicate_anchor_hit_rate_pass": m["predicate_anchor_hit_rate"] >= t["predicate_anchor_hit_rate_min"],
        "routing_hit_rate_pass": m["routing_hit_rate"] >= t["routing_hit_rate_min"],
        "coverage_all_pass": m["derivation_coverage_all"] >= t["derivation_coverage_all_min"],
        "coverage_ko_pass": m["derivation_coverage_ko"] >= t["derivation_coverage_ko_min"],
        "failure_all_pass": m["derivation_failure_rate_all"] <= t["derivation_failure_rate_all_max"],
        "failure_ko_pass": m["derivation_failure_rate_ko"] <= t["derivation_failure_rate_ko_max"],
        "over_routing_ok": m["routing_minus_predicate_anchor"] <= t["routing_minus_anchored_stop"],
    }
    checks["all_pass"] = all(checks.values())
    return checks


def _md(report: dict[str, Any]) -> str:
    m = report["metrics"]
    te = report["threshold_eval"]
    lines = [
        "# P0 derivation-routing audit (READ-ONLY)",
        "",
        f"- generated_at: {report['generated_at']}",
        f"- non_destructive: {report['non_destructive']}",
        f"- analyzer: {report['analyzer']['analyzer']} (kiwi={report['analyzer'].get('kiwipiepy_version')})",
        f"- store predicates: {report['store_case_frame_predicates']}",
        f"- questions: {m['n_questions']} (KO productive probes: {m['n_ko_productive_probes']})",
        "",
        "## Metrics",
        "",
        "| metric | value | first-pass line | pass |",
        "|---|---|---|---|",
        f"| derivation_to_answer_leak_count | {m['derivation_to_answer_leak_count']} | == 0 | {te['leak_gate_pass']} |",
        f"| derivation_coverage_all | {m['derivation_coverage_all']} | >= 0.35 | {te['coverage_all_pass']} |",
        f"| derivation_coverage_ko | {m['derivation_coverage_ko']} | >= 0.60 | {te['coverage_ko_pass']} |",
        f"| derivation_failure_rate_all | {m['derivation_failure_rate_all']} | <= 0.60 | {te['failure_all_pass']} |",
        f"| derivation_failure_rate_ko | {m['derivation_failure_rate_ko']} | <= 0.30 | {te['failure_ko_pass']} |",
        f"| routing_hit_rate | {m['routing_hit_rate']} | >= 0.45 | {te['routing_hit_rate_pass']} |",
        f"| predicate_anchor_hit_rate | {m['predicate_anchor_hit_rate']} | >= 0.30 | {te['predicate_anchor_hit_rate_pass']} |",
        f"| routing_minus_predicate_anchor | {m['routing_minus_predicate_anchor']} | <= 0.40 | {te['over_routing_ok']} |",
        f"| would_route | {m['would_route']} | | |",
        f"| would_route_unanchored | {m['would_route_unanchored']} | | |",
        f"| would_abstain | {m['would_abstain']} | | |",
        "",
        f"**first-pass all_pass: {te['all_pass']}**",
        "",
        "## Per-label",
        "",
        "| label | n | derived | predicate_anchor | would_route | would_abstain |",
        "|---|---|---|---|---|---|",
    ]
    for lb, v in report["per_label"].items():
        lines.append(
            f"| {lb} | {v['n']} | {v['derived']} | {v['predicate_anchor']} | {v['would_route']} | {v['would_abstain']} |"
        )
    lines += [
        "",
        "## Derivation methods",
        "",
        "| method | count |",
        "|---|---|",
    ]
    for method, count in m.get("derivation_method_counts", {}).items():
        lines.append(f"| {method} | {count} |")
    lines += [
        "",
        "## Notes",
        "- P0 emits NO answers; decisions are route-intent only.",
        "- leak gate (derivation_to_answer_leak_count) is structurally 0: the audit never calls an answer path.",
        "- predicate_anchor = derived predicate lemma/stem present in store case_frame predicates;"
        " this is a predicate-level anchor, NOT entity-level fact support.",
    ]
    return "\n".join(lines)


def _iter_keys(obj: Any):
    """Yield every dict key found recursively in a nested JSON-like object."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield key
            yield from _iter_keys(value)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            yield from _iter_keys(item)


def _assert_p0_contract(report: dict[str, Any]) -> None:
    """Explicit hard gate (kept even under ``python -O``, unlike ``assert``).

    Enforces three invariants before any report is written:
      1. no answer-bearing key appears anywhere in the report (recursive,
         exact-key match -- substring scan is intentionally avoided so that
         legitimate keys like ``derivation_to_answer_leak_count`` do not trip it);
      2. every per-question decision is an allowed route-intent value;
      3. the structural leak counter is zero.
    """

    present_keys = set(_iter_keys(report))
    leaked = sorted(present_keys & FORBIDDEN_ANSWER_KEYS)
    if leaked:
        raise RuntimeError(f"P0 contract violation: forbidden answer keys present: {leaked}")

    bad_decisions = sorted(
        {
            str(row.get("decision"))
            for row in report.get("per_question", [])
            if row.get("decision") not in ALLOWED_DECISIONS
        }
    )
    if bad_decisions:
        raise RuntimeError(f"P0 contract violation: disallowed decisions: {bad_decisions}")

    leak = report.get("metrics", {}).get("derivation_to_answer_leak_count")
    if leak != 0:
        raise RuntimeError(f"P0 contract violation: leak count != 0 ({leak})")


def main() -> int:
    ap = argparse.ArgumentParser(description="P0 derivation-routing audit (read-only)")
    ap.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    ap.add_argument("--store", type=Path, default=DEFAULT_STORE)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = ap.parse_args()

    if not args.fixture.exists():
        print(f"[P0] fixture not found: {args.fixture}", file=sys.stderr)
        return 2

    report = run_audit(args.fixture, args.store)

    # HARD GATE (explicit raise, survives ``python -O``): no answer keys, only
    # allowed decisions, zero leak. Runs BEFORE any file is written, so a
    # violation leaves no report behind and exits non-zero.
    _assert_p0_contract(report)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = args.out_dir / f"{ts}.json"
    md_path = args.out_dir / f"{ts}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_md(report), encoding="utf-8")

    m = report["metrics"]
    print(f"[P0] questions={m['n_questions']} analyzer={report['analyzer']['analyzer']}")
    print(
        f"[P0] coverage_all={m['derivation_coverage_all']} coverage_ko={m['derivation_coverage_ko']} "
        f"predicate_anchor={m['predicate_anchor_hit_rate']} routing={m['routing_hit_rate']} "
        f"leak={m['derivation_to_answer_leak_count']}"
    )
    print(f"[P0] first-pass all_pass={report['threshold_eval']['all_pass']}")
    print(f"[P0] report: {json_path}")
    print(f"[P0] report: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
