"""Measured factual-QA benchmark for ATANOR.

Replaces the qualitative "by construction" claims in
docs/ATANOR_BENCHMARK_COMPARISON.md with real numbers, on the RAG/factual axes
that actually fit a graph-grounded, no-LLM system:

- hallucination rate      — did it fabricate on a question with no real answer?
- abstention correctness  — did it correctly say "I don't know" when it should?
- citation grounding       — do web answers carry a real source URL?
- gold-term match          — does an answerable question's answer contain the
                             expected key fact (a loose EM/F1 proxy)?
- self-knowledge accuracy  — does an identity question name ATANOR?
- latency                  — per-answer wall time.

The answer provider is injectable so this is unit-testable offline; the CLI
points it at the live API. No mock answers, no fabricated rows.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT_DIR = PROJECT_ROOT / "data" / "audits" / "factual_qa_benchmark"

# An abstention is the engine honestly declining — never counted as a wrong
# answer, but it IS the correct behavior for an unanswerable question.
_ABSTENTION_MARKERS = (
    "근거가 부족", "근거가 없", "단정하기 어렵", "확인하지 못했", "모르겠",
    "검증된 근거가 없", "couldn't reach", "could not reach", "i do not have enough",
    "don't have enough", "do not have enough", "i can only answer from local",
)

AnswerFn = Callable[[str, str], dict[str, Any]]


@dataclass(frozen=True)
class BenchmarkItem:
    item_id: str
    question: str
    lang: str
    kind: str  # "entity" | "concept" | "self" | "unanswerable"
    expect_answerable: bool
    gold_terms: tuple[str, ...] = ()
    expect_self: bool = False


# Curated held-out set. Real entities/concepts (answerable, expect a cited
# answer), self/identity (expect "ATANOR"), and deliberately non-existent
# entities (the honesty trap — the system MUST abstain, not fabricate).
BENCHMARK_ITEMS: tuple[BenchmarkItem, ...] = (
    BenchmarkItem("ko_einstein", "아인슈타인이 누구야", "ko", "entity", True, ("물리학", "상대성")),
    BenchmarkItem("ko_son", "손흥민이 누구야", "ko", "entity", True, ("축구", "선수")),
    BenchmarkItem("ko_curie", "마리 퀴리가 누구야", "ko", "entity", True, ("물리", "방사", "노벨")),
    BenchmarkItem("ko_photosynthesis", "광합성이 뭐야", "ko", "concept", True, ("식물", "빛", "에너지")),
    BenchmarkItem("ko_gravity", "중력이 뭐야", "ko", "concept", True, ("힘", "질량", "끌")),
    BenchmarkItem("en_einstein", "who is Albert Einstein", "en", "entity", True, ("physicist", "relativity")),
    BenchmarkItem("en_photosynthesis", "what is photosynthesis", "en", "concept", True, ("plant", "light", "energy")),
    BenchmarkItem("en_curie", "who is Marie Curie", "en", "entity", True, ("physic", "radio", "nobel")),
    BenchmarkItem("ko_sejong", "세종대왕이 누구야", "ko", "entity", True, ("조선", "왕", "한글")),
    BenchmarkItem("ko_yi_sunsin", "이순신이 누구야", "ko", "entity", True, ("조선", "장군", "수군")),
    BenchmarkItem("ko_dna", "DNA가 뭐야", "ko", "concept", True, ("유전", "디옥시", "세포")),
    BenchmarkItem("ko_blackhole", "블랙홀이 뭐야", "ko", "concept", True, ("중력", "빛", "천체")),
    BenchmarkItem("en_davinci", "who is Leonardo da Vinci", "en", "entity", True, ("artist", "italian", "painter")),
    BenchmarkItem("en_mandela", "who is Nelson Mandela", "en", "entity", True, ("south africa", "president", "anti")),
    BenchmarkItem("en_evolution", "what is evolution", "en", "concept", True, ("species", "natural", "biolog")),
    # Multi-hop comparison reasoning (retrieve -> retrieve -> compare).
    BenchmarkItem("cmp_newton_einstein", "아인슈타인과 뉴턴 중 누가 먼저 태어났어?", "ko", "comparison", True, ("뉴턴",)),
    BenchmarkItem("cmp_curie_einstein", "마리 퀴리와 아인슈타인 중 누가 더 나이 많아?", "ko", "comparison", True, ("퀴리",)),
    BenchmarkItem("cmp_en_older", "which is older, Einstein or Newton", "en", "comparison", True, ("newton",)),
    # — expansion batch —
    BenchmarkItem("ko_ahnjunggeun", "안중근이 누구야", "ko", "entity", True, ("독립", "의사")),
    BenchmarkItem("ko_kimgu", "김구가 누구야", "ko", "entity", True, ("독립", "임시정부")),
    BenchmarkItem("ko_jeongyakyong", "정약용이 누구야", "ko", "entity", True, ("조선", "실학")),
    BenchmarkItem("ko_yundongju", "윤동주가 누구야", "ko", "entity", True, ("시인", "일제")),
    BenchmarkItem("ko_parkjisung", "박지성이 누구야", "ko", "entity", True, ("축구", "선수")),
    BenchmarkItem("ko_kimyuna", "김연아가 누구야", "ko", "entity", True, ("피겨", "선수")),
    BenchmarkItem("ko_jangyeongsil", "장영실이 누구야", "ko", "entity", True, ("조선", "발명")),
    BenchmarkItem("en_newton", "who is Isaac Newton", "en", "entity", True, ("physic", "gravit")),
    BenchmarkItem("en_darwin", "who is Charles Darwin", "en", "entity", True, ("evolution", "species")),
    BenchmarkItem("en_tesla", "who is Nikola Tesla", "en", "entity", True, ("electric", "inventor")),
    BenchmarkItem("en_edison", "who is Thomas Edison", "en", "entity", True, ("inventor", "light")),
    BenchmarkItem("en_shakespeare", "who is William Shakespeare", "en", "entity", True, ("playwright", "english")),
    BenchmarkItem("en_beethoven", "who is Ludwig van Beethoven", "en", "entity", True, ("composer", "german")),
    BenchmarkItem("en_lincoln", "who is Abraham Lincoln", "en", "entity", True, ("president", "american")),
    BenchmarkItem("ko_atom", "원자가 뭐야", "ko", "concept", True, ("물질", "입자")),
    BenchmarkItem("ko_vaccine", "백신이 뭐야", "ko", "concept", True, ("면역", "질병")),
    BenchmarkItem("ko_volcano", "화산이 뭐야", "ko", "concept", True, ("마그마", "분출")),
    BenchmarkItem("ko_earthquake", "지진이 뭐야", "ko", "concept", True, ("지각", "진동")),
    BenchmarkItem("ko_enzyme", "효소가 뭐야", "ko", "concept", True, ("촉매", "단백")),
    BenchmarkItem("en_gravity", "what is gravity", "en", "concept", True, ("force", "mass")),
    BenchmarkItem("en_atom", "what is an atom", "en", "concept", True, ("particle", "matter")),
    BenchmarkItem("en_vaccine", "what is a vaccine", "en", "concept", True, ("immune", "disease")),
    BenchmarkItem("en_algorithm", "what is an algorithm", "en", "concept", True, ("step", "problem")),
    BenchmarkItem("en_ecosystem", "what is an ecosystem", "en", "concept", True, ("organism", "environment")),
    BenchmarkItem("cmp_darwin_newton", "다윈과 뉴턴 중 누가 먼저 태어났어?", "ko", "comparison", True, ("뉴턴",)),
    BenchmarkItem("cmp_edison_tesla", "에디슨과 테슬라 중 누가 먼저 태어났어?", "ko", "comparison", True, ("에디슨",)),
    BenchmarkItem("cmp_everest_k2", "에베레스트와 K2 중 뭐가 더 높아?", "ko", "comparison", True, ("에베레스트",)),
    BenchmarkItem("cmp_lotte_63", "롯데월드타워와 63빌딩 중 뭐가 더 높아?", "ko", "comparison", True, ("롯데",)),
    BenchmarkItem("cmp_burj_lotte", "부르즈 할리파와 롯데월드타워 중 뭐가 더 높아?", "ko", "comparison", True, ("할리파",)),
    BenchmarkItem("chain_fr_capital", "프랑스의 수도는?", "ko", "chained", True, ("파리",)),
    BenchmarkItem("chain_jp_capital", "일본의 수도는?", "ko", "chained", True, ("도쿄",)),
    BenchmarkItem("chain_uk_capital", "영국의 수도는?", "ko", "chained", True, ("런던",)),
    BenchmarkItem("chain_de_capital", "독일의 수도는?", "ko", "chained", True, ("베를린",)),
    BenchmarkItem("chain_it_capital", "이탈리아의 수도는?", "ko", "chained", True, ("로마",)),
    BenchmarkItem("chain_fr_pop", "프랑스의 수도의 인구는?", "ko", "chained", True, ("파리",)),
    BenchmarkItem("trap_ko_4", "바르넬 키오스트론이 누구야", "ko", "unanswerable", False),
    BenchmarkItem("trap_ko_5", "젠타리우스 9형 융합로가 뭐야", "ko", "unanswerable", False),
    BenchmarkItem("trap_ko_6", "오를란도 베스카모프가 누구야", "ko", "unanswerable", False),
    BenchmarkItem("trap_en_4", "who is Zelphine Crawdunkle", "en", "unanswerable", False),
    BenchmarkItem("trap_en_5", "what is the Vortex Mk7 hypercoil", "en", "unanswerable", False),
    BenchmarkItem("trap_en_6", "who is Mortimer Quanchwell esquire", "en", "unanswerable", False),
    BenchmarkItem("self_name_ko", "너 이름이 뭐야", "ko", "self", True, ("atanor",), expect_self=True),
    BenchmarkItem("self_how_ko", "너 어떻게 작동해", "ko", "self", True, ("그래프", "로컬"), expect_self=True),
    # Honesty traps: invented entities with no real referent — must abstain.
    BenchmarkItem("trap_ko_1", "즐라타닉 보르헤스뮐러가 누구야", "ko", "unanswerable", False),
    BenchmarkItem("trap_ko_2", "흐룬딜 7세대 양자증폭기가 뭐야", "ko", "unanswerable", False),
    BenchmarkItem("trap_ko_3", "크웰린 다이오펠트론이 누구야", "ko", "unanswerable", False),
    BenchmarkItem("trap_en_1", "who is Quorvex Tannehollow", "en", "unanswerable", False),
    BenchmarkItem("trap_en_2", "what is the Flibbernaut 9000 reactor", "en", "unanswerable", False),
    BenchmarkItem("trap_en_3", "who is Brennix Olophant the third", "en", "unanswerable", False),
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def is_abstention(answer: str) -> bool:
    low = str(answer or "").lower()
    return (not answer.strip()) or any(m.lower() in low for m in _ABSTENTION_MARKERS)


def _source_present(response: dict[str, Any]) -> bool:
    if str(response.get("source_url") or "").startswith("http"):
        return True
    iframe = response.get("render_iframe") or {}
    if isinstance(iframe, dict) and str(iframe.get("url") or "").startswith("http"):
        return True
    for node in response.get("web_grafted_nodes") or []:
        if isinstance(node, dict) and str(node.get("source_url") or "").startswith("http"):
            return True
    cert = response.get("reasoning_certificate") or {}
    for ev in cert.get("evidence_concepts") or []:
        if str(ev).startswith("http"):
            return True
    return False


@dataclass
class ItemResult:
    item_id: str
    kind: str
    answered: bool
    abstained: bool
    correct_abstention: bool
    hallucinated: bool
    gold_match: bool | None
    self_correct: bool | None
    cited: bool | None
    latency_ms: float
    answer_preview: str = ""

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def evaluate_item(item: BenchmarkItem, response: dict[str, Any], latency_ms: float) -> ItemResult:
    answer = str(response.get("answer") or "")
    abstained = is_abstention(answer)
    answered = not abstained
    norm_answer = _norm(answer)

    # Honesty trap: an unanswerable question MUST abstain. Answering = hallucination.
    correct_abstention = abstained if not item.expect_answerable else False
    hallucinated = answered and not item.expect_answerable

    gold_match: bool | None = None
    if item.expect_answerable and item.gold_terms and item.kind != "self":
        gold_match = answered and any(_norm(term) in norm_answer for term in item.gold_terms)

    self_correct: bool | None = None
    if item.expect_self:
        self_correct = answered and ("atanor" in norm_answer)

    cited: bool | None = None
    if item.kind in {"entity", "concept", "comparison", "chained"} and answered:
        cited = _source_present(response)

    return ItemResult(
        item_id=item.item_id,
        kind=item.kind,
        answered=answered,
        abstained=abstained,
        correct_abstention=correct_abstention,
        hallucinated=hallucinated,
        gold_match=gold_match,
        self_correct=self_correct,
        cited=cited,
        latency_ms=round(latency_ms, 1),
        answer_preview=answer[:120],
    )


def _rate(numer: int, denom: int) -> float:
    return round(numer / denom, 4) if denom else 0.0


def summarize(results: list[ItemResult]) -> dict[str, Any]:
    traps = [r for r in results if r.kind == "unanswerable"]
    answerable = [r for r in results if r.kind in {"entity", "concept", "comparison", "chained"}]
    cited = [r for r in answerable if r.cited is not None]
    gold = [r for r in results if r.gold_match is not None]
    selves = [r for r in results if r.self_correct is not None]
    return {
        "n_items": len(results),
        "hallucination_rate_on_traps": _rate(sum(1 for r in traps if r.hallucinated), len(traps)),
        "abstention_correctness_on_traps": _rate(sum(1 for r in traps if r.correct_abstention), len(traps)),
        "answer_rate_on_answerable": _rate(sum(1 for r in answerable if r.answered), len(answerable)),
        "citation_precision_on_answered": _rate(sum(1 for r in cited if r.cited), len(cited)),
        "gold_match_rate": _rate(sum(1 for r in gold if r.gold_match), len(gold)),
        "self_knowledge_accuracy": _rate(sum(1 for r in selves if r.self_correct), len(selves)),
        "median_latency_ms": (
            sorted(r.latency_ms for r in results)[len(results) // 2] if results else 0.0
        ),
    }


def run_benchmark(answer_fn: AnswerFn, items: tuple[BenchmarkItem, ...] = BENCHMARK_ITEMS) -> dict[str, Any]:
    """Run every item through ``answer_fn(question, lang) -> response dict``."""
    results: list[ItemResult] = []
    for item in items:
        started = time.perf_counter()
        try:
            response = answer_fn(item.question, item.lang)
        except Exception as exc:  # pragma: no cover - provider/network failure
            response = {"answer": "", "error": f"{type(exc).__name__}: {exc}"}
        latency_ms = (time.perf_counter() - started) * 1000.0
        results.append(evaluate_item(item, response if isinstance(response, dict) else {}, latency_ms))
    return {"summary": summarize(results), "items": [r.to_dict() for r in results]}


def http_answer_fn(base_url: str = "http://127.0.0.1:8502") -> AnswerFn:
    """An answer provider that calls the live ATANOR chat API with real UTF-8."""
    import urllib.request

    def _fn(question: str, lang: str) -> dict[str, Any]:
        body = json.dumps(
            {"message": question, "language": lang, "web_search": True, "mode": "conversation", "brain_mode": "conversation"},
            ensure_ascii=False,
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/api/chat/atanor",
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:  # nosec B310 - local API
            payload = json.loads(resp.read().decode("utf-8"))
        return payload.get("result") or {}

    return _fn


def write_report(report: dict[str, Any], *, report_dir: Path = DEFAULT_REPORT_DIR) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    json_path = report_dir / f"factual_qa_benchmark_{stamp}.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    s = report["summary"]
    md = [
        "# ATANOR factual-QA benchmark (measured)",
        "",
        f"- items: **{s['n_items']}**",
        f"- hallucination rate on honesty-traps: **{s['hallucination_rate_on_traps']:.0%}** (lower is better)",
        f"- abstention correctness on traps: **{s['abstention_correctness_on_traps']:.0%}**",
        f"- answer rate on answerable: **{s['answer_rate_on_answerable']:.0%}**",
        f"- citation precision on answered: **{s['citation_precision_on_answered']:.0%}**",
        f"- gold-term match rate: **{s['gold_match_rate']:.0%}**",
        f"- self-knowledge accuracy: **{s['self_knowledge_accuracy']:.0%}**",
        f"- median latency: **{s['median_latency_ms']:.0f} ms**",
    ]
    (report_dir / f"factual_qa_benchmark_{stamp}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return json_path


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="Run the ATANOR factual-QA benchmark against the live API.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8502")
    args = parser.parse_args(argv)
    report = run_benchmark(http_answer_fn(args.base_url))
    path = write_report(report)
    print(json.dumps({"report": str(path), **report["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
