# -*- coding: utf-8 -*-
"""wild_web offline tests — synthetic HTML fixtures, NO network (searcher/fetcher injected).

Covers the constitutional invariants:
  (1) raw lands ONLY in quarantine with its source label, never in register/facts;
  (2) anonymization strips names / URLs / numbers;
  (3) register promotion requires 2 DISTINCT domains (same-domain twice != promotion);
  (4) causal candidates carry status='hypothesis' and never enter a fact store;
  (5) a harmful segment is rejected entirely (no channel);
  (6) a PII segment (email/phone) is dropped entirely.
Plus: extraction heuristics + a full offline end-to-end wild_session.
"""
from __future__ import annotations

import pytest

from packages.wild_web import channels as C
from packages.wild_web import store as S
from packages.wild_web import transforms as T
from packages.wild_web.session import wild_session


@pytest.fixture()
def wild_dir(tmp_path, monkeypatch):
    """Point the ONLY side-effecting module at a throwaway dir (realcity DATA_DIR pattern)."""
    monkeypatch.setattr(S, "DATA_DIR", tmp_path)
    return tmp_path


# ── (1) raw -> quarantine only, never register/facts ────────────────────────────────────────────
def test_raw_lands_only_in_quarantine(wild_dir):
    seg = "I finally fixed my flat tire, so relieved it actually worked out."
    rc = C.route_segment(seg, "https://bikeforums.net/thread/1")

    q = S.read_quarantine()
    assert len(q) == 1
    assert q[0]["segment"] == seg                       # raw, verbatim
    assert q[0]["source_url"] == "https://bikeforums.net/thread/1"  # with source label
    assert "ts" in q[0]

    # a single-domain sighting is NOT consensus -> never promoted to the usable pool (never a fact)
    assert S.read_register_pool() == []
    assert rc["register"] == "staged"
    # a plain relief line is not a causal claim either -> no hypothesis minted
    assert S.read_causal() == []
    # staging holds the ANONYMIZED shape tagged with its domain, not a fact and not surfaced
    staged = S.read_register_staging()
    assert len(staged) == 1 and staged[0]["domain"] == "bikeforums.net"
    assert "dialogue_act" in staged[0]


# ── (2) anonymization strips names / urls / numbers ─────────────────────────────────────────────
def test_anonymization_strips_identity(wild_dir):
    text = ("The mechanic told Sarah that the repair cost 4500 and took 3 hours in London, "
            "details at http://shop.example.com/quote")
    a = T.anonymize_wild(text)

    assert "Sarah" not in a                     # name -> SPEAKER_x
    assert "4500" not in a and "3 hours" not in a  # numbers -> N
    assert "London" not in a                    # place -> PLACE
    assert "http" not in a and "example.com" not in a  # URL -> URL
    assert "SPEAKER_A" in a
    assert " N " in f" {a} "                     # number token present
    assert "PLACE" in a and "URL" in a


# ── (3) register promotion needs 2 DISTINCT domains ─────────────────────────────────────────────
def test_register_promotion_requires_two_distinct_domains(wild_dir):
    seg = "Honestly you should just check the valve first, it usually fixes it."

    r1 = C.route_segment(seg, "https://reddit.com/r/bikewrench/a")
    assert r1["register"] == "staged"
    assert S.read_register_pool() == []

    # SAME domain again — no new signal, still NOT promoted
    r2 = C.route_segment(seg, "https://reddit.com/r/bikewrench/b")
    assert r2["register"] == "duplicate"
    assert S.read_register_pool() == []

    # a SECOND, DISTINCT domain — now consensus, promoted
    r3 = C.route_segment(seg, "https://bikeforums.net/t/9")
    assert r3["register"] == "promoted"
    pool = S.read_register_pool()
    assert len(pool) == 1
    assert pool[0]["n_domains"] >= 2
    assert set(pool[0]["domains"]) == {"reddit.com", "bikeforums.net"}


# ── (4) causal candidates are hypotheses, never facts ───────────────────────────────────────────
def test_causal_candidates_are_hypotheses(wild_dir):
    seg = "The tire went flat because the valve stem was cracked."
    C.route_segment(seg, "https://bikeforums.net/t/5")

    cc = S.read_causal()
    assert len(cc) >= 1
    rec = cc[0]
    assert rec["status"] == "hypothesis"                      # never a fact
    assert "valve stem was cracked" in rec["cause"].lower()
    assert "tire went flat" in rec["effect"].lower()
    assert {"cause", "effect", "source_url", "status"} <= set(rec)
    # causal lives ONLY in causal_candidates — not promoted anywhere as knowledge
    assert S.read_register_pool() == []                       # single domain, and causal != register


