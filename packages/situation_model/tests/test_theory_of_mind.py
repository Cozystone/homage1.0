# -*- coding: utf-8 -*-
"""Theory-of-Mind organ: a per-agent belief shadow over the world state.

The reality tracker follows where things ARE; belief[agent][X] follows where each agent last SAW X.
An UNWITNESSED move makes belief diverge from reality (that divergence is the false belief); an agent
never co-present with X has no grounded belief and must ABSTAIN — never guess reality-as-belief.

These tests pin the three organs the ToM benchmark exposed as missing: a presence timeline
(enter/leave per scene), a witnessed-only belief map, and second-order nesting — plus the honesty
floor and the invariant that none of this perturbs the reality tracker.
"""
from packages.situation_model.builder import build
from packages.situation_model.reasoner import answer


def _ans(text, q):
    return answer(q, build(text))


# ---- witnessed vs unwitnessed move: belief diverges from reality (copula surface) ----
def test_copula_false_belief_diverges_from_reality():
    t = ("Nadia and Bem were together in the greenhouse. The quill was in the crate. "
         "Nadia stepped out of the greenhouse. Bem lingered in the greenhouse. "
         "The quill was in the urn.")
    st = build(t).state
    # reality intact: the quill really moved to the urn
    assert st.where_is("quill")[0] == "urn"
    # Nadia left BEFORE the move -> still believes the old place; Bem witnessed -> tracks reality
    assert st.believes("Nadia", "quill")[0] == "crate"
    assert st.believes("Bem", "quill")[0] == "urn"
    # and through the reasoner (two phrasings of the same first-order belief question)
    assert _ans(t, "Where does Nadia think the quill is?")["answer"] == "crate"
    assert _ans(t, "Where will Nadia look for the quill?")["answer"] == "crate"
    # a reality question is NOT intercepted by the belief route -> still answers reality
    assert _ans(t, "Where is the quill?")["answer"] == "urn"


# ---- witnessed vs unwitnessed move: agent-carry surface ----
def test_agent_carry_false_belief_diverges():
    t = ("Orin took the gem. Orin went to the sack. Orin put down the gem. Orin left the sack. "
         "Sela picked up the gem. Sela walked to the locker. Sela dropped the gem.")
    st = build(t).state
    assert st.where_is("gem")[0] == "locker"            # reality: carried on to the locker
    assert st.believes("Orin", "gem")[0] == "sack"      # Orin left before the move
    assert st.believes("Sela", "gem")[0] == "locker"    # Sela carried it there
    assert _ans(t, "Where will Orin look for the gem?")["answer"] == "sack"


# ---- true belief: witnessing the move -> belief tracks reality (must not merely echo reality) ----
def test_true_belief_tracks_reality_when_witnessed():
    t = ("Pax and Juno were together in the pantry. The coin was in the tin. "
         "Pax remained in the pantry the whole time. The coin was in the jar.")
    assert _ans(t, "Where does Pax think the coin is?")["answer"] == "jar"   # Pax saw the move


# ---- co-presence timeline records enter/leave over the story ----
def test_presence_timeline_records_enter_and_leave():
    t = ("Nadia and Bem were together in the greenhouse. The quill was in the crate. "
         "Nadia stepped out of the greenhouse. Bem lingered in the greenhouse.")
    w = build(t).state.w
    ev = [(a, kind) for _, a, kind, _ in w.presence_log]
    assert ("nadia", "present") in ev and ("bem", "present") in ev
    assert ("nadia", "leave") in ev
    assert ("bem", "leave") not in ev            # Bem never left
    assert w.present == {"bem"}                  # only Bem remains in the active scene


# ---- honesty floor: abstain when the agent was never co-present with the object ----
def test_abstains_when_never_co_present():
    # Vesna is off in the garden the whole time; the gem is only ever placed in the vault by Coby
    t = ("Vesna went to the garden. Coby took the gem. Coby went to the vault. Coby put down the gem.")
    st = build(t).state
    assert st.believes("Vesna", "gem") is None            # never saw the gem -> ungrounded
    out = _ans(t, "Where does Vesna think the gem is?")
    assert out["answer"] is None                          # abstain, do NOT guess 'vault'
    assert st.believes("Coby", "gem")[0] == "vault"       # Coby did witness it


# ---- second-order: copula (co-present) is grounded; agent-carry (sequential) abstains honestly ----
def test_second_order_copula_grounded():
    t = ("Coby and Lio worked side by side in the cellar. The coin was in the casket. "
         "Coby walked out of the cellar. Lio stayed behind quietly. The coin was in the tin.")
    # Lio saw Coby see the coin at the casket, then saw Coby leave before the move ->
    # Lio thinks Coby still expects it at the casket
    assert _ans(t, "Where does Lio think that Coby will look for the coin?")["answer"] == "casket"


def test_second_order_agent_carry_abstains():
    # Yara and Orin are never co-present; Orin has no model of Yara's belief -> honest abstain
    t = ("Yara picked up the quill. Yara went to the kettle. Yara dropped the quill. "
         "Yara went home for a while. Orin took the quill. Orin went to the bucket. "
         "Orin dropped the quill.")
    assert _ans(t, "Where does Orin think that Yara will look for the quill?")["answer"] is None


# ---- invariant: the belief layer must NOT perturb the reality tracker ----
def test_reality_tracker_untouched_by_belief_layer():
    t = ("Nadia and Bem were together in the greenhouse. The quill was in the crate. "
         "Nadia stepped out of the greenhouse. The quill was in the urn.")
    w = build(t).state.w
    assert w.loc["quill"] == "urn"                                   # loc follows reality
    assert [l for _, l, _ in w.traj["quill"]] == ["crate", "urn"]    # trajectory memory intact
