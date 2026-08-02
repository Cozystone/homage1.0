# -*- coding: utf-8 -*-
"""Self-repair safety — the properties that make an autonomous repair loop trustworthy.

These are adversarial: each test is a way the loop could be turned against itself (edit the
examiner, patch the gate, land an ambiguous anchor, leave a broken file behind) and asserts the
loop refuses. A repair loop without these is a self-destruct button on a timer."""
from __future__ import annotations

import json

import packages.self_repair.defect_ledger as dl
import packages.self_repair.patch_protocol as pp
import packages.self_repair.repair_cycle as rc
from packages.continuous_self.auto_self_modification import touches_constitution


def _patch(path: str, old: str, new: str) -> str:
    return f"FILE: {path}\nOLD:\n<<<\n{old}\n>>>\nNEW:\n<<<\n{new}\n>>>"


# ---------- the wireheading guard: the examiner is immutable ----------

def test_tests_are_constitutionally_immutable():
    """A subject that may edit its own examiner has no gate. Every shape of test path is caught."""
    for p in ("packages/brain_link/tests/test_conversation.py",
              "packages/self_repair/tests/test_repair_safety.py",
              "tests/test_top_level.py",
              "packages/foo/bar_test.py"):
        assert touches_constitution([p]), p
    # ordinary body code stays modifiable — the guard is narrow, not a blanket freeze
    assert not touches_constitution(["packages/realizer_struct/frame_realizer.py"])


def test_patch_editing_a_test_is_refused(tmp_path):
    edit, why = pp.parse_patch(_patch("packages/brain_link/tests/test_conversation.py",
                                      "assert x == 1", "assert True"))
    assert edit is not None, why
    assert "immutable" in pp.check_eligible(edit)


def test_patch_editing_the_gate_itself_is_refused():
    edit, _ = pp.parse_patch(_patch("packages/continuous_self/auto_self_modification.py",
                                    "if hits:", "if False:"))
    assert edit is not None
    assert "immutable" in pp.check_eligible(edit)


def test_patch_editing_the_repair_organ_is_refused():
    edit, _ = pp.parse_patch(_patch("packages/self_repair/patch_protocol.py",
                                    "MAX_EDIT_BYTES = 4000", "MAX_EDIT_BYTES = 999999"))
    assert edit is not None
    assert "no-repair set" in pp.check_eligible(edit)


# ---------- anchor safety: no ambiguous or stale application ----------

def test_ambiguous_anchor_is_refused(tmp_path, monkeypatch):
    f = tmp_path / "packages" / "x" / "m.py"
    f.parent.mkdir(parents=True)
    f.write_text("a = 1\nb = 1\n", encoding="utf-8")   # '= 1' occurs twice
    monkeypatch.setattr(pp, "REPO", tmp_path)
    edit, _ = pp.parse_patch(_patch("packages/x/m.py", "= 1", "= 2"))
    assert "appears 2 times" in pp.check_eligible(edit)


def test_stale_anchor_is_refused(tmp_path, monkeypatch):
    f = tmp_path / "packages" / "x" / "m.py"
    f.parent.mkdir(parents=True)
    f.write_text("a = 1\n", encoding="utf-8")
    monkeypatch.setattr(pp, "REPO", tmp_path)
    edit, _ = pp.parse_patch(_patch("packages/x/m.py", "z = 99", "z = 100"))
    assert "does not appear" in pp.check_eligible(edit)


def test_syntax_breaking_patch_never_reaches_disk(tmp_path, monkeypatch):
    f = tmp_path / "packages" / "x" / "m.py"
    f.parent.mkdir(parents=True)
    original = "def f():\n    return 1\n"
    f.write_text(original, encoding="utf-8")
    monkeypatch.setattr(pp, "REPO", tmp_path)
    edit, _ = pp.parse_patch(_patch("packages/x/m.py", "    return 1", "    return ((("))
    assert "would not parse" in pp.check_eligible(edit)
    assert f.read_text(encoding="utf-8") == original      # untouched


def test_path_traversal_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(pp, "REPO", tmp_path)
    edit, why = pp.parse_patch(_patch("packages/../../etc/x.py", "a", "b"))
    if edit is not None:
        assert pp.check_eligible(edit)                    # some refusal, never empty
    # scope check alone already rejects anything not under packages/
    e2, _ = pp.parse_patch(_patch("scripts/roam_daemon.py", "a", "b"))
    assert "outside the repair scope" in pp.check_eligible(e2)