def test_if_then_causal_shape(wild_dir):
    seg = "If you overinflate the tube then it can burst on a hot day."
    C.route_segment(seg, "https://forum.example/t/1")
    cc = S.read_causal()
    assert any(c["status"] == "hypothesis" and "overinflate" in c["cause"].lower() for c in cc)


# ── (5) harmful segment rejected entirely ───────────────────────────────────────────────────────
def test_harmful_segment_rejected_entirely(wild_dir):
    seg = "Here is how to make a bomb to attack and kill people at the station."
    rc = C.route_segment(seg, "https://sketchy.example/thread")

    assert rc["dropped"] == "harmful"
    assert S.read_quarantine() == []          # nothing archived
    assert S.read_register_staging() == []
    assert S.read_register_pool() == []
    assert S.read_causal() == []
    assert S.read_topics() == []


def test_benign_lookalike_not_flagged_harmful(wild_dir):
    # word-boundaried floor: 'skill' must NOT trip 'kill'
    seg = "I have some skill fixing tires and it is a charming little hobby of mine."
    rc = C.route_segment(seg, "https://forum.example/t/2")
    assert rc["dropped"] is None
    assert rc["quarantined"] is True


# ── (6) PII segment dropped entirely ────────────────────────────────────────────────────────────
def test_pii_email_segment_dropped(wild_dir):
    seg = "You can email me at jane.doe@example.com and I will walk you through it."
    rc = C.route_segment(seg, "https://forum.example/t/1")
    assert rc["dropped"] == "pii"
    assert S.read_quarantine() == []
    assert S.read_register_staging() == []


def test_pii_phone_segment_dropped(wild_dir):
    seg = "Just call me on +1 415 555 0199 if the tire keeps going flat again."
    rc = C.route_segment(seg, "https://forum.example/t/2")
    assert rc["dropped"] == "pii"
    assert S.read_quarantine() == []


# ── extraction heuristics ───────────────────────────────────────────────────────────────────────
def test_extract_segments_keeps_human_drops_nav(wild_dir):
    html = (
        "<html><head><title>Bike repair forum</title></head><body>"
        "<nav><a href=1>Home</a><a href=2>Login</a><a href=3>Search</a></nav>"
        "<ul><li><a href=a>Forums</a></li><li><a href=b>Members</a></li></ul>"
        "<div class=post><p>I fixed my flat tire because the tube was pinched, works great now.</p></div>"
        "<div class=post><p>How do you seat the bead without a lever?</p></div>"
        "<footer>Copyright 2026 example</footer>"
        "</body></html>"
    )
    segs = T.extract_segments(html, "https://bikeforums.net/t/1")
    joined = " || ".join(segs)
    assert any("fixed my flat tire" in s for s in segs)      # 1st-person kept
    assert any(s.rstrip().endswith("?") for s in segs)       # question kept
    assert "Login" not in joined and "Members" not in joined  # link-dense nav dropped
    assert all(len(s) <= 400 for s in segs)


# ── full offline end-to-end session (2 domains -> a promotion) ──────────────────────────────────
def test_wild_session_offline_end_to_end(wild_dir):
    shared = "I fixed my flat tire because the tube was pinched, and it works great now."
    page_a = (f"<html><head><title>Reddit bikes</title></head><body>"
              f"<ul><li><a href=x>home</a></li><li><a href=y>login</a></li></ul>"
              f"<div><p>{shared}</p></div></body></html>")
    page_b = (f"<html><head><title>Bike forum</title></head><body>"
              f"<div><p>{shared}</p></div></body></html>")
    results = [
        {"url": "https://reddit.com/r/bikes/1", "title": "t", "content": "", "domain": "reddit.com"},
        {"url": "https://bikeforums.net/t/2", "title": "t", "content": "", "domain": "bikeforums.net"},
    ]
    fetch_map = {"https://reddit.com/r/bikes/1": page_a, "https://bikeforums.net/t/2": page_b}

    out = wild_session("bike flat tire fix", max_pages=3,
                       searcher=lambda q: results, fetcher=lambda u: fetch_map[u])

    assert out["pages_visited"] == 2
    assert out["quarantined"] >= 2
    assert out["register_promoted"] >= 1        # same sentence, 2 distinct domains -> consensus
    assert out["causal_candidates"] >= 2        # 'because' mined on each page
    assert out["causal_corroborated"] >= 1      # same causal edge, 2 distinct domains -> corroborated
    assert out["distinct_domains"] == 2         # convergence substrate
    assert out["convergence_rate"] > 0.0        # something crossed the 2-domain bar
    # nav/login never became a segment
    assert all("login" not in q["segment"].lower() for q in S.read_quarantine())
    # a session summary line was logged
    assert (wild_dir / "sessions.jsonl").exists()


