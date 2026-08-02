# -*- coding: utf-8 -*-
"""Block-universe view: time spatialized over the ONE timeline + learned phase field.
Look down / project forward / branch / infer backward — every leap hypothesis-flagged."""
from packages.temporal_reasoning.block_universe import BlockUniverse
from packages.temporal_reasoning.precedence_field import PrecedenceField
from packages.temporal_reasoning.unified_timeline import Timeline


def _toy_field() -> PrecedenceField:
    # a tiny learned-shaped field: plant < grow < harvest < eat (phases ascending), seen>=3 each
    return PrecedenceField(
        phase={"plant": -0.9, "grow": -0.3, "harvest": 0.3, "eat": 0.9},
        seen={"plant": 5, "grow": 5, "harvest": 5, "eat": 5})


def _tl() -> Timeline:
    tl = Timeline()
    tl.record("perception", "the farmer began to plant the field", who="camera")
    tl.record("fact", "the crops grow through spring")
    return tl


def test_look_down_surveys_the_whole_line_with_both_coordinates():
    bu = BlockUniverse(_tl(), _toy_field())
    v = bu.look_down()
    assert v["n_events"] == 2 and v["span_utc"] is not None
    phased = [e for e in v["events"] if e["phase"] is not None]
    assert phased, "events with known tokens carry a causal-phase coordinate (time as space)"


def test_project_forward_walks_the_learned_field_and_flags_hypotheses():
    bu = BlockUniverse(_tl(), _toy_field())
    proj = bu.project_forward(horizon=2)
    assert proj, "field knows what canonically follows grow"
    assert [p["event_token"] for p in proj] == ["harvest", "eat"]     # learned order, not hardcoded
    assert all(p["hypothesis"] is True for p in proj)                  # a leap is flagged, never asserted
    assert all(p["confidence"] is None or 0 <= p["confidence"] <= 1 for p in proj)


def test_branches_lays_alternative_futures_side_by_side():
    bu = BlockUniverse(_tl(), _toy_field())
    br = bu.branches(["grow", "harvest", "unknownthing"], depth=2)
    known = [b for b in br if b["known"]]
    assert len(known) == 2 and all(b["hypothesis"] for b in br)
    assert known[0]["score"] is not None                               # ranked by field confidence
    unknown = [b for b in br if not b["known"]]
    assert unknown and unknown[0]["path"] == []                        # honest: unknown stays empty


def test_infer_backward_is_time_symmetric_with_uncertainty():
    bu = BlockUniverse(_tl(), _toy_field())
    back = bu.infer_backward("harvest", k=2)
    assert back and back[0]["event_token"] in ("grow", "plant")        # reverse walk of same field
    assert all(b["hypothesis"] is True for b in back)
    # timeline evidence is cited when the inferred precursor was actually observed
    grow_row = [b for b in back if b["event_token"] == "grow"]
    assert not grow_row or grow_row[0]["observed_on_timeline"], "observed precursor cites its events"


def test_render_human_narrates_on_single_axis_with_hedges():
    bu = BlockUniverse(_tl(), _toy_field())
    text = bu.render_human(projections=bu.project_forward(horizon=1),
                           backward=bu.infer_backward("harvest", k=1))
    assert "projection, not a certainty" in text                       # kind single-axis narration,
    assert "not a record" in text                                      # hypotheses stay marked


def test_no_field_degrades_honestly():
    bu = BlockUniverse(_tl(), None)
    assert bu.project_forward() == [] and bu.branches(["x"]) == [] and bu.infer_backward("x") == []


def test_real_trained_field_integration_if_present():
    f = PrecedenceField.load()
    if f is None:
        return                                                          # environment without artifact
    tl = Timeline()
    tl.record("fact", "they plant the seeds in early spring")
    bu = BlockUniverse(tl, f)
    proj = bu.project_forward(horizon=2)
    assert all(p["hypothesis"] for p in proj)                           # flag holds on the real field