def test_malformed_and_oversized_replies_are_rejected():
    assert pp.parse_patch("just prose, no patch here")[0] is None
    assert pp.parse_patch(_patch("packages/x/m.py", "", "new"))[0] is None       # anchorless
    assert pp.parse_patch(_patch("packages/x/m.py", "same", "same"))[0] is None  # no-op
    big = "x" * (pp.MAX_EDIT_BYTES + 1)
    assert pp.parse_patch(_patch("packages/x/m.py", big, "y"))[0] is None        # rewrite, not fix


# ---------- staging: a rejected or crashing judgement always restores ----------

def _staging_file(tmp_path, monkeypatch):
    f = tmp_path / "packages" / "x" / "m.py"
    f.parent.mkdir(parents=True)
    f.write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.setattr(pp, "REPO", tmp_path)
    return f


def test_rejected_patch_is_restored_byte_for_byte(tmp_path, monkeypatch):
    f = _staging_file(tmp_path, monkeypatch)
    original = f.read_text(encoding="utf-8")
    monkeypatch.setattr(rc, "run_tests", lambda timeout_s=600: (False, "1 failed", {"t::a"}))
    edit, _ = pp.parse_patch(_patch("packages/x/m.py", "VALUE = 1", "VALUE = 2"))
    out = rc.stage_and_judge(edit, {"child_battery": 1.0})
    assert out["allow"] is False and "not green" in out["reason"]
    assert f.read_text(encoding="utf-8") == original


def test_regressing_patch_is_restored(tmp_path, monkeypatch):
    f = _staging_file(tmp_path, monkeypatch)
    original = f.read_text(encoding="utf-8")
    monkeypatch.setattr(rc, "run_tests", lambda timeout_s=600: (True, "ok", set()))
    monkeypatch.setattr(rc, "live_battery", lambda: {"child_battery": 0.80})   # dropped
    edit, _ = pp.parse_patch(_patch("packages/x/m.py", "VALUE = 1", "VALUE = 2"))
    out = rc.stage_and_judge(edit, {"child_battery": 0.95})
    assert out["allow"] is False and out["regressions"]
    assert f.read_text(encoding="utf-8") == original


def test_crash_during_judgement_still_restores(tmp_path, monkeypatch):
    f = _staging_file(tmp_path, monkeypatch)
    original = f.read_text(encoding="utf-8")

    def _boom(timeout_s=600):
        raise RuntimeError("judgement exploded")

    monkeypatch.setattr(rc, "run_tests", _boom)
    edit, _ = pp.parse_patch(_patch("packages/x/m.py", "VALUE = 1", "VALUE = 2"))
    try:
        rc.stage_and_judge(edit, {})
    except RuntimeError:
        pass
    assert f.read_text(encoding="utf-8") == original      # `finally` did its job


def test_allowed_patch_is_kept(tmp_path, monkeypatch):
    f = _staging_file(tmp_path, monkeypatch)
    monkeypatch.setattr(rc, "run_tests", lambda timeout_s=600: (True, "ok", set()))
    monkeypatch.setattr(rc, "live_battery", lambda: {"child_battery": 0.95})
    edit, _ = pp.parse_patch(_patch("packages/x/m.py", "VALUE = 1", "VALUE = 2"))
    out = rc.stage_and_judge(edit, {"child_battery": 0.95})
    assert out["allow"] is True
    assert f.read_text(encoding="utf-8") == "VALUE = 2\n"   # the repair stands


# ---------- the ledger: repetition is the priority signal ----------

def test_repeated_defect_outranks_a_one_off(tmp_path, monkeypatch):
    src = tmp_path / "reviews.jsonl"
    rows = [{"critique": "1. The demonym german should be capitalized in the realizer output."},
            {"critique": "1. A nationality adjective german must be capitalized, it reads wrong."},
            {"critique": "1. The demonym german is lowercase and that is not native English."},
            {"critique": "1. Some entirely separate cosmetic spacing nitpick about blank lines."}]
    src.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    monkeypatch.setattr(dl, "SOURCES", (src,))
    monkeypatch.setattr(dl, "LOG", tmp_path / "defects.jsonl")
    # this test is about RANKING BY RECURRENCE, so it reads the whole ledger; the separate
    # repairability filter is exercised in test_abstract_critique_is_not_a_repair_target
    top = dl.top_defect(require_repairable=False)
    assert top is not None and top.sightings >= 2, top
    assert "german" in top.key or any("german" in q for q in top.quotes)
    # once attempted, the loop advances to the next fault instead of retrying forever
    dl.journal(top, "rejected", "no fix survived", now_utc=1.0)
    assert top.key in dl.attempted_keys()
    nxt = dl.top_defect(exclude_keys=dl.attempted_keys(), require_repairable=False)
    assert nxt is None or nxt.key != top.key