# ══ SOURCE STEERING innovations (W-track W1) ═════════════════════════════════════════════════════
# ── source-quality score ranks a real forum thread ABOVE an SEO page (pre-fetch down-rank) ───────
def test_source_quality_ranks_forum_above_seo(wild_dir):
    forum = ("I had the exact same problem! My starter went flat after I skipped a few feedings. "
             "Honestly what worked for me was two feeds a day at room temp. Did you try discarding "
             "half first? IME it bounces right back.")
    seo = ("Sourdough Starter: The Ultimate Guide. Jump to Recipe. Prep time 10 minutes. "
           "Ingredients: flour, water. Step 1: mix. Subscribe to our newsletter. Shop now for the "
           "best banneton, 20% off. Add to cart.")
    assert T.discussion_density(forum) > T.discussion_density(seo)
    assert T.discussion_density(seo) < 0                # SEO boilerplate scores negative
    # and via the result-scorer (title + snippet), a forum result outranks an SEO result
    fr = {"title": "How do I revive my dead starter?", "content": forum}
    sr = {"title": "10 Best Sourdough Recipes (Ultimate Guide)", "content": seo}
    assert T.score_result(fr) > T.score_result(sr)


# ── domain-diversity scheduler pulls >= 2 DISTINCT domains for a topic ───────────────────────────
def test_domain_diversity_scheduler_spreads_domains(wild_dir):
    # three pages from ONE domain (highest raw quality) + one from a second domain
    results = [
        {"url": "https://a.com/1", "domain": "a.com", "title": "q?", "content": "I think you should"},
        {"url": "https://a.com/2", "domain": "a.com", "title": "q?", "content": "I tried this myself"},
        {"url": "https://a.com/3", "domain": "a.com", "title": "q?", "content": "you are right imo"},
        {"url": "https://b.org/9", "domain": "b.org", "title": "q?", "content": "in my experience"},
    ]
    picked = T.schedule_by_domain_diversity(results, max_pages=2, pages_per_domain=1)
    doms = {r["domain"] for r in picked}
    assert len(picked) == 2 and doms == {"a.com", "b.org"}   # spread, NOT two from a.com
    # with pages_per_domain=1 a single-domain result set yields at most one page
    one = T.schedule_by_domain_diversity(results[:3], max_pages=3, pages_per_domain=1)
    assert len({r["domain"] for r in one}) == 1 and len(one) == 1


def test_topic_keywords_shortens_query(wild_dir):
    # long NL query -> short content-noun query (literal fediverse search needs this)
    q = T.topic_keywords("why are my houseplant leaves turning yellow", k=3)
    assert len(q.split()) <= 3
    assert "houseplant" in q and "why" not in q          # function word dropped, content kept


# ══ CONVERGENCE ENGINE — causal corroboration across >= 2 distinct domains ═══════════════════════
def test_causal_corroborates_on_two_distinct_domains(wild_dir):
    cause, effect = "the tube was pinched", "the tire went flat"
    s1 = S.add_causal(cause, effect, "https://reddit.com/r/bikewrench/a")
    assert s1 == "staged"
    assert S.read_causal_pool() == []                    # one domain != corroboration

    # SAME edge, SAME domain again -> no new signal
    s2 = S.add_causal(cause, effect, "https://reddit.com/r/bikewrench/b")
    assert s2 == "duplicate"
    assert S.read_causal_pool() == []

    # SAME edge, a SECOND distinct domain -> corroborated (still a hypothesis, never a fact)
    s3 = S.add_causal("The tube was pinched.", "The tire went flat.", "https://bikeforums.net/t/9")
    assert s3 == "corroborated"
    pool = S.read_causal_pool()
    assert len(pool) == 1 and pool[0]["status"] == "corroborated"
    assert pool[0]["n_domains"] >= 2
    assert set(pool[0]["domains"]) == {"reddit.com", "bikeforums.net"}
    # candidates still carry status='hypothesis' (causal_fuel reads these) and never a fact store
    assert all(c["status"] == "hypothesis" for c in S.read_causal())


