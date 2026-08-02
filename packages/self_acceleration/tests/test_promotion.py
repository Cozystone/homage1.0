# -*- coding: utf-8 -*-
"""H4 v3 operator-signed promotion — fast, ISOLATED invariants (temp bank; no synthesis).

Locks that `promotion.promote` is ADDITIVE (never drops existing recipes), IDEMPOTENT (a re-run adds
nothing), stamps OPERATOR PROVENANCE, and round-trips the failure signature. The heavy end-to-end
promotion (running the coupled flywheel + writing the real bank) is done operationally, not in CI; here we
monkeypatch the record source so the invariants are checked in milliseconds against a temp bank file."""
from __future__ import annotations

import json

import numpy as np

from packages.self_acceleration import promotion as P
from packages.meta_diagnosis import recipe_ledger as bank


def _fake_records():
    sig = np.exp(1j * np.linspace(0.0, 1.0, 8))
    return ([
        {"signature": sig, "wall": "sum_minus_min",
         "scheme": {"family": "computed_projection", "depth": 2, "aux": ["min2", "add"],
                    "out_step_template": None}},
        {"signature": sig, "wall": "second_max",
         "scheme": {"family": "projection_chain", "depth": 2, "out_step_template": [["get_rel", 0]]}},
    ], {"walls_crossed": 2, "walls_total": 2})


def test_scheme_label():
    assert P._scheme_label({"family": "projection_chain", "depth": 3}) == "projection_chain(depth=3)"
    assert P._scheme_label({"family": "computed_projection", "aux": ["min2", "add"]}) == \
        "computed_projection({min2,add})"


def test_promotion_additive_idempotent_provenance(tmp_path, monkeypatch):
    bankfile = tmp_path / "recipes.json"
    # a pre-existing (non-v3) recipe must survive the promotion untouched (ADDITIVE)
    bank.add_recipe(failure_signature=[1.0, 0.0, 2.0, 0.0], cluster_label="colour-only",
                    module_name="pre_existing", module_desc="{}", lift_before=0.0, lift_after=1.0,
                    task_ids_fixed=["t"], notes="pre", ts="2026-07-23", path=bankfile)
    monkeypatch.setattr(P, "build_v3_ledger_records", lambda seed=7: _fake_records())

    a = P.promote(operator="op", approved="2026-07-24", ts="2026-07-24", path=bankfile,
                  sibling_backup=False)
    recs = bank.all_recipes(bankfile)
    assert a["total_before"] == 1 and a["total_after"] == 3 and len(recs) == 3
    assert any(r["module_name"] == "pre_existing" for r in recs)          # existing preserved (additive)
    v3 = [r for r in recs if r["cluster_label"] == P.CLUSTER_LABEL]
    assert len(v3) == 2
    for r in v3:                                                          # operator provenance stamped
        d = json.loads(r["module_desc"])
        assert d["operator"] == "op" and d["approved"] == "2026-07-24"
        assert d["source_commit"] == P.SOURCE_COMMIT and d["capability"] == P.CAPABILITY
        assert "promo_id" in d and "scheme" in d
        assert bank.recipe_signature(r).size > 0 and np.iscomplexobj(bank.recipe_signature(r))  # round-trip
        assert r["lift_after"] == 1.0 and r["task_ids_fixed"]

    a2 = P.promote(operator="op", approved="2026-07-24", ts="2026-07-24", path=bankfile,
                   sibling_backup=False)                                  # IDEMPOTENT
    assert len(a2["added"]) == 0 and len(a2["skipped"]) == 2
    assert len(bank.all_recipes(bankfile)) == 3


def test_promotion_no_exec_or_eval():
    src = open(P.__file__, encoding="utf-8").read()
    assert "exec(" not in src and "eval(" not in src
