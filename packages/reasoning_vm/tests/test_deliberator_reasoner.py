# -*- coding: utf-8 -*-
"""DELIBERATOR reasoner surfaces + the controlled probe gate. The probe is the deliverable proof the
System-2 engine FIRES: with the required facts present, it derives the correct multi-step answer and
never fabricates on the negative controls."""
from packages.reasoning_vm.deliberator.controlled_probe import build_probe_kb, run_probe
from packages.reasoning_vm.deliberator.reasoner import Deliberator


def _dlb():
    fa, ip, custom = build_probe_kb()
    d = Deliberator(fa, inherit_props=ip, with_kernels=True, max_depth=6)
    d.chainer.rules = d.chainer.rules + custom
    return d


def test_derive_path_explicit_chain():
    d = _dlb()
    # busan -> south_korea -> asia -> earth : three explicit hops
    out = d.derive_path("busan", ["located_in", "located_in", "located_in"])
    assert out["answer"] == "earth" and out["fired"]
    # two hops stop one bridge earlier, at the continent
    assert d.derive_path("busan", ["located_in", "located_in"])["answer"] == "asia"


def test_answer_mcq_object_picks_provable_continent():
    d = _dlb()
    out = d.answer_mcq_object("seoul", "located_in",
                              {"A": "asia", "B": "europe", "C": "africa", "D": "antarctica"})
    assert out["choice_key"] == "A" and out["mode"] == "grounded"


def test_answer_mcq_prove_membership_multihop():
    d = _dlb()
    # socrates is a human only via is_a*: philosopher -> human
    out = d.answer_mcq_prove("is_a", "human",
                             {"A": "whale", "B": "socrates", "C": "shark", "D": "paris"})
    assert out["choice_key"] == "B"
    assert out["hops"] >= 2 and out["fired"] is True
    assert out["proof"] is not None and out["trail"]


def test_answer_mcq_derive_kernel_answer():
    d = _dlb()
    out = d.answer_mcq_derive("chloride_ion", "net_charge",
                              {"A": "0", "B": "+2", "C": "-1", "D": "-3"})
    assert out["choice_key"] == "C" and out["mode"] == "grounded"


def test_answer_mcq_derive_rational_fraction_matches_only_exact_decimal(tmp_path, monkeypatch):
    from packages.reasoning_vm.deliberator import kernel_forge as KF
    from packages.reasoning_vm.deliberator.back_chain import KernelBinding

    monkeypatch.setattr(KF, "REGISTRY", tmp_path / "registry.json")
    train = [
        ({"x": "1", "y": "2"}, "1/2"),
        ({"x": "2", "y": "4"}, "1/2"),
        ({"x": "3", "y": "6"}, "1/2"),
    ]
    holdout = [
        ({"x": "4", "y": "8"}, "1/2"),
        ({"x": "5", "y": "10"}, "1/2"),
    ]
    assert KF.forge(
        "ratio", train, ["x", "y"], dsl=KF.RATIONAL_DSL,
        holdout_examples=holdout, max_nodes=5,
    )["accepted"]

    kg = {"sample": [("sample", "x_value", "1"), ("sample", "y_value", "2")]}
    d = Deliberator(
        lambda subject: kg.get(subject, []),
        kernels=[KernelBinding(
            "ratio_value", [("x_value", "x"), ("y_value", "y")], "ratio",
        )],
        with_kernels=False,
    )
    derived = d.derive("sample", "ratio_value")
    assert derived["answer"] == "1/2"
    out = d.answer_mcq_derive(
        "sample", "ratio_value", {"A": "0.5000000001", "B": "0.5"},
    )
    assert out["choice_key"] == "B" and out["mode"] == "grounded"


def test_answer_mcq_derive_abstains_on_duplicate_exact_numeric_choices(monkeypatch):
    d = _dlb()
    monkeypatch.setattr(
        d, "derive",
        lambda _subject, _relation: {
            "answer": "1/2", "fired": True, "hops": 1, "proof": None, "trail": None,
        },
    )
    out = d.answer_mcq_derive(
        "sample", "ratio_value", {"A": "0.5", "B": "1/2", "C": "0.5000000001"},
    )
    assert out["choice_key"] is None and out["mode"] == "abstain"


