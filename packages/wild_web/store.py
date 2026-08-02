# -*- coding: utf-8 -*-
"""Wild-web persistence — the ONLY side-effecting module. All four channels write here, behind a
single module-level DATA_DIR that tests monkeypatch to a tmp path (realcity persistence pattern).

The CONSENSUS-BY-DOMAIN promotion (Channel 2) mirrors packages/autonomy_kernel/register_harvest.py:
a template is hashed on its normalized form, staged with its source domain (deduped per
(hash, domain) so the same site twice adds no signal), and PROMOTED to register_pool.jsonl only once
its distinct-domain count reaches MIN_DOMAINS (2). Independent domains ~= independent strangers.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR: Path = _ROOT / "data" / "wild_web"   # monkeypatchable (tests set this to tmp_path)
MIN_DOMAINS = 2                                 # consensus floor — register_harvest doctrine parity

_QUARANTINE = "quarantine.jsonl"
_STAGING = "register_staging.jsonl"
_POOL = "register_pool.jsonl"
_FRAG_STAGING = "fragment_staging.jsonl"      # Channel 2b — discourse-act skeletons (staging)
_FRAG_POOL = "fragment_pool.jsonl"            # Channel 2b — promoted (>= 2 distinct domains)
_TOPICS = "curiosity_topics.jsonl"
_CAUSAL = "causal_candidates.jsonl"
_CAUSAL_POOL = "causal_pool.jsonl"
_VISITED = "visited.jsonl"
_SESSIONS = "sessions.jsonl"


def _dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def _p(name: str) -> Path:
    return _dir() / name


def domain_of(url: str) -> str:
    """Consensus source id — the registrable-ish domain (www. stripped). For most of the web an
    independent domain ~= an independent stranger."""
    try:
        dom = (urlparse(url).netloc or "unknown").lower()
        return dom[4:] if dom.startswith("www.") else dom
    except Exception:
        return "unknown"


def _append(name: str, row: dict[str, Any]) -> None:
    with _p(name).open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read(name: str) -> list[dict[str, Any]]:
    try:
        return [json.loads(ln) for ln in _p(name).read_text(encoding="utf-8").splitlines()
                if ln.strip()]
    except FileNotFoundError:
        return []
    except Exception:
        return []


# ── Channel 1 — RAW quarantine (hearsay archive) ────────────────────────────────────────────────
def quarantine(source_url: str, segment: str) -> None:
    _append(_QUARANTINE, {"source_url": source_url, "ts": int(time.time()), "segment": segment})


# ── Channel 2 — REGISTER staging + consensus promotion ──────────────────────────────────────────
def _hash(norm_key: str) -> str:
    return hashlib.sha256(norm_key.encode("utf-8")).hexdigest()[:16]


def stage_register(template: str, dialogue_act: str, norm_key: str,
                   domain: str, source_url: str) -> str:
    """Stage one anonymized template and promote on consensus. Returns:
      'promoted'  — this template just reached >= MIN_DOMAINS distinct domains (now in register_pool),
      'staged'    — recorded from a NEW domain but still below consensus,
      'duplicate' — same template already seen from this same domain (no new signal).
    """
    h = _hash(norm_key)
    domains: set[str] = set()
    for r in _read(_STAGING):
        if r.get("h") == h:
            domains.add(r.get("domain"))

    if domain in domains:
        status = "duplicate"                       # same pattern, same domain — no new signal
    else:
        _append(_STAGING, {"h": h, "template": template, "dialogue_act": dialogue_act,
                           "domain": domain, "source_url": source_url, "ts": int(time.time())})
        domains.add(domain)
        status = "staged"

    if len(domains) >= MIN_DOMAINS:
        already = {r.get("h") for r in _read(_POOL)}
        if h not in already:
            _append(_POOL, {"h": h, "template": template, "dialogue_act": dialogue_act,
                            "domains": sorted(d for d in domains if d), "n_domains": len(domains),
                            "ts": int(time.time())})
            return "promoted"
    return status


# ── Channel 2b — FRAGMENT register (discourse-act skeletons) staging + consensus promotion ───────
# The convergence lever: WHOLE anonymized segments are near-unique across strangers (only boilerplate
# ever crossed 2-domain consensus, a false positive we reject), but the 12..60-char discourse-ACT
# SKELETON inside them ('the trick is to', 'in my experience') DOES recur across independent domains.
# Same consensus machinery as stage_register (hash-dedup, per-(hash,domain) counting, MIN_DOMAINS),
# only the UNIT is the fragment (already canonical from transforms.extract_fragments). A lone fragment
# stays staged; >= 2 DISTINCT domains promote it to fragment_pool.jsonl (usable discourse register).
def stage_fragment(fragment: str, act: str, domain: str, source_url: str) -> str:
    """Stage one discourse-act fragment and promote on consensus. Returns 'promoted' (just reached
    >= MIN_DOMAINS distinct domains), 'staged' (new domain, still below), or 'duplicate' (same
    fragment already seen from this same domain — no new signal)."""
    h = _hash(fragment)
    domains: set[str] = set()
    for r in _read(_FRAG_STAGING):
        if r.get("h") == h:
            domains.add(r.get("domain"))

    if domain in domains:
        status = "duplicate"
    else:
        _append(_FRAG_STAGING, {"h": h, "fragment": fragment, "act": act,
                                "domain": domain, "source_url": source_url, "ts": int(time.time())})
        domains.add(domain)
        status = "staged"

    if len(domains) >= MIN_DOMAINS:
        already = {r.get("h") for r in _read(_FRAG_POOL)}
        if h not in already:
            _append(_FRAG_POOL, {"h": h, "fragment": fragment, "act": act,
                                 "domains": sorted(d for d in domains if d), "n_domains": len(domains),
                                 "ts": int(time.time())})
            return "promoted"
    return status


# ── Channel 3 — TOPIC curiosity queue (ungrounded pointers) ─────────────────────────────────────
def add_topic(topic: str) -> bool:
    """Append an ungrounded curiosity topic (deduped). Returns True if newly added."""
    if not topic:
        return False
    existing = {r.get("topic") for r in _read(_TOPICS)}
    if topic in existing:
        return False
    _append(_TOPICS, {"topic": topic, "status": "ungrounded", "ts": int(time.time())})
    return True


def next_ungrounded_topic() -> str | None:
    for r in _read(_TOPICS):
        if r.get("status") == "ungrounded":
            return r.get("topic")
    return None


# ── Channel 4 — CAUSAL candidates (hypotheses) + CONSENSUS corroboration ────────────────────────
# The consciousness-audit HOT-3 starvation was: causal candidates were logged but NEVER corroborated
# — every "X because Y" stayed a lone hypothesis. So the SAME register consensus the doctrine already
# applies to speech patterns now applies to causal edges: a normalized cause->effect attested by
# >= MIN_DOMAINS DISTINCT domains is CORROBORATED into causal_pool.jsonl (still not a fact — a
# hypothesis that independent strangers stated, which is exactly what later self-grounding needs).
def _edge_key(cause: str, effect: str) -> str:
    """Normalized cause->effect identity for consensus. Delegates to transforms.canonicalize_causal
    (lemmatize + strip modifiers + fold degree phrases + collapse change-of-state), so PARAPHRASES
    map to the SAME edge: 'leaves turn yellow'<-'overwatering' and 'yellowing'<-'too much water' both
    hash to over_water->yellow and corroborate across domains. Falls back to the old alnum-collapse if
    transforms is somehow unavailable (keeps store import-safe)."""
    try:
        from . import transforms as _T
        canon = _T.canonicalize_causal(cause, effect)["edge"]
    except Exception:
        canon = re.sub(r"[^a-z0-9]+", " ",
                       f"{str(cause or '').lower()} -> {str(effect or '').lower()}").strip()
        canon = re.sub(r"\s+", " ", canon)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]


def add_causal(cause: str, effect: str, source_url: str, pattern: str = "") -> str:
    """Stage one causal HYPOTHESIS and corroborate on cross-domain consensus. Deduped per
    (edge, domain) — the same edge from the same domain adds no signal (mirrors stage_register /
    register_harvest). Returns:
      'corroborated' — this edge just reached >= MIN_DOMAINS distinct domains (now in causal_pool),
      'staged'       — recorded from a NEW domain but still below consensus,
      'duplicate'    — same edge already seen from this same domain.
    Candidate rows keep {cause, effect, source_url, status:'hypothesis'} verbatim (consumed by
    continuous_self.causal_fuel, which counts distinct domains itself)."""
    dom = domain_of(source_url)
    ek = _edge_key(cause, effect)
    try:
        from . import transforms as _T
        _canon = _T.canonicalize_causal(cause, effect)
        canon_cause, canon_effect = _canon["canon_cause"], _canon["canon_effect"]
    except Exception:
        canon_cause, canon_effect = "", ""
    domains: set[str] = set()
    for r in _read(_CAUSAL):
        if r.get("edge") == ek or _edge_key(r.get("cause", ""), r.get("effect", "")) == ek:
            domains.add(domain_of(r.get("source_url", "")))

    if dom in domains:
        status = "duplicate"                       # same edge, same domain — no new signal
    else:
        _append(_CAUSAL, {"cause": cause, "effect": effect, "source_url": source_url,
                          "pattern": pattern, "status": "hypothesis", "edge": ek,
                          "canon_cause": canon_cause, "canon_effect": canon_effect,
                          "domain": dom, "ts": int(time.time())})
        domains.add(dom)
        status = "staged"

    if len(domains) >= MIN_DOMAINS:
        already = {r.get("edge") for r in _read(_CAUSAL_POOL)}
        if ek not in already:
            _append(_CAUSAL_POOL, {"edge": ek, "cause": cause, "effect": effect,
                                   "canon_cause": canon_cause, "canon_effect": canon_effect,
                                   "domains": sorted(d for d in domains if d),
                                   "n_domains": len(domains), "status": "corroborated",
                                   "pattern": pattern, "ts": int(time.time())})
            return "corroborated"
    return status


# ── EFFICIENCY — cross-session dedupe (visit_index pattern, browse_director recipe) ──────────────
# Two levers, both md5[:16] (same recipe as autonomy_kernel.browse_director visit_index):
#   (1) already_seen(url)      — never re-spend a fetch on a URL harvested in a past session.
#   (2) seen_content(url, txt) — skip byte-identical content SEEN FROM THE SAME DOMAIN before (a
#       within-domain crosspost/mirror adds no signal). It is deliberately NOT cross-domain: the same
#       sentence from a DIFFERENT domain is an independent stranger — exactly the consensus signal —
#       so content dedupe must never suppress a new domain (doctrine: domain ~= independent stranger).
def _md5(s: str) -> str:
    return hashlib.md5(str(s or "").encode("utf-8", "ignore")).hexdigest()[:16]


def url_key(url: str) -> str:
    return _md5(str(url or "").split("#")[0])


def content_hash(text: str) -> str:
    return _md5(re.sub(r"\s+", " ", str(text or "")).strip().lower())


def already_seen(url: str = "") -> bool:
    """True if this exact URL was harvested in a past session — the novelty drive spends the fetch
    budget on NEW sources, not pages already read."""
    if not url:
        return False
    uk = url_key(url)
    return any(r.get("ukey") == uk for r in _read(_VISITED))


def seen_content(url: str, content_text: str) -> bool:
    """True if this exact content was already harvested FROM THIS SAME DOMAIN (within-domain mirror /
    crosspost — no new signal). Cross-domain identical content is NOT flagged (it is consensus)."""
    ch = content_hash(content_text)
    dom = domain_of(url)
    return any(r.get("chash") == ch and r.get("domain") == dom for r in _read(_VISITED))


def mark_visited(url: str, content_text: str = "") -> None:
    _append(_VISITED, {"ukey": url_key(url), "chash": content_hash(content_text),
                       "domain": domain_of(url), "url": url, "ts": int(time.time())})


# ── session summary ─────────────────────────────────────────────────────────────────────────────
def log_session(summary: dict[str, Any]) -> None:
    _append(_SESSIONS, {**summary, "ts": int(time.time())})


# ── read-backs (tests + status) ─────────────────────────────────────────────────────────────────
def read_quarantine() -> list[dict[str, Any]]:
    return _read(_QUARANTINE)


def read_register_staging() -> list[dict[str, Any]]:
    return _read(_STAGING)


def read_register_pool() -> list[dict[str, Any]]:
    return _read(_POOL)


def read_fragment_staging() -> list[dict[str, Any]]:
    return _read(_FRAG_STAGING)


def read_fragment_pool() -> list[dict[str, Any]]:
    return _read(_FRAG_POOL)


def read_topics() -> list[dict[str, Any]]:
    return _read(_TOPICS)


def read_causal() -> list[dict[str, Any]]:
    return _read(_CAUSAL)


def read_causal_pool() -> list[dict[str, Any]]:
    return _read(_CAUSAL_POOL)


def read_visited() -> list[dict[str, Any]]:
    return _read(_VISITED)


def status() -> dict[str, Any]:
    return {
        "data_dir": str(DATA_DIR),
        "quarantined": len(read_quarantine()),
        "register_staged": len(read_register_staging()),
        "register_promoted": len(read_register_pool()),
        "fragment_staged": len(read_fragment_staging()),
        "fragment_promoted": len(read_fragment_pool()),
        "topics": len(read_topics()),
        "causal_candidates": len(read_causal()),
        "causal_corroborated": len(read_causal_pool()),
        "urls_visited": len(read_visited()),
        "min_domains": MIN_DOMAINS,
    }