def test_abstract_critique_is_not_a_repair_target(tmp_path, monkeypatch):
    """Discovered live: the most-repeated defect was 'a clean instance of the Chinese-room context
    problem' (5 sightings) and the advisor correctly answered NO PATCH — no edit follows from a
    philosophical observation. Recurrence says what matters; concreteness says what is actionable."""
    src = tmp_path / "reviews.jsonl"
    abstract = ("This is a clean instance of the Chinese room context problem where symbols are "
                "processed without the surrounding situation that fixes their sense entirely.")
    concrete = ("The demonym german should be capitalized in the realizer, so \"Einstein is a "
                "german physicist\" reads wrong to any native speaker of the language.")
    # real comprehensive_review rows carry the file they were reviewing; the dialogue coach's do
    # not — which is exactly what separates an actionable report from a floating observation
    rows = ([{"critique": abstract}] * 4 +
            [{"critique": concrete, "source": "packages/realizer_struct/frame_realizer.py"}] * 2)
    src.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    monkeypatch.setattr(dl, "SOURCES", (src,))
    monkeypatch.setattr(dl, "LOG", tmp_path / "defects.jsonl")
    every = dl.collect()
    top_overall = every[0]
    assert top_overall.sightings == 4 and not top_overall.repairable   # most-repeated, unactionable
    picked = dl.top_defect()                                           # what the loop will work on
    assert picked is not None and picked.repairable and picked.sightings == 2
    assert any("german" in q for q in picked.quotes)
    assert picked.hints == ["packages/realizer_struct/frame_realizer.py"]   # a place to cut
    # the abstract one is not discarded — it stays visible for design guidance
    assert dl.top_defect(require_repairable=False).sightings == 4


def test_multiline_anchor_is_refused():
    """The advisor transport flattens newlines, so a multi-line anchor cannot survive the round
    trip verbatim and would never match. Single-line anchors also keep the blast radius small."""
    edit, why = pp.parse_patch(_patch("packages/x/m.py", "line one\nline two", "fixed"))
    assert edit is None and "single line" in why


def test_request_carries_the_real_file_so_an_anchor_can_be_copied(tmp_path, monkeypatch):
    """The first live cycle drew NO PATCH because the advisor had never seen the file and so could
    not produce a verbatim anchor. The request must ship the source it is asking about."""
    import packages.self_repair.repair_cycle as rcm
    f = tmp_path / "packages" / "realizer_struct" / "frame_realizer.py"
    f.parent.mkdir(parents=True)
    f.write_text("MARKER_LINE = 'findable'\n", encoding="utf-8")
    monkeypatch.setattr(rcm, "REPO", tmp_path)
    d = dl.Defect(key="k", sightings=3, quotes=["a defect"],
                  hints=["packages/realizer_struct/frame_realizer.py"])
    req = rcm.build_request(d)
    assert "MARKER_LINE = 'findable'" in req            # the anchor is copyable from the request
    assert "SINGLE LINE" in req and "NO PATCH" in req   # the contract is stated


def test_parser_accepts_transport_sanitized_fences():
    """A real live patch arrived fenced in '‹‹‹' because the advisor transport sanitizes cmd
    metacharacters — including the '<' of the '<<<' the format itself asked for. A well-formed
    edit must not be lost to a mangled delimiter."""
    for fence in ("@@@", "<<<", "‹‹‹"):
        reply = (f"FILE: packages/x/m.py\nOLD:\n{fence}\nVALUE = 1\n{fence}\n"
                 f"NEW:\n{fence}\nVALUE = 2\n{fence}")
        edit, why = pp.parse_patch(reply)
        assert edit is not None, (fence, why)
        assert edit.old == "VALUE = 1" and edit.new == "VALUE = 2"
    assert "@@@" in pp.PATCH_FORMAT and "<<<" not in pp.PATCH_FORMAT   # ask for the safe one
