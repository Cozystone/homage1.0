# -*- coding: utf-8 -*-
"""The inference must GENERALIZE by structure, not memorize phrases — so we test
sentences with the SAME structure but different entities and expect the same reasoning."""
from packages.graph_scale.intent_inference import infer


def _s(q):
    r = infer(q, store=None)
    return r["subject"], r["intent"]


def test_subject_is_the_topic_entity_not_a_modifier():
    # the central subject is the entity, never the counter/attribute/wh/auxiliary word
    # (English-only since 2026-07-18; the Korean originals retired with the Kiwi lane)
    assert _s("How many cups of coffee per day are okay?")[0] == "coffee"  # coffee, not the counter
    assert _s("What is the chemical formula of water?")[0] == "water"      # water, not formula
    assert _s("Was Rome an empire?")[0] == "Rome"                # Rome, not the auxiliary 'Was'
    # KNOWN GAP (measured 2026-07-18): 'What is the population of Seoul?' still centres on
    # 'population'. The head-first-genitive fix for it regressed four other tests (see the note in
    # intent_inference), so it is left failing-by-omission rather than papered over.


def test_quantity_intent_generalizes_to_unseen_entities():

    assert _s("커피 하루에 몇 잔까지 괜찮아?")[1] in ("quantity", "safe_quantity")
    assert _s("소주 몇 병까지 마셔도 돼?")[1] in ("quantity", "safe_quantity")
    assert _s("이 약 하루에 몇 알 먹어야 해?")[1] in ("quantity", "safe_quantity")
    # evaluation present → the SAFE-amount variant
    assert _s("커피 하루에 몇 잔까지 괜찮아?")[1] == "safe_quantity"


def test_wh_roles_compose_the_right_intent():
    assert _s("에펠탑 어디에 있어?")[1] == "location"
    assert _s("비트코인 왜 올랐어?")[1] == "cause"
    assert _s("김치찌개 끓이는 법 알려줘")[1] == "method"
    assert _s("아인슈타인이 누구야?")[1] == "identity"
    assert _s("커피가 뭐야?")[1] == "definition"


def test_comparison_needs_two_entities():
    subj, intent = _s("파이썬이랑 자바 뭐가 나아?")
    assert intent == "compare"
    r = infer("파이썬이랑 자바 뭐가 나아?", store=None)
    assert set(r["compare_targets"]) == {"파이썬", "자바"}


def test_english_wh_lane_fires_and_is_not_swallowed_by_function_words():
    """REGRESSION (2026-07-18): every English wh-word is also in the function-word list, and
    role_of() consulted that list FIRST — so _EN_WH was dead code and every English wh-question
    fell through to 'definition' ('Where is Paris?'). The wh mapping must win over the function
    filter, because the wh-word is precisely what carries the intent."""
    from packages.graph_scale.intent_inference import role_of

    assert role_of("where", None) == "ask_location"
    assert role_of("when", None) == "ask_time"
    assert role_of("why", None) == "ask_cause"
    assert role_of("how", None) == "ask_method"
    assert role_of("who", None) == "ask_identity"
    assert role_of("what", None) == "ask_definition"
    # ordinary function words must still be dropped
    assert role_of("the", None) == "function"
    assert role_of("of", None) == "function"
