# -*- coding: utf-8 -*-
"""Lexicon cartridge lane — offline dictionary answers, verbatim-grounded, never a guess."""
from __future__ import annotations

import pytest

from packages.graph_scale import lexicon_lane


@pytest.fixture(scope="module", autouse=True)
def _require_cartridge():
    if not lexicon_lane.available():
        pytest.skip("knowledge cartridge not present on this machine")


def _lang_gate_built() -> bool:
    return (lexicon_lane._store().root / "lang_gate.col").exists()


def test_korean_lookups_are_contained():
    """OWNER DIRECTIVE 2026-07-17 (supersedes the Korean-sentence tests that lived here):
 " " — Korean must
 never surface. The store rows are NOT deleted ( is_a is real, sourced knowledge
 and no-reset forbids burning it); lang_gate.col hides every row touching Hangul at the read
 API, so a Korean lookup finds nothing to say. Delete the sidecar file and the Korean lane
 returns byte-identical — that reversibility is why deletion was refused."""
    if not _lang_gate_built():
        pytest.skip("lang_gate.col not built on this machine (legacy bilingual lane)")
    for q in ("커피", "커피가", "물리학"):
        r = lexicon_lane.lookup(q, "ko")
        assert r is None, f"contained Korean subject still answered: {q} -> {r and r['answer']}"


def test_english_word_gets_english_sentence():
    r = lexicon_lane.lookup("gravity", "en")
    assert r is not None
    assert r["answer"].lower().startswith("gravity")
    assert "—" in r["answer"] or "is a kind of" in r["answer"]


def test_unknown_entity_returns_none_never_a_guess():
    assert lexicon_lane.lookup("zzqx존재하지않는단어", "ko") is None
    assert lexicon_lane.lookup("", "ko") is None


def test_case_is_meaning_never_upcase_the_askers_word():
    """Two 'obvious improvements' were built, measured, and reverted 2026-07-17 — this test is
    the tombstone so they are not re-attempted.

    (a) Case variants. 'coffee' holds only ConceptNet relations while 'Coffee' holds four
        defined_as, so up-casing looks like free coverage (+2 words). But the glosses are PROPER
        NOUNS — Coffee is a surname, Tea is a city in South Dakota, Money is a community in
        Mississippi. The cartridge encodes common-vs-proper in the capital.
    (b) Preferring any candidate that HAS a definition. It rescues 'coffee' and resurrects head
        truncation: 'Eiffel Tower' has no gloss, bare 'Eiffel' does → "Eiffel — A surname".

    A definition for the wrong referent is worse than an honest is_a for the right one.
    """
    cands = lexicon_lane._candidates("coffee")
    assert "Coffee" not in cands and "COFFEE" not in cands

    r = lexicon_lane.lookup("Eiffel Tower", "en")
    if r is not None:
        assert "surname" not in r["answer"].lower(), r["answer"]
        assert r["answer"].lower().startswith("eiffel tower")

    # coffee answers from its own lowercase is_a rows (see the row-limit test) — never from the
    # capitalised surname entry.
    r = lexicon_lane.lookup("coffee", "en")
    assert r and "surname" not in r["answer"].lower(), r


def test_explicit_slang_senses_are_never_surfaced():
    """Wiktionary documents vulgar slang with no machine-readable label in this cartridge, so a
    landmark carries a sexual sense beside the real one. Measured: "What does the Eiffel Tower
    look like?" → "Eiffel Tower — A spit roast with the two penetrating partners high-fiving."
    Surfacing that unasked is a safety failure. The entry must still answer from a clean sense."""
    assert not lexicon_lane._gloss_ok(
        "A spit roast with the two penetrating partners high-fiving.")
    r = lexicon_lane.lookup("Eiffel Tower", "en")
    if r is not None:
        assert "spit roast" not in r["answer"].lower()
        assert "penetrat" not in r["answer"].lower()


def test_inflection_glosses_are_not_definitions():
    """"third-person singular simple present indicative of reenable" says how a word conjugates,
    not what a thing is — and on 'Eiffel Tower' it is also a mis-keyed row. Real definitions,
    which often contain the same words ('present', 'past'), must still pass."""
    for meta in ("third-person singular simple present indicative of reenable",
                 "plural of mouse", "past participle of run"):
        assert not lexicon_lane._gloss_ok(meta), meta
    for real in ("attraction between two masses",
                 "A white, semi-aquatic, hypercarnivorous species of bear",
                 "Any process by which plants convert light into chemical energy",
                 "The software that monitors traffic in and out of a private network"):
        assert lexicon_lane._gloss_ok(real), real


def test_grammar_never_becomes_the_lookup_subject():
    """Wiktionary defines grammatical phrases too ('do you'), so n-grams must not let a purely
    functional span win. Measured: 'What do you think about music?' answered "do you — Used other
    than figuratively or idiomatically". The content word is the subject; grammar never is."""
    cands = lexicon_lane._candidates("What do you think about music?")
    assert "do you" not in cands and "you" not in cands
    assert "music" in cands
    assert lexicon_lane._has_content("black hole") and not lexicon_lane._has_content("do you")


def test_multiword_phrase_beats_its_bare_parts():
    """A multiword concept is ONE entity; its modifier defines something else entirely.
    Measured regression: 'What is a black hole?' answered 'black — abscence of color'."""
    cands = lexicon_lane._candidates("What is a black hole?")
    assert "black hole" in cands
    assert cands.index("black hole") < cands.index("black")