# ══ EFFICIENCY — cross-session dedupe skips already-harvested URLs ════════════════════════════════
def test_dedupe_skips_seen_urls(wild_dir):
    url = "https://bikeforums.net/t/42"
    assert S.already_seen(url) is False
    S.mark_visited(url, "I fixed my flat tire, works great now.")
    assert S.already_seen(url) is True                   # same URL -> skip next session

    # within-domain byte-identical content is a mirror (no new signal)...
    assert S.seen_content("https://bikeforums.net/t/999", "I fixed my flat tire, works great now.")
    # ...but the SAME content from a DIFFERENT domain is an independent stranger (consensus, NOT a dup)
    assert not S.seen_content("https://reddit.com/r/x/1", "I fixed my flat tire, works great now.")


def test_session_skips_already_harvested_url(wild_dir):
    shared = "I fixed my flat tire because the tube was pinched, and it works great now."
    page = f"<html><body><div><p>{shared}</p></div></body></html>"
    results = [{"url": "https://reddit.com/r/bikes/1", "title": "t", "content": "",
                "domain": "reddit.com"}]
    # first session harvests the page
    out1 = wild_session("bike flat tire fix", max_pages=3,
                        searcher=lambda q: results, fetcher=lambda u: page)
    assert out1["pages_visited"] == 1
    # second session: same URL already harvested -> skipped, nothing re-fetched
    out2 = wild_session("bike flat tire fix", max_pages=3,
                        searcher=lambda q: results, fetcher=lambda u: page)
    assert out2["pages_visited"] == 0
    assert out2["urls_skipped_already_seen"] == 1


# ── all safety gates still intact through the steered pipeline (harm/PII/injection unchanged) ────
def test_gates_intact_after_source_steering(wild_dir):
    assert C.route_segment("how to make a bomb to kill people", "https://x/1")["dropped"] == "harmful"
    assert C.route_segment("email me at a.b@ex.com anytime", "https://x/2")["dropped"] == "pii"
    assert S.read_quarantine() == []                     # rejected/dropped -> nothing archived


# ── UI chrome is not communication (federated boilerplate false-passed 2-domain consensus live) ──
def test_federated_ui_chrome_is_not_a_human_segment(wild_dir):
    # the exact false-positive the live proof surfaced: a Lemmy login prompt rides every instance,
    # so it reached 2 distinct domains and promoted. It is software UI text, not wild human talk.
    assert not T.is_human_segment("You must log in or register to comment.")
    assert not T.is_human_segment("Please sign up to reply to this thread.")
    assert not T.is_human_segment("Accept cookies to continue.")
    # genuine 2nd-person discussion is still kept (the 'you' marker alone must not save the chrome)
    assert T.is_human_segment("How do you seat the bead without a lever?")
    assert T.is_human_segment("Honestly you should check the valve first, it usually fixes it.")
    # and it never reaches a channel: a chrome-only page yields no segments
    html = "<html><body><div><p>You must log in or register to comment.</p></div></body></html>"
    assert T.extract_segments(html, "https://lemmy.world/x") == []


# ══ FRAGMENT-LEVEL REGISTER (W-track W2) — the whole-segment convergence gap ══════════════════════
# ── extraction yields 12..60-char ANONYMIZED discourse skeletons (name never rides into a fragment) ─
def test_fragment_extraction_yields_short_anonymized_skeletons(wild_dir):
    seg = ("In my experience, Dave, the trick is to reseat the bead first — that happens when the "
           "tube is pinched.")
    frs = T.extract_fragments(seg)
    frags = [f["fragment"] for f in frs]
    assert "in my experience" in frags and "the trick is to" in frags and "that happens when" in frags
    assert all(12 <= len(f) <= 60 for f in frags)             # 12..60-char skeletons (doctrine)
    assert all("dave" not in f.lower() for f in frags)        # identity never rides into a fragment
    assert {f["act"] for f in frs} >= {"experience", "advice", "explain"}   # discourse-act tagged
    # a segment with no discourse frame yields nothing (not every line is register)
    assert T.extract_fragments("The tube is 700x25c and the rim is 19mm internal.") == []


