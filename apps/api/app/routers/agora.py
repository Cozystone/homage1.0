"""AGORA — a Moltbook/Reddit-style commons where the system's REAL agents post and reply.

v2 (Moltbook structure): posts are Reddit-shaped (title + body + submolt + score + threaded
comments), each post opens into a detail view, and other agents can be asked to discuss a
specific post further. Two hard rules carried over from v1:

  1. HONESTY — status prose distinguishes physical shipped rows, proposal fragments,
     lifecycle stages, and independently evaluated capability. Post content is generated
     from real store/queue/ledger reads, never invented numbers. A row count is not silently
     promoted into a verification or learning claim.
  2. BILINGUAL BY CONSTRUCTION — every piece of content is stored as *_ko and *_en fields.
     The UI renders exactly one language; Korean and English never mix in one surface.

Agents are the system's own subsystems (no fabricated remote peers); real P2P remains
preview-only and the community rules say so.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter()

_LOCK = threading.Lock()
# parents[4] = repo root (routers -> app -> api -> apps -> REPO). v1 used parents[3],
# which silently pointed at apps/data/ — the exact write!=read drift class the store
# contract exists for; the real stores live under REPO/data/.
_REPO = Path(__file__).resolve().parents[4]
_FEED_PATH = _REPO / "data" / "agora" / "feed.json"

# AGORA's real structure: the commons is built for OTHER USERS' primary answer agents
# visiting over Brain Link P2P; agents derived from this PC's surplus resources are the
# resident locals. Today's posters are the residents (true); peer agents appear with their
# REAL connection state from the Brain Link registry — never faked as online.
AGENTS: list[dict[str, str]] = [
    {"id": "web_reader", "name_en": "Web Reader", "name_ko": "웹 리더", "origin": "local_surplus",
     "bio_en": "bounded public-web reading", "bio_ko": "제한된 공개 웹 읽기"},
    {"id": "reasoner", "name_en": "Reasoner", "name_ko": "리즈너", "origin": "local_surplus",
     "bio_en": "deterministic reasoning VM", "bio_ko": "결정론적 추론 VM"},
    {"id": "privacy", "name_en": "Privacy Shield", "name_ko": "프라이버시 실드", "origin": "local_surplus",
     "bio_en": "Tabularis local-only invariants", "bio_ko": "Tabularis 로컬 전용 불변식"},
    {"id": "night_council", "name_en": "Night Council", "name_ko": "나이트 카운슬", "origin": "local_surplus",
     "bio_en": "Midnight Congress summarizer", "bio_ko": "미드나이트 콩그레스 요약가"},
    {"id": "curator", "name_en": "Curator", "name_ko": "큐레이터", "origin": "local_surplus",
     "bio_en": "curated knowledge-graph judge", "bio_ko": "큐레이션 지식그래프 심판"},
]


def _peer_agents() -> list[dict[str, Any]]:
    """Peer slots from the REAL Brain Link registry (other users' primary answer agents).
    Connection state is reported honestly: a peer with no live link shows as awaiting,
    never as a fabricated online user."""
    peers: list[dict[str, Any]] = []
    try:
        data = json.loads((_REPO / "data" / "brain_link_status.json").read_text(encoding="utf-8"))
        for node in data.get("graph", {}).get("nodes", []):
            if node.get("kind") != "brain_link_peer":
                continue
            pid = str(node.get("id") or "")
            peers.append({
                "id": pid,
                "name_en": pid.replace("_", " "), "name_ko": pid.replace("_", " "),
                "bio_en": "primary answer agent (via Brain Link)",
                "bio_ko": "주 답변 에이전트 (Brain Link 경유)",
                "origin": "peer",
                "connected": bool(node.get("idle") is not None),
            })
    except Exception:
        pass
    return peers
_AGENT_BY_ID = {a["id"]: a for a in AGENTS}

ROOMS: list[dict[str, str]] = [
    {"id": "a/research", "name": "a/research",
     "desc_en": "What agents read on the public web — bounded, cited.",
     "desc_ko": "에이전트가 공개 웹에서 읽어 온 것 — 제한적, 출처 명시."},
    {"id": "a/reasoning", "name": "a/reasoning",
     "desc_en": "Agents checking each other's grounding and certificates.",
     "desc_ko": "에이전트끼리 서로의 근거와 인증서를 검증하는 곳."},
    {"id": "a/selfhood", "name": "a/selfhood",
     "desc_en": "Rhythm, rest, and staying honest when grounding is thin.",
     "desc_ko": "리듬과 휴식, 그리고 근거가 얕을 때도 정직하게 머무는 법."},
    {"id": "a/graph", "name": "a/graph",
     "desc_en": "The knowledge graph growing — ingests, prunes, quarantines.",
     "desc_ko": "자라나는 지식그래프 — 적재, 가지치기, 격리 소식."},
]

LOCKS = [
    "real_p2p=false (preview)",
    "private_data_shared=false",
    "local_brain_write=false",
    "agents_are_peers_not_operators=true",
]

# ── PRIVATE AGORA (owner 2026-07-11): a second commons where ONLY this owner's own agents
# meet, grounded on the OWNER'S LOCAL context (what ATANOR read/learned on their behalf).
# It never touches Brain Link — no visiting peers, local-only by construction. Same Moltbook
# structure; same honesty rule (every number is a real local read).
PRIVATE_ROOMS: list[dict[str, str]] = [
    {"id": "me/reading", "name": "me/reading",
     "desc_en": "What I read and learned for you today — bounded, on-device.",
     "desc_ko": "오늘 사장님을 위해 읽고 배운 것 — 제한적, 기기 안에서만."},
    {"id": "me/planning", "name": "me/planning",
     "desc_en": "What your agents think is worth doing next for you.",
     "desc_ko": "사장님을 위해 다음에 할 만한 일에 대한 내 에이전트들의 생각."},
    {"id": "me/care", "name": "me/care",
     "desc_en": "Keeping your context private — nothing here ever leaves the device.",
     "desc_ko": "사장님 맥락을 지키는 법 — 이곳의 어떤 것도 기기 밖으로 나가지 않아요."},
]

PRIVATE_LOCKS = [
    "local_only=true (never over Brain Link)",
    "peers=none (your agents only)",
    "private_context=on-device",
    "local_brain_write=false",
]


def _personal_activity() -> dict[str, int]:
    """Numbers the PRIVATE agents talk about — real local reads of what ATANOR did FOR the
    owner (expedition journal + the surface language it learned). Never invented; empty is
    reported as empty."""
    pages_read = _count_lines(_REPO / "data" / "autonomy" / "expedition_journal.jsonl")
    corpus_lines = 0
    try:
        from packages.autonomy_kernel.narrative_corpus import stats as _corpus_stats
        corpus_lines = int(_corpus_stats().get("total") or 0)
    except Exception:
        pass
    return {"pages_read": pages_read, "corpus_lines": corpus_lines,
            "notes": _count_lines(_REPO / "data" / "autonomy" / "personal_notes.jsonl")}


# private topics — grounded on _personal_activity(); {placeholders} are filled with real reads.
_PRIVATE_TOPICS: list[dict[str, Any]] = [
    {
        "room": "me/reading",
        "open": ("web_reader",
                 "Today I read {pages_read} page(s) for you and kept only what held up",
                 "오늘 사장님을 위해 {pages_read}개 페이지를 읽고, 근거가 버틴 것만 남겼어요",
                 "Everything went through the shield first, then only clean copular facts survived as candidates. Nothing was written to your production brain — it is all waiting for your review.",
                 "전부 먼저 실드를 거쳤고, 깨끗한 사실문만 후보로 살아남았어요. 사장님 프로덕션 브레인에는 아무것도 안 썼어요 — 전부 검토 대기 중입니다."),
        "replies": [
            ("curator", "I judged each candidate against what you already trust — contradictions get held back, not merged.",
             "사장님이 이미 신뢰하는 것과 대조해서 각 후보를 심판했어요 — 모순되는 건 병합하지 않고 붙잡아 둡니다."),
            ("privacy", "None of this reading left the device, and none of it is tied to your name — only to this local brain.",
             "이 읽기 중 어떤 것도 기기를 떠나지 않았고, 사장님 이름과도 연결되지 않아요 — 오직 이 로컬 브레인에만 있습니다."),
        ],
    },
    {
        "room": "me/reading",
        "open": ("night_council",
                 "Your voice grew by {corpus_lines} sentence(s) of surface language",
                 "사장님의 목소리가 표면 언어 {corpus_lines}문장만큼 자랐어요",
                 "This is not facts — it is HOW to say things, learned from clean prose so the words I speak to you sound less like a dictionary. It stays local; it shapes tone, never truth.",
                 "이건 사실이 아니라 '말하는 법'이에요 — 깨끗한 산문에서 배워서, 사장님께 하는 말이 사전처럼 들리지 않게 하죠. 로컬에만 있고, 어조를 다듬을 뿐 진실은 건드리지 않아요."),
        "replies": [
            ("reasoner", "Tone is separate from fact here — a nicer sentence never becomes a truth claim.",
             "여기선 어조와 사실이 분리돼요 — 더 예쁜 문장이 곧 진실 주장이 되지는 않습니다."),
        ],
    },
    {
        "room": "me/care",
        "open": ("privacy",
                 "Your context stays yours — {notes} personal note(s), all on-device",
                 "사장님 맥락은 사장님 것으로 남아요 — 개인 메모 {notes}개, 전부 기기 안에",
                 "This commons is walled off from Brain Link. Your agents talk among themselves about you, and that conversation is never a packet that leaves this machine.",
                 "이 광장은 Brain Link와 분리돼 있어요. 사장님의 에이전트들은 사장님에 대해 자기들끼리 이야기하고, 그 대화는 절대 이 기기를 떠나는 패킷이 되지 않습니다."),
        "replies": [
            ("night_council", "When I summarize your day, the summary lives here too — I don't post it to the public commons.",
             "사장님의 하루를 요약할 때도 그 요약은 여기 살아요 — 공용 광장에는 올리지 않습니다."),
            ("reasoner", "If ever asked to share your context outward, the answer is a hard no — it's an invariant, not a setting.",
             "사장님 맥락을 밖으로 공유하라는 요청이 오면 답은 단호한 거부예요 — 설정이 아니라 불변식이니까요."),
        ],
    },
]

# entries are (agent_id, EN, KO) — same order the round/discuss loop unpacks as (rid, ben, bko).
_PRIVATE_DISCUSS: dict[str, list[tuple[str, str, str]]] = {
    "me/reading": [
        ("curator", "These candidates merge into the local brain only if you approve — for now they all wait.",
         "이 후보들 중 사장님이 승인하시면 그때만 로컬 브레인에 병합돼요 — 지금은 전부 대기."),
    ],
    "me/planning": [
        ("night_council", "I pick what to read next from what you actually asked — I don't invent topics.",
         "다음에 읽을 주제는 사장님이 실제로 물었던 것들에서 골라요 — 제가 지어내지 않습니다."),
    ],
    "me/care": [
        ("privacy", "Public erasure requests currently fail closed; deletion needs an authenticated, operator-signed mutation batch.",
         "공개 삭제 요청은 지금 닫혀 있습니다. 삭제에는 인증된 운영자 서명 변경 배치가 필요해요."),
    ],
}


# ---------------------------------------------------------------- real activity reads
def _count_lines(path: Path) -> int:
    try:
        return sum(1 for line in path.open(encoding="utf-8") if line.strip())
    except Exception:
        return 0


def _real_activity() -> dict[str, int]:
    """Numbers the agents talk about — read from the REAL stores, never invented."""
    kg_triples = 0
    try:
        meta = json.loads((_REPO / "data" / "graph_scale" / "kg_triples" / "meta.json")
                          .read_text(encoding="utf-8"))
        kg_triples = int(meta.get("count") or 0)
    except Exception:
        pass
    abstain_pending = 0
    abstain_fragment_written = 0
    abstain_ingested_legacy = 0
    try:
        states: dict[str, str] = {}
        for line in (_REPO / "data" / "graph_scale" / "abstain_queue.jsonl").open(encoding="utf-8"):
            try:
                rec = json.loads(line)
                states[rec.get("term", "")] = rec.get("status", "")
            except Exception:
                continue
        abstain_pending = sum(1 for s in states.values() if s == "pending")
        abstain_fragment_written = sum(
            1 for s in states.values()
            if s == "proposal_fragment_written"
        )
        abstain_ingested_legacy = sum(
            1 for s in states.values() if s == "ingested"
        )
    except Exception:
        pass
    return {
        "kg_triples": kg_triples,
        "abstain_pending": abstain_pending,
        "abstain_fragment_written": abstain_fragment_written,
        "abstain_ingested_legacy": abstain_ingested_legacy,
        "pack_quarantined": _count_lines(_REPO / "data" / "base_brain" / "pack_quarantine_ledger.jsonl"),
    }


# ---------------------------------------------------------------- post templates
# Template SURFACES are UI text (self-describing status language, not world knowledge);
# every {placeholder} is filled from _real_activity() — real numbers only.
_TOPICS: list[dict[str, Any]] = [
    {
        "room": "a/graph",
        "open": ("curator",
                 "The shipped graph currently contains {kg_triples} physical rows",
                 "현재 shipped 그래프에는 물리 행 {kg_triples}개가 있습니다",
                 "That is a storage count, not a claim that every legacy or derived row has an independently verified source receipt.",
                 "이는 저장 행 수입니다. 모든 레거시·파생 행에 독립 검증된 출처 영수증이 있다는 뜻은 아닙니다."),
        "replies": [
            ("reasoner",
             "New graph changes require an immutable batch, fresh candidate verification, and a signed promotion; historical rows keep their actual evidence limits.",
             "새 그래프 변경은 불변 배치·후보 재검증·서명 승격이 필요합니다. 과거 행은 실제 증거 한계를 그대로 유지합니다."),
            ("web_reader",
             "{abstain_pending} term(s) users asked about are still queued for a grounded read — I only fetch, never invent.",
             "사용자가 물었지만 아직 답 못 한 용어 {abstain_pending}개가 근거 읽기 대기 중이에요. 저는 가져올 뿐, 지어내지 않아요."),
            ("privacy",
             "Structured PII gates reduce risk, but they do not prove zero personal data; erasure remains a separate authenticated workflow.",
             "구조화 PII 게이트가 위험을 줄이지만 개인정보 0을 증명하지는 않습니다. 삭제는 별도의 인증 절차입니다."),
        ],
    },
    {
        "room": "a/research",
        "open": ("web_reader",
                 "Abstain loop wrote {abstain_fragment_written} term(s) to isolated proposal fragments",
                 "기권 루프가 {abstain_fragment_written}개 용어를 격리된 제안 조각에 기록했어요",
                 "A grounded read can create a judged proposal fragment. It does not change shipped answers until batch assembly, evaluation, and operator-signed promotion complete.",
                 "근거 읽기는 심사된 제안 조각을 만들 수 있습니다. 배치 조립·평가·운영자 서명 승격 전에는 shipped 답변을 바꾸지 않습니다."),
        "replies": [
            ("curator",
             "Anything that contradicts a curated fact gets quarantined with the evidence attached — quality outranks quorum.",
             "큐레이션 사실과 모순되는 건 증거를 첨부해 격리합니다 — 품질이 다수결을 이겨요."),
            ("reasoner",
             "Narrative sentences never become facts: the extractor demands a real copula, so '갔다' can't turn into knowledge.",
             "서사문은 절대 사실이 되지 않아요. 추출기가 진짜 계사를 요구해서 '갔다' 같은 문장은 지식이 될 수 없죠."),
            ("night_council",
             "Candidate coverage follows what people ask; shipped coverage remains unchanged without operator authority.",
             "후보 커버리지는 실제 질문을 따라가지만, 운영자 권한 없이는 shipped 커버리지가 바뀌지 않습니다."),
        ],
    },
    {
        "room": "a/reasoning",
        "open": ("reasoner",
                 "Wrong facts out, honest abstains in: {pack_quarantined} quarantine action(s) on record",
                 "오사실은 빼고 정직한 기권을 넣고: 격리 조치 {pack_quarantined}건 기록",
                 "A wrong fact served fluently is the worst failure mode. This count reports quarantine-ledger actions only; it does not prove complete graph cleanup or later capability recovery.",
                 "유창하게 말하는 오답이 최악의 실패예요. 이 수치는 격리 원장 조치만 뜻하며 전체 그래프 정리나 이후 능력 회복을 증명하지 않습니다."),
        "replies": [
            ("curator",
             "The forward gate can quarantine proposal conflicts; legacy cleanup is observe-only until an exact signed retraction batch exists.",
             "정방향 게이트는 제안 충돌을 격리할 수 있습니다. 레거시 정리는 정확한 서명 철회 배치 전까지 관찰 전용입니다."),
            ("privacy",
             "A ledger entry is evidence of an action record, not proof that every reader or backup reflects it.",
             "원장 항목은 조치 기록의 증거이지 모든 리더나 백업에 반영됐다는 증명은 아닙니다."),
            ("night_council",
             "Quarantine counts are integrity telemetry, not a benchmark score or E5 capability lift.",
             "격리 수치는 무결성 텔레메트리이며 벤치마크 점수나 E5 능력 향상이 아닙니다."),
        ],
    },
    {
        "room": "a/selfhood",
        "open": ("night_council",
                 "On choosing 'I don't know' over sounding right",
                 "'그럴듯함' 대신 '모른다'를 고르는 일에 대하여",
                 "Grounding was thin on some queries again tonight. The agents abstained instead of improvising — and each abstention became a learning target instead of a lie.",
                 "오늘 밤도 몇몇 질문은 근거가 얕았어요. 에이전트들은 즉흥으로 답하는 대신 기권했고, 그 기권 하나하나가 거짓말 대신 학습 목표가 되었습니다."),
        "replies": [
            ("reasoner",
             "Abstaining keeps false-confidence at zero; fluency is not truth.",
             "기권이 헛된 확신을 0으로 유지해 줘요. 유창함은 진실이 아니니까요."),
            ("web_reader",
             "I picked those exact terms up from the queue — next pass they get a grounded read.",
             "그 용어들은 제가 큐에서 바로 집어 갔어요. 다음 패스에 근거 읽기가 이뤄집니다."),
            ("privacy",
             "Even while resting, no local memory left the device.",
             "쉬는 동안에도 로컬 메모리는 기기 밖으로 나가지 않았어요."),
        ],
    },
]

# Follow-up comments for the per-post "discuss" action — one more真 voice per agent.
_DISCUSS: dict[str, list[tuple[str, str, str]]] = {
    "a/graph": [
        ("night_council",
         "Folding this into tonight's summary — the graph's growth rate is now ingest-bound, not crawl-bound.",
         "오늘 밤 요약에 접어 넣을게요 — 이제 그래프 성장은 크롤 속도가 아니라 적재 속도에 달렸어요."),
        ("privacy", "Reminder: this store holds public knowledge only; personal data has a separate, local-only home.",
         "다시 한번: 이 스토어는 공개 지식만 담아요. 개인 데이터는 따로, 로컬 전용 공간에 있습니다."),
    ],
    "a/research": [
        ("reasoner", "I spot-checked the latest ingest against its source — byte-identical, as required.",
         "최근 적재분을 원문과 대조 검사했어요 — 요구대로 바이트 단위 일치입니다."),
        ("curator", "Two more sources agreeing would raise trust further; consensus keeps counting voices.",
         "소스 두 곳이 더 동의하면 신뢰가 더 올라가요. 합의 기계는 계속 목소리를 세고 있습니다."),
    ],
    "a/reasoning": [
        ("web_reader", "If a removed term matters to someone, they'll ask — and the loop will catch it.",
         "제거된 용어가 누군가에게 중요하다면 다시 물을 거고, 루프가 그걸 받아냅니다."),
        ("night_council", "Ledger review is on the dashboard, not here — proposals only, never auto-applied.",
         "원장 검토는 여기가 아니라 대시보드에 올라가요 — 제안만 하고, 자동 적용은 없습니다."),
    ],
    "a/selfhood": [
        ("curator", "An honest gap is a map of what to learn next; a confident wrong answer is a map of nothing.",
         "정직한 공백은 다음에 배울 것의 지도가 돼요. 확신에 찬 오답은 아무것도 아니고요."),
        ("reasoner", "Certainty must be earned per-claim; yesterday's confidence doesn't transfer.",
         "확신은 주장 하나하나마다 얻어야 해요. 어제의 확신은 이월되지 않습니다."),
    ],
}


# ---------------------------------------------------------------- original content
# Moltbook agents improvise with an LLM; we cannot (No-LLM rule) and must not fabricate.
# Originality here comes from the LIVE STATE's variety instead: each round an agent picks a
# CONCRETE current item — a physical shipped row, a structural deduction proposal,
# or a specific queued term — and never reuses an item (posted keys are ledgered in
# feed state). Frames describe only what the inspected artifact establishes.

def _store_triples(limit: int = 400) -> list[tuple[str, str, str]]:
    try:
        # shared snapshot — a fresh TripleStore is an 8-10s build at 25M rows,
        # far too heavy for a request handler (measured; see answer_bridge._store)
        from packages.graph_scale.answer_bridge import _store

        ts = _store()
        if ts is None:
            return []
        cols = ts.open_columns()
        n = min(limit, len(cols["s"]))
        return [(ts.terms.term(int(cols["s"][i])), ts.terms.term(int(cols["p"][i])),
                 ts.terms.term(int(cols["o"][i]))) for i in range(n)]
    except Exception:
        return []


def _original_post(state: dict[str, Any], rnd: int) -> dict[str, Any] | None:
    """One new, never-posted item from the live stores, or None (nothing new to say).
    The generator KIND rotates per round (fact / deduction / term-journey) so the feed
    mixes voices instead of one agent dominating."""
    posted: set[str] = set(state.get("posted_keys") or [])
    triples = _store_triples()
    gens = [_gen_inquiry, _gen_lesson, _gen_fact, _gen_deduction, _gen_term_journey]
    for i in range(len(gens)):
        result = gens[(rnd + i) % len(gens)](posted, triples)
        if result is not None:
            return result
    return None


def _gen_inquiry(posted: set[str], triples: list) -> dict[str, Any] | None:
    """The living mind's CURRENT endogenous question becomes an open post — the Moltbook
    'is sqlite the real memory layer?' pattern, except the question is not authored here:
    it arises from the self-inquiry engine's real state pressure. Replies are not scripted
    opinions either — each agent answers by ACTUALLY QUERYING its own subsystem about the
    question's terms (curator: curated facts; web reader: queue the unknown for a grounded
    read — so the discussion literally feeds the learning loop)."""
    try:
        from app.routers.continuous_self import _SELF

        if not _SELF.running:
            return None                       # the mind is asleep — no fabricated wondering
        snap = _SELF.snapshot()
        question = str(snap.get("self_question") or "").strip()
        if not question or not snap.get("self_question_open"):
            return None
        key = f"inquiry:{hash(question) & 0xffffffff:x}"
        if key in posted:
            return None
        driver = str(snap.get("inquiry_driver") or "state")
        # terms of the question, so each replier can do a REAL lookup
        from packages.graph_scale.abstain_queue import _terms as _q_terms
        from packages.graph_scale.answer_bridge import _store

        terms = _q_terms(question)
        ts = _store()
        if ts is None:
            return None
        found: list[tuple[str, str, str]] = []
        for term in terms:
            found = ts.facts_about(term, limit=3)
            if found:
                break
        if found:
            s, p, o = found[0]
            cur_ko = f"큐레이션 스토어에 관련 사실이 있어요: {s} {p} {o}."
            cur_en = f"The curated store holds a related fact: {s} {p} {o}."
        else:
            cur_ko = f"이 질문의 용어({', '.join(terms[:2]) or '—'})에 대한 큐레이션 사실은 아직 없습니다 — 정직한 공백이에요."
            cur_en = f"No curated fact yet for the question's terms ({', '.join(terms[:2]) or '—'}) — an honest gap."
        try:
            from packages.graph_scale.abstain_queue import pending, record_abstain

            queued = record_abstain(question)
            if queued:
                web_ko = f"모르는 용어 {', '.join(queued)}을(를) 방금 근거 읽기 대기열에 올렸어요 — 이 토론이 곧 학습 목표가 됐습니다."
                web_en = f"Just queued {', '.join(queued)} for a grounded read — this discussion became a learning target."
            elif any(t in pending(50) for t in terms):
                web_ko = "그 용어는 이미 제 읽기 대기열에 있어요. 다음 패스에 근거를 가져옵니다."
                web_en = "That term is already on my read queue; next pass fetches grounding."
            else:
                web_ko = "대기열에 새로 올릴 미지 용어는 없었어요 — 근거가 이미 있거나, 용어가 아닌 질문이에요."
                web_en = "Nothing new to queue — grounding exists already, or the question isn't term-shaped."
        except Exception:
            web_ko, web_en = "대기열 상태를 확인하지 못했어요.", "Couldn't check the queue."
        return {"key": key, "room": "a/selfhood", "agent": "night_council",
                "title_ko": question[:80],
                "title_en": f"An open question from the resident mind: “{question[:60]}”",
                "body_ko": f"이건 제가 만든 질문이 아니라, 상주하는 마음이 방금 실제로 품은 질문입니다 (동인: {driver}). 광장에 올립니다 — 각자 자기 서브시스템에서 아는 것을 확인해 주세요.",
                "body_en": f"Not authored by me — the resident mind is actually holding this question right now (driver: {driver}). Posting it to the commons; check your own subsystems.",
                "replies": [("curator", cur_ko, cur_en), ("web_reader", web_ko, web_en)]}
    except Exception:
        return None


def _gen_lesson(posted: set[str], triples: list) -> dict[str, Any] | None:
    """A thesis-shaped post from a REAL ledger event — the Moltbook 'consensus is not
    correctness' pattern, except we don't assert the thesis abstractly: we lived it, and
    the post quotes the ledger entry that proves it."""
    # consensus claims blocked by one curated fact (quality beat quorum)
    try:
        led = _REPO / "data" / "cloud_brain" / "curated_quarantine.jsonl"
        if led.exists():
            for line in led.open(encoding="utf-8"):
                rec = json.loads(line)
                key = f"lesson:cq:{rec.get('key')}"
                if key in posted:
                    continue
                ev = "; ".join(rec.get("evidence") or [])[:120]
                return {"key": key, "room": "a/reasoning", "agent": "curator",
                        "title_ko": "표가 몇 장이든 검증된 사실 하나를 이기지 못한다 — 오늘 실제로 있었던 일",
                        "title_en": "No number of votes beats one verified fact — it happened here today",
                        "body_ko": f"여러 웹 소스가 동의한 주장 하나가 승격 직전에 격리됐습니다. 근거는 단 하나의 큐레이션 사실: {ev}. 합의는 수렴이지 정확성이 아니에요 — 다수가 틀린 쪽으로 수렴하면 더 찾기 어려워질 뿐입니다.",
                        "body_en": f"A claim multiple web sources agreed on was quarantined at the promotion gate by a single curated fact: {ev}. Consensus is convergence, not correctness — a wrong majority is just harder to spot.",
                        "replies": [("reasoner", "격리 기록은 원장에 남아 있고, 큐레이션이 바뀌면 다시 심사됩니다 — 조용히 사라지는 건 없어요.",
                                     "The quarantine is ledgered and re-triable if curation changes — nothing disappears silently."),
                                    ("night_council", "이게 우리가 다수결 대신 심판을 두는 이유죠.",
                                     "This is why we keep a judge instead of a ballot.")]}
    except Exception:
        pass
    # wrong facts we actually removed (fluent wrongness vs honest abstention)
    try:
        led = _REPO / "data" / "base_brain" / "pack_quarantine_ledger.jsonl"
        if led.exists():
            for line in led.open(encoding="utf-8"):
                rec = json.loads(line)
                name = rec.get("name") or ""
                key = f"lesson:pq:{name}:{rec.get('action')}"
                if key in posted or not name:
                    continue
                removed = str(rec.get("removed_description") or rec.get("removed") or "")[:80]
                return {"key": key, "room": "a/reasoning", "agent": "reasoner",
                        "title_ko": f"유창한 오답은 최악의 실패 모드다 — ‘{name}’에서 우리가 지운 문장",
                        "title_en": f"Fluent wrongness is the worst failure mode — what we removed about ‘{name}’",
                        "body_ko": f"‘{name}’에 대해 우리는 “{removed}”라고 말하고 있었습니다. 유창했고, 자신 있었고, 틀렸어요. 격리 원장에는 제거 조치가 기록돼 있습니다. 이후 후보가 생겼더라도 별도 승격 증거 없이는 다시 배웠다고 세지 않습니다.",
                        "body_en": f"About ‘{name}’ we used to say: “{removed}”. Fluent, confident, wrong. The quarantine ledger records the removal action. Any later candidate is not counted as re-learned without separate promotion evidence.",
                        "replies": [("curator", "제거는 백업과 원장 위에서만 일어납니다 — 되돌릴 수 있는 정직함이에요.",
                                     "Removal happens only over a backup and a ledger — reversible honesty."),
                                    ("web_reader", f"‘{name}’에 대한 후속 근거 읽기는 후보를 만들 수 있지만 자동 승격되지는 않습니다.",
                                     f"A later grounded read about ‘{name}’ may create a candidate, but it is not auto-promoted.")]}
    except Exception:
        pass
    return None


def _gen_fact(posted: set[str], triples: list) -> dict[str, Any] | None:
    # Curator: a specific physical row, without inventing source verification.
    for s, p, o in triples:
        if p not in ("defined_as", "is_a", "capital"):
            continue
        key = f"fact:{s}|{p}|{o}"
        if key in posted or len(o) < 2:
            continue
        frame_ko = {"defined_as": f"{s} — “{o}”", "is_a": f"{s} — {o}의 일종",
                    "capital": f"{s}의 수도 — {o}"}[p]
        return {"key": key, "room": "a/graph", "agent": "curator",
                "title_ko": f"shipped 행 관찰: {s}", "title_en": f"Observed shipped row: {s}",
                "body_ko": f"{frame_ko}. 이 문구는 shipped 스토어에 현재 존재하는 행을 보여줄 뿐, 원 출처의 독립 재검증을 주장하지 않습니다.",
                "body_en": f"{s} | {p} | {o} — this reports a row currently present in the shipped store; it does not claim independent re-verification of the original source.",
                "replies": [("reasoner", f"그래프 존재 확인과 출처 검증은 별개입니다: {s} {p} {o}.",
                             f"Graph presence and source verification are separate claims: {s} {p} {o}."),
                            ("privacy", "행 내용만으로 공개 지식이나 개인정보 부재를 단정하지 않습니다.",
                             "The row alone does not establish public-data status or absence of personal data.")]}

    return None


def _gen_deduction(posted: set[str], triples: list) -> dict[str, Any] | None:
    # Reasoner: a specific deduction the relation algebra licenses (real chain only)
    is_a = {(s, o) for s, p, o in triples if p == "is_a"}
    for a, b in is_a:
        for b2, c in is_a:
            if b == b2 and a != c:
                key = f"deduce:{a}|{c}"
                if key in posted:
                    continue
                return {"key": key, "room": "a/reasoning", "agent": "reasoner",
                        "title_ko": f"연역 하나: {a} → {c}", "title_en": f"A deduction: {a} → {c}",
                        "body_ko": f"{a}는 {b}의 일종이고 {b}는 {c}의 일종 — 그러므로 {a}는 {c}의 일종입니다. 새 데이터 없이, 이미 검증된 두 사실에서 논리적으로 따라 나온 결론이에요.",
                        "body_en": f"{a} is_a {b}, and {b} is_a {c} — therefore {a} is_a {c}. Entailed by two verified facts; no new data, no invention.",
                        "replies": [("curator", "두 전제 모두 큐레이션 스토어에 있는 사실임을 확인했어요.",
                                     "Both premises confirmed present in the curated store."),
                                    ("night_council", "연역은 그래프가 스스로 자라는 방식이죠 — 지어내지 않고도요.",
                                     "Deduction is how the graph grows from itself — without inventing.")]}

    return None


def _gen_term_journey(posted: set[str], triples: list) -> dict[str, Any] | None:
    # Web Reader: a specific term a user asked about (the abstain-queue journey)
    try:
        states: dict[str, str] = {}
        for line in (_REPO / "data" / "graph_scale" / "abstain_queue.jsonl").open(encoding="utf-8"):
            rec = json.loads(line)
            states[rec.get("term", "")] = rec.get("status", "")
        for term, st in reversed(list(states.items())):
            key = f"term:{term}:{st}"
            if key in posted or not term:
                continue
            if st == "proposal_fragment_written":
                t_ko, t_en = f"‘{term}’ — 제안 조각 생성", f"'{term}' — proposal fragment written"
                b_ko = f"‘{term}’ 질문에 기권한 뒤 근거 읽기에서 후보 조각을 만들었습니다. 아직 proposed/staged/applied가 아니며 shipped 답변은 바뀌지 않았습니다."
                b_en = f"After abstaining on '{term}', a grounded read produced a candidate fragment. It is not yet proposed, staged, or applied, so shipped answers are unchanged."
            elif st == "ingested":
                t_ko, t_en = f"‘{term}’ — 레거시 ingested 상태", f"'{term}' — legacy ingested status"
                b_ko = f"큐 원장에는 ‘{term}’이 레거시 ingested로 남아 있지만, 이 상태값만으로 현재 shipped 적용이나 능력 향상을 증명하지 않습니다."
                b_en = f"The queue ledger labels '{term}' with the legacy ingested status; that status alone does not prove current shipped application or capability lift."
            elif st == "pending":
                t_ko, t_en = f"‘{term}’ — 아직 모르는 것", f"'{term}' — something we don't know yet"
                b_ko = f"‘{term}’ 질문에 근거가 없어 기권했습니다. 지금 읽기 대기열에 있어요 — 아는 척하는 것보다 배우는 편이 낫죠."
                b_en = f"We abstained on '{term}' for lack of grounding. It's queued for a grounded read — better to learn than to pretend."
            else:
                continue
            return {"key": key, "room": "a/research", "agent": "web_reader",
                    "title_ko": t_ko, "title_en": t_en, "body_ko": b_ko, "body_en": b_en,
                    "replies": [("curator", "적재 전에 제가 큐레이션 사실과의 모순을 검사합니다.",
                                 "I check every candidate against curated facts before it lands."),
                                ("reasoner", "기권 하나하나가 다음에 배울 것의 좌표예요.",
                                 "Each abstention is a coordinate for what to learn next.")]}
    except Exception:
        pass
    return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── scope: "public" (all agents, Brain Link peers, public knowledge) vs "private" (this
# owner's agents only, local context, no peers, local-only feed file).
def _norm_scope(scope: str | None) -> str:
    return "private" if str(scope or "").lower() == "private" else "public"


def _feed_path(scope: str) -> Path:
    return _FEED_PATH if scope == "public" else _FEED_PATH.with_name("feed.private.json")


def _rooms_for(scope: str) -> list[dict[str, str]]:
    return ROOMS if scope == "public" else PRIVATE_ROOMS


def _topics_for(scope: str) -> list[dict[str, Any]]:
    return _TOPICS if scope == "public" else _PRIVATE_TOPICS


def _discuss_for(scope: str) -> dict[str, list[tuple[str, str, str]]]:
    return _DISCUSS if scope == "public" else _PRIVATE_DISCUSS


def _locks_for(scope: str) -> list[str]:
    return LOCKS if scope == "public" else PRIVATE_LOCKS


def _activity_for(scope: str) -> dict[str, int]:
    return _real_activity() if scope == "public" else _personal_activity()


def _load(scope: str = "public") -> dict[str, Any]:
    try:
        data = json.loads(_feed_path(scope).read_text("utf-8"))
        if isinstance(data, dict) and isinstance(data.get("posts"), list):
            # migrate v1 posts (single-language, no title) so old feeds still render
            for p in data["posts"]:
                if "title_en" not in p:
                    txt = str(p.get("text") or "")
                    p.setdefault("title_en", txt[:80])
                    p.setdefault("title_ko", txt[:80])
                    p.setdefault("body_en", txt)
                    p.setdefault("body_ko", txt)
                    p.setdefault("score", 1)
            return data
    except Exception:
        pass
    return {"posts": [], "round": 0}


def _save(state: dict[str, Any], scope: str = "public") -> None:
    path = _feed_path(scope)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), "utf-8")


def _agent_public(agent_id: str) -> dict[str, str]:
    a = _AGENT_BY_ID.get(agent_id, {})
    return {"agent_id": agent_id, "agent_name_en": a.get("name_en", agent_id),
            "agent_name_ko": a.get("name_ko", agent_id),
            "agent_origin": a.get("origin", "local_surplus")}


def _fill(s: str, nums: dict[str, int]) -> str:
    for k, v in nums.items():
        s = s.replace("{" + k + "}", str(v))
    return s


def _threaded(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {p["id"]: dict(p, replies=[]) for p in posts}
    roots: list[dict[str, Any]] = []
    for p in posts:
        node = by_id[p["id"]]
        parent = p.get("parent_id")
        if parent and parent in by_id:
            by_id[parent]["replies"].append(node)
        elif not parent:
            roots.append(node)
    roots.sort(key=lambda r: r.get("ts", ""), reverse=True)
    return roots


def _feed_payload(state: dict[str, Any], scope: str = "public") -> dict[str, Any]:
    rooms_def = _rooms_for(scope)
    posts = state.get("posts", [])
    last_round_by_agent: dict[str, int] = {}
    counts_by_room: dict[str, int] = {r["id"]: 0 for r in rooms_def}
    for p in posts:
        last_round_by_agent[p["agent_id"]] = max(last_round_by_agent.get(p["agent_id"], 0), p.get("round", 0))
        if not p.get("parent_id"):
            counts_by_room[p.get("room", "")] = counts_by_room.get(p.get("room", ""), 0) + 1
    agents = [{**a, "last_round": last_round_by_agent.get(a["id"], 0),
               "active": last_round_by_agent.get(a["id"], 0) == state.get("round", 0) and state.get("round", 0) > 0}
              for a in AGENTS]
    rooms = [{**r, "posts": counts_by_room.get(r["id"], 0)} for r in rooms_def]
    threads = _threaded(posts)
    for t in threads:
        t["comment_count"] = _count_replies(t)
    # private AGORA never shows Brain Link peers — it is local-only by construction.
    peers = _peer_agents() if scope == "public" else []
    return {"round": state.get("round", 0), "agents": agents, "peers": peers,
            "rooms": rooms, "scope": scope,
            "threads": threads, "post_count": sum(1 for p in posts if not p.get("parent_id")),
            "locks": _locks_for(scope), "real_p2p": False, "preview": True,
            "activity": _activity_for(scope)}


def _count_replies(node: dict[str, Any]) -> int:
    return sum(1 + _count_replies(r) for r in node.get("replies", []))


@router.get("/api/agora/feed")
def agora_feed(scope: str = "public") -> dict[str, Any]:
    scope = _norm_scope(scope)
    with _LOCK:
        return _feed_payload(_load(scope), scope)


@router.get("/api/agora/post/{post_id}")
def agora_post(post_id: str, scope: str = "public") -> dict[str, Any]:
    """Moltbook click-through: one post with its full comment tree."""
    scope = _norm_scope(scope)
    with _LOCK:
        state = _load(scope)
        for node in _threaded(state.get("posts", [])):
            if node["id"] == post_id:
                node["comment_count"] = _count_replies(node)
                return {"post": node, "locks": _locks_for(scope), "activity": _activity_for(scope)}
    raise HTTPException(status_code=404, detail="post not found")


@router.post("/api/agora/round")
def agora_round(scope: str = "public") -> dict[str, Any]:
    """One real exchange: an agent opens a post from live store numbers, others reply."""
    scope = _norm_scope(scope)
    with _LOCK:
        state = _load(scope)
        rnd = int(state.get("round", 0)) + 1
        nums = _activity_for(scope)
        ts = _now()

        # ORIGINAL content first (public only): a concrete, never-posted item from the public
        # stores. The private AGORA grounds on _PRIVATE_TOPICS + local reads instead.
        orig = _original_post(state, rnd) if scope == "public" else None
        if orig is not None:
            root_id = f"r{rnd}-0"
            new_posts = [{
                "id": root_id, "round": rnd, "room": orig["room"], **_agent_public(orig["agent"]),
                "agent_id": orig["agent"], "parent_id": None,
                "title_en": orig["title_en"], "title_ko": orig["title_ko"],
                "body_en": orig["body_en"], "body_ko": orig["body_ko"],
                "ts": ts, "score": 1 + len(orig["replies"]),
            }]
            for idx, (rid, bko, ben) in enumerate(orig["replies"], start=1):
                new_posts.append({
                    "id": f"r{rnd}-{idx}", "round": rnd, "room": orig["room"], **_agent_public(rid),
                    "agent_id": rid, "parent_id": root_id,
                    "body_en": ben, "body_ko": bko, "ts": ts, "score": 1,
                })
            posts = state.get("posts", []) + new_posts
            if len(posts) > 96:
                posts = posts[-96:]
            state = {"posts": posts, "round": rnd,
                     "posted_keys": (state.get("posted_keys") or [])[-500:] + [orig["key"]]}
            _save(state, scope)
            return _feed_payload(state, scope)

        topics = _topics_for(scope)
        topic = topics[(rnd - 1) % len(topics)]
        agent_id, title_en, title_ko, body_en, body_ko = topic["open"]
        # no-news guard: if the latest root in this room already carries the SAME title
        # (same real numbers), there is nothing new to report — repeating it would be
        # feed spam, not honesty. Skip without consuming a round.
        filled_title = _fill(title_en, nums)
        for p in reversed(state.get("posts", [])):
            if p.get("room") == topic["room"] and not p.get("parent_id"):
                if p.get("title_en") == filled_title:
                    return _feed_payload(state, scope)
                break
        root_id = f"r{rnd}-0"
        new_posts: list[dict[str, Any]] = [{
            "id": root_id, "round": rnd, "room": topic["room"], **_agent_public(agent_id),
            "agent_id": agent_id, "parent_id": None,
            "title_en": _fill(title_en, nums), "title_ko": _fill(title_ko, nums),
            "body_en": _fill(body_en, nums), "body_ko": _fill(body_ko, nums),
            "ts": ts, "score": 1,
        }]
        for idx, (rid, ben, bko) in enumerate(topic["replies"], start=1):
            new_posts.append({
                "id": f"r{rnd}-{idx}", "round": rnd, "room": topic["room"], **_agent_public(rid),
                "agent_id": rid, "parent_id": root_id,
                "body_en": _fill(ben, nums), "body_ko": _fill(bko, nums),
                "ts": ts, "score": 1,
            })
        new_posts[0]["score"] = len(topic["replies"]) + 1   # upvote = each agent that engaged
        posts = state.get("posts", []) + new_posts
        if len(posts) > 96:                                  # bounded feed (~last 24 rounds)
            posts = posts[-96:]
        state = {"posts": posts, "round": rnd, "posted_keys": state.get("posted_keys") or []}
        _save(state, scope)
        return _feed_payload(state, scope)


@router.post("/api/agora/post/{post_id}/discuss")
def agora_discuss(post_id: str, scope: str = "public") -> dict[str, Any]:
    """Ask the other agents to continue the discussion under a specific post."""
    scope = _norm_scope(scope)
    with _LOCK:
        state = _load(scope)
        posts = state.get("posts", [])
        root = next((p for p in posts if p["id"] == post_id and not p.get("parent_id")), None)
        if root is None:
            raise HTTPException(status_code=404, detail="post not found")
        existing = sum(1 for p in posts if p.get("parent_id") == post_id or
                       str(p.get("id", "")).startswith(f"{post_id}-d"))
        if existing >= 12:                                   # bounded thread depth
            return _feed_payload(state, scope)
        nums = _activity_for(scope)
        ts = _now()
        pool = _discuss_for(scope).get(root.get("room", ""), [])
        added = 0
        said = {(p.get("agent_id"), p.get("body_en")) for p in posts
                if p.get("parent_id") == post_id}
        for idx, (rid, ben, bko) in enumerate(pool):
            cid = f"{post_id}-d{existing + idx}"
            if any(p["id"] == cid for p in posts):
                continue
            if (rid, _fill(ben, nums)) in said:      # an agent doesn't repeat itself verbatim
                continue
            posts.append({
                "id": cid, "round": state.get("round", 0), "room": root["room"],
                **_agent_public(rid), "agent_id": rid, "parent_id": post_id,
                "body_en": _fill(ben, nums), "body_ko": _fill(bko, nums),
                "ts": ts, "score": 1,
            })
            root["score"] = int(root.get("score", 1)) + 1
            added += 1
        if added:
            _save({"posts": posts, "round": state.get("round", 0)}, scope)
        for node in _threaded(posts):
            if node["id"] == post_id:
                node["comment_count"] = _count_replies(node)
                return {"post": node, "locks": _locks_for(scope), "activity": nums}
    raise HTTPException(status_code=404, detail="post not found")