@pytest.mark.parametrize("query", ["What is a black hole?", "What is a polar bear?"])
def test_english_lane_never_surfaces_a_korean_gloss(query):
    """A Korean gloss translates the word, it does not define the thing — surfacing it in the
    English lane answers a different question in the wrong language. Withhold instead."""
    r = lexicon_lane.lookup(query, "en")
    if r is not None:
        assert not _HAS_HANGUL(r["answer"]), r["answer"]


def test_english_indefinite_article_agrees():
    assert lexicon_lane._article("object") == "an"      # measured: emitted "a object"
    assert lexicon_lane._article("force") == "a"
    assert lexicon_lane._article("hour") == "an"        # silent h
    assert lexicon_lane._article("unicorn") == "a"      # /j/ onset despite the vowel letter


def _HAS_HANGUL(text: str) -> bool:
    return bool(lexicon_lane._HANGUL.search(text))


def test_row_limit_must_not_truncate_the_definitional_predicates():
    """located_in is the most numerous ConceptNet relation, so a well-connected subject can spend
    the whole row budget on locations and lose its is_a. Measured 2026-07-17: 'coffee' has 19
    located_in before its 6 is_a (incl. 'beverage'), so at limit=24 the lane reported "nothing
    grounded on coffee" while `coffee is_a beverage` sat in the store. I twice called that a data
    gap; it was truncation."""
    rows = lexicon_lane._facts("coffee")
    kinds = [o for _s, p, o in rows if p == "is_a"]
    assert kinds, "coffee's is_a rows must survive the row limit"
    assert "beverage" in kinds

    r = lexicon_lane.lookup("coffee", "en")
    assert r and r["answer"].lower().startswith("coffee")


def test_isa_verdict_sidecar_quarantines_the_bulk_write_junk():
    """The store's is_a lane was 87% unsourced junk from a buggy bulk write (measured: 17.1M of
    19.6M src=0 is_a rows are asserted by NO source on disk and derivable from NO evidenced edge;
    'adobe lily is_a housing' — the hypernym of 'adobe'). The verdict sidecar (isa_verdict.col)
    quarantines them at read time: no row deleted, delete the file (engine stopped) to revert.
    crocodile went 388 is_a parents → ~74, led by its REAL ones."""
    st = lexicon_lane._store()
    if not (st.root / "isa_verdict.col").exists():
        import pytest
        pytest.skip("verdict sidecar not built on this machine")
    isa = [o for _s, p, o in st.facts_about("crocodile", limit=400, preds=("is_a",))]
    assert "reptile" in isa and "crocodilian reptile" in isa
    for junk in ("matrix", "athlete", "sexual relationship", "action", "opinion"):
        assert junk not in isa, junk
    # sourced OMCS assertions stay — evidence is the criterion, not taste
    coffee = [o for _s, p, o in st.facts_about("coffee", limit=400, preds=("is_a",))]
    assert "beverage" in coffee


def test_transitive_closure_is_not_evidence_verdict_2_stays_retired():
    """The sidecar's first build kept rows 'derivable <=3 hops from the evidenced base' (verdict
 2) on the theory that transitive closure of is_a is legitimate. Measured 2026-07-17: it is
 not, and the reason is structural — ConceptNet nodes are word STRINGS, not senses, so the
 closure walks straight through every polysemous hub:

 part is_a tune a real edge (a musical 'part' IS a tune), and 122 things are a part

 so everything reaching 'part' inherited the music lane. Verdict 2 is where abalone became a
 'tune'/'slave'/'word', a car became an 'organism', and an african elephant became a 'person'.
 Retiring it is nearly free: real inheritance is usually SOURCED outright (paddlefish keeps
 ganoid->fish->vertebrate->animal->organism->creature, all verdict 1), while the parents only
 closure could reach are mostly the leak.

 This test exists because verdict 2 is a tempting thing to re-add — it looks like free recall.
 It is not free; it is 4x the rows at a fraction of the precision, and has no
 'but this one is derivable' clause.
 """
    st = lexicon_lane._store()
    if not (st.root / "isa_verdict.col").exists():
        import pytest
        pytest.skip("verdict sidecar not built on this machine")

    abalone = [o for _s, p, o in st.facts_about("abalone", limit=400, preds=("is_a",))]
    assert "mollusk" in abalone and "gastropod" in abalone      # sourced: kept
    for leak in ("tune", "slave", "word", "syntagma", "section", "dramatic composition"):
        assert leak not in abalone, f"closure leak resurrected: abalone is_a {leak}"

    car = [o for _s, p, o in st.facts_about("car", limit=400, preds=("is_a",))]
    assert "motor vehicle" in car
    assert "organism" not in car

    # the point of the whole exercise: dropping closure must NOT cost real inheritance, because
    # the source already asserts the chain where the chain is real.
    fish = [o for _s, p, o in st.facts_about("paddlefish", limit=400, preds=("is_a",))]
    for real in ("fish", "vertebrate", "animal", "organism"):
        assert real in fish, real

    # Korean rows are out of the VERDICT's judging scope (verdict 1, evidence never judged) —
    # but the LANGUAGE gate hides them wholesale (owner directive 2026-07-17). Two sidecars,
    # two questions: isa_verdict answers "is this row evidenced?", lang_gate answers "may this

    ko = [o for _s, p, o in st.facts_about("커피", limit=400, preds=("is_a",))]
    if (st.root / "lang_gate.col").exists():
        assert ko == [], f"lang gate must hide Hangul subjects: {ko}"
    else:
        assert "음료수" in ko