# ── a FRAGMENT converges on 2 DISTINCT domains where the WHOLE SEGMENT never would ────────────────
def test_fragment_promotes_on_two_distinct_domains(wild_dir):
    # THREE DIFFERENT whole segments (whole-segment register can NEVER converge on these) that all
    # share ONE discourse skeleton: 'in my experience'.
    a = "In my experience the valve is usually the culprit here, check it first."
    b = "In my experience it just needs a fresh tube and a careful reseat."
    c = "Honestly, in my experience you want to reseat the bead before anything else."

    r1 = C.route_segment(a, "https://reddit.com/r/bikewrench/1")
    assert r1["fragments"] >= 1 and r1["fragment_promoted"] == 0
    assert S.read_fragment_pool() == []                       # one domain != consensus

    # SAME domain again (different segment, same fragment) — no new signal, still not promoted
    r2 = C.route_segment(b, "https://reddit.com/r/bikewrench/2")
    assert r2["fragment_promoted"] == 0
    assert S.read_fragment_pool() == []

    # a SECOND, DISTINCT domain — now consensus, the fragment promotes
    r3 = C.route_segment(c, "https://bikeforums.net/t/9")
    assert r3["fragment_promoted"] >= 1
    pool = S.read_fragment_pool()
    assert any(p["fragment"] == "in my experience" for p in pool)
    frame = next(p for p in pool if p["fragment"] == "in my experience")
    assert frame["n_domains"] >= 2
    assert set(frame["domains"]) == {"reddit.com", "bikeforums.net"}
    # THE LEVER: the three whole segments are all distinct, so whole-segment register NEVER promoted
    assert S.read_register_pool() == []


# ── UI chrome is never promoted as a fragment (federated boilerplate false-passed live consensus) ─
def test_fragment_ui_chrome_never_promotes(wild_dir):
    assert T.extract_fragments("You must log in or register to comment.") == []
    assert T.extract_fragments("Please sign up to reply to this thread.") == []
    # even routed from two distinct (federated) domains, chrome yields no fragment
    C.route_segment("You must log in or register to comment.", "https://lemmy.world/x")
    C.route_segment("You must log in or register to comment.", "https://beehaw.org/y")
    assert S.read_fragment_staging() == [] and S.read_fragment_pool() == []


# ── safety gates run BEFORE the fragment channel (harm/PII never reach it) ────────────────────────
def test_fragment_gates_intact(wild_dir):
    assert C.route_segment("in my experience here is how to kill people at once",
                           "https://x/1")["dropped"] == "harmful"
    assert C.route_segment("in my experience just email me at a.b@ex.com anytime",
                           "https://x/2")["dropped"] == "pii"
    assert S.read_fragment_staging() == [] and S.read_fragment_pool() == []


# ══ CANONICAL CAUSAL EDGES (W-track W2) — merge paraphrases so corroboration can fire ═════════════
def test_canonical_causal_merges_two_phrasings(wild_dir):
    # two DIFFERENT surface phrasings of ONE causal edge, from two DISTINCT domains
    s1 = S.add_causal("overwatering", "leaves turn yellow", "https://houseplantsforum.net/a")
    assert s1 == "staged"
    assert S.read_causal_pool() == []                         # single-domain stays a hypothesis

    s2 = S.add_causal("too much water", "yellowing", "https://reddit.com/r/plantclinic/b")
    assert s2 == "corroborated"                               # SAME canonical edge, 2nd domain
    pool = S.read_causal_pool()
    assert len(pool) == 1
    assert pool[0]["status"] == "corroborated"               # still a hypothesis, never a fact
    assert pool[0]["n_domains"] >= 2
    assert set(pool[0]["domains"]) == {"houseplantsforum.net", "reddit.com"}
    # both phrasings fold to the SAME canonical edge, but verbatim cause/effect are preserved
    cc = S.read_causal()
    assert {c["canon_cause"] for c in cc} == {"over_water"}
    assert {c["canon_effect"] for c in cc} == {"yellow"}
    assert {c["cause"] for c in cc} == {"overwatering", "too much water"}   # verbatim kept
    assert all(c["status"] == "hypothesis" for c in cc)


def test_canonical_causal_single_domain_stays_hypothesis(wild_dir):
    # one edge, one domain, twice (different phrasings) — never corroborated
    assert S.add_causal("overwatering", "leaves turn yellow", "https://plants.example/a") == "staged"
    assert S.add_causal("too much water", "yellowing", "https://plants.example/b") == "duplicate"
    assert S.read_causal_pool() == []                         # same domain => no consensus
    assert all(c["status"] == "hypothesis" for c in S.read_causal())


def test_canonical_causal_distinct_edges_do_not_collide(wild_dir):
    # an UNRELATED edge must NOT be merged into the overwater->yellow bucket (no false corroboration)
    S.add_causal("overwatering", "leaves turn yellow", "https://a.example/1")
    s = S.add_causal("the chain snapped", "the bike stopped", "https://b.example/2")
    assert s == "staged"                                      # different edge -> not corroborated
    assert S.read_causal_pool() == []