def test_answer_mcq_derive_numeric_tokens_never_use_loose_punctuation_matching(monkeypatch):
    d = _dlb()

    def derived(answer):
        return lambda _subject, _relation: {
            "answer": answer, "fired": True, "hops": 1, "proof": None, "trail": None,
        }

    # Loose punctuation normalization used to collapse "1.0" to "10" and select A by list order.
    monkeypatch.setattr(d, "derive", derived("10"))
    out = d.answer_mcq_derive("sample", "value", {"A": "1.0", "B": "10"})
    assert out["choice_key"] == "B"

    monkeypatch.setattr(d, "derive", derived("9007199254740993"))
    out = d.answer_mcq_derive(
        "sample", "value", {"A": "9007199254740992", "B": "9007199254740993"},
    )
    assert out["choice_key"] == "B"

    # Conventional thousands separators retain legacy display compatibility, but malformed grouping
    # is never stripped into a different number.
    monkeypatch.setattr(d, "derive", derived("1000"))
    out = d.answer_mcq_derive(
        "sample", "value", {"A": "1,00", "B": "1,000", "C": "999.999999999"},
    )
    assert out["choice_key"] == "B"
    malformed = d.answer_mcq_derive("sample", "value", {"A": "1,00"})
    assert malformed["choice_key"] is None and malformed["mode"] == "abstain"


def test_answer_mcq_derive_compares_exact_values_and_units(monkeypatch):
    from packages.reasoning_vm.deliberator.reasoner import _as_exact_quantity

    d = _dlb()

    def derived(answer):
        return lambda _subject, _relation: {
            "answer": answer, "fired": True, "hops": 1, "proof": None, "trail": None,
        }

    monkeypatch.setattr(d, "derive", derived("10 m"))
    out = d.answer_mcq_derive("sample", "length", {"A": "1.0 m", "B": "10 m"})
    assert out["choice_key"] == "B"

    monkeypatch.setattr(d, "derive", derived("1e3 Hz"))
    out = d.answer_mcq_derive("sample", "frequency", {"A": "999 Hz", "B": "1000 Hz"})
    assert out["choice_key"] == "B"

    monkeypatch.setattr(d, "derive", derived("1 m"))
    out = d.answer_mcq_derive("sample", "length", {"A": "100 cm", "B": "1 s"})
    assert out["choice_key"] == "A"

    monkeypatch.setattr(d, "derive", derived("1"))
    out = d.answer_mcq_derive("sample", "value", {"A": "1 m", "B": "1 s"})
    assert out["choice_key"] is None and out["mode"] == "abstain"

    for invalid in ("1e5000", "1/0", "nan", "9" * 8193):
        assert _as_exact_quantity(invalid) is None


def test_mcq_abstains_when_none_provable():
    d = _dlb()
    out = d.answer_mcq_prove("is_a", "reptile",
                             {"A": "whale", "B": "socrates", "C": "shark", "D": "paris"})
    assert out["choice_key"] is None and out["mode"] == "abstain"


def test_mcq_adapter_grounds_multihop_membership():
    # the exam-cascade adapter grounds 'which is a <category>' by proof-verified transitive is_a
    from packages.reasoning_vm.deliberator.mcq_adapter import engine_pick
    kg = {"whale": [("whale", "is_a", "cetacean")], "cetacean": [("cetacean", "is_a", "mammal")],
          "shark": [("shark", "is_a", "fish")], "tuna": [("tuna", "is_a", "fish")]}
    out = engine_pick("Which of the following is a mammal?",
                      {"A": "shark", "B": "whale", "C": "tuna", "D": "octopus"}, lambda s: kg.get(s, []))
    assert out is not None and out["choice_key"] == "B" and out["mode"] == "grounded"


def test_mcq_adapter_abstains_off_category():
    from packages.reasoning_vm.deliberator.mcq_adapter import engine_pick
    assert engine_pick("Compute the pH of the buffer.",
                       {"A": "1", "B": "2", "C": "3", "D": "4"}, lambda s: []) is None


# ── the probe gate — locks the engine's measured firing rate & 작화0 ────────────────────────────
def test_controlled_probe_engine_fires_and_never_fabricates():
    r = run_probe()
    assert r["scope"] == "bounded_structured_engine_integrity"
    assert r["natural_language_compiler_exercised"] is False
    assert r["grounded_firing_rate"] == 1.0        # every positive derives a verified answer
    assert r["multistep_firing_rate"] == 1.0       # every one is a genuine multi-step chain
    assert r["reasoning_accuracy"] == 1.0          # and each derived answer is correct
    assert r["negative_abstention_rate"] == 1.0    # every facts-absent control abstains
    assert r["fabrications"] == []                 # 작화0: not one fabricated chain


def test_controlled_probe_mcq_telemetry_is_never_hardcoded():
    """The probe must preserve a reasoner's actual proof depth and firing verdict."""
    from packages.reasoning_vm.deliberator.controlled_probe import _run_item

    class _Stub:
        def answer_mcq_prove(self, _relation, _target, _choices):
            return {
                "choice_key": "B",
                "hops": 0,
                "fired": False,
                "trail": "stubbed single-step result",
            }

    item = {
        "kind": "mcq_prove",
        "args": ("is_a", "human"),
        "choices": {"A": "whale", "B": "socrates"},
        "gold": "B",
    }
    result = _run_item(_Stub(), item)
    assert result["answered"] is True and result["correct"] is True
    assert result["hops"] == 0
    assert result["fired"] is False
