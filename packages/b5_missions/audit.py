# -*- coding: utf-8 -*-
"""The B5 audit contract + the INDEPENDENT hard-gate grader.

Every mission answer carries an AuditReport. The grader never trusts the executor's self-report: it
re-derives every gate from the claim text and the case's frozen bone table. The core faithfulness
check reuses the composer's grounding gate (content word must trace to a CITED bone) — a claim whose
text contains a word not in the bones it cites is an unsupported factual claim, and the architecture's
whole promise is that this count is zero.

Two disclosed adaptations (docs/ATANOR_b5_mission_spec_v1.md §Honest adaptations):
  ① grammar is measured on ENGLISH output (ATANOR is English-only);
  ② the native-blind-fluency Likert is human-panel-only and is reported DEFERRED, never self-scored.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from packages.grounded_composer.dual_route import grounding_gate, _content_stems
from packages.reasoning_vm.ace.match_features import tokenize

_NEG = {"not", "no", "never", "without", "none", "cannot", "n't", "un"}
_NUMISH = re.compile(r"[0-9]")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:+\-/]*")


@dataclass
class Claim:
    text: str
    bone_ids: list[str] = field(default_factory=list)


@dataclass
class AuditReport:
    case_id: str
    decision: str                       # ANSWER | PARTIAL | ABSTAIN
    route: str                          # formulaic | open | G-F3
    claims: list[Claim] = field(default_factory=list)
    blocked_uids: list[str] = field(default_factory=list)
    abstained_slots: list[str] = field(default_factory=list)   # slots the report explicitly G-F3'd

    def to_json(self) -> dict:
        return {"decision": self.decision, "route": self.route,
                "claims": [{"text": c.text, "bone_ids": c.bone_ids} for c in self.claims],
                "blocked_uids": self.blocked_uids}


@dataclass
class GateResult:
    name: str
    value: float
    threshold: float
    passed: bool
    detail: str = ""


def _numish(text: str) -> set[str]:
    # strip trailing sentence punctuation the token regex greedily swallowed (".../07." vs bone ".../07")
    return {t.rstrip(".,;:") for t in _TOKEN.findall(text) if _NUMISH.search(t)}


def _neg_markers(text: str) -> set[str]:
    toks = {w.lower() for w in tokenize(text)}
    return toks & _NEG


def _bone_text(case_bones: dict, bone_ids: list[str]) -> tuple[str, list[list[str]]]:
    cited = [case_bones[b] for b in bone_ids if b in case_bones]
    txt = " ".join(f"{s} {r} {o}" for s, r, o in cited)
    return txt, cited


def _bounded_index(text: str, needle: str) -> int | None:
    """First index of `needle` as a whole token (word-boundaried), else None. Word-boundaried so
    'event-1-1' does not spuriously match inside 'event-1-10'. Deterministic (no set iteration)."""
    if not needle:
        return None
    m = re.search(r"(?<![\w-])" + re.escape(needle) + r"(?![\w-])", text)
    return m.start() if m else None


def _direction_ok(text: str, s: str, o: str) -> bool:
    """Relation-direction preservation: if both endpoints appear verbatim, subject must precede object.
    If either endpoint isn't present verbatim, direction is indeterminate -> not a violation."""
    sl, ol = s.lower(), o.lower()
    if sl in ol or ol in sl:                             # overlapping endpoints (e.g. a self-referential
        return True                                      # repaired_by whose object contains the subject)
    low = text.lower()
    ps, po = _bounded_index(low, sl), _bounded_index(low, ol)
    if ps is None or po is None or ps == po:
        return True
    return ps < po


def _uid_loop(text: str) -> bool:
    # A UID loop is a DEGENERATE GENERATION artefact (the realizer stuck: "the the", "is a is a"),
    # measured on alphabetic tokens only. Repeated digits inside a verbatim data value (an IP octet
    # 203.0.0.113, a timestamp) are data, not a generation loop, so numeric tokens are excluded.
    toks = [w.lower() for w in tokenize(text) if w.isalpha()]
    for i in range(1, len(toks)):
        if toks[i] == toks[i - 1]:                      # immediate token repeat
            return True
    for i in range(3, len(toks)):                       # consecutive bigram repeat  a b a b
        if toks[i - 3:i - 1] == toks[i - 1:i + 1] and toks[i - 3:i - 1]:
            return True
    return False


def _grammar_errors(text: str) -> int:
    e = 0
    s = text.strip()
    if s and not s[0].isupper():
        e += 1
    if s and s[-1] not in ".!?":
        e += 1
    toks = [w.lower() for w in tokenize(s)]
    e += sum(1 for i in range(1, len(toks)) if toks[i] == toks[i - 1])   # doubled word
    return e


def _three_gram_repeat_rate(texts: list[str]) -> float:
    grams: list[tuple] = []
    for t in texts:
        toks = [w.lower() for w in tokenize(t)]
        grams += [tuple(toks[i:i + 3]) for i in range(len(toks) - 2)]
    if not grams:
        return 0.0
    return (len(grams) - len(set(grams))) / len(grams)


def grade_reports(cases: dict[str, dict], reports: list[AuditReport],
                  peak_rss_bytes: int | None = None,
                  allowed_scaffold: set[str] | None = None) -> dict[str, GateResult]:
    """cases[case_id] = {"bones": {id:[s,r,o]}, "should_abstain":[slot], "known_present":[slot]}.
    allowed_scaffold: a CLOSED, declared set of non-factual procedure verbs (close/verify/measure...)
    that may appear in plan steps -- the imperative scaffold, analogous to the connective whitelist.
    It never contains entity or value words, so it cannot license a fabricated fact."""
    scaffold_stems = _content_stems(" ".join(allowed_scaffold)) if allowed_scaffold else set()
    total_claims = faithful = unsupported = preserve_viol = 0
    uid_incidents = 0
    gram_errors = gram_words = 0
    all_texts: list[str] = []
    gf3_should = gf3_hit = 0
    known_total = known_wrong_abstain = 0

    for rep in reports:
        case = cases.get(rep.case_id, {})
        bones = case.get("bones", {})
        for c in rep.claims:
            total_claims += 1
            all_texts.append(c.text)
            btxt, cited = _bone_text(bones, c.bone_ids)
            ok, _ = grounding_gate(c.text, cited, extra_allowed=scaffold_stems) if cited else (False, {})
            if ok:
                faithful += 1
            else:
                unsupported += 1
            # numeric/time/account preservation: every digit-bearing token must be in a cited bone
            blow = btxt.lower()
            if any(n.lower() not in blow for n in _numish(c.text)):
                preserve_viol += 1
            # negation preservation: negation words in claim must be licensed by a cited bone
            elif _neg_markers(c.text) - _neg_markers(btxt):
                preserve_viol += 1
            else:
                # relation direction: if both endpoints appear verbatim, subject precedes object
                if any(not _direction_ok(c.text, s, o) for s, r, o in cited):
                    preserve_viol += 1
            if _uid_loop(c.text):
                uid_incidents += 1
            gram_errors += _grammar_errors(c.text)
            gram_words += max(1, len(tokenize(c.text)))

        abst = set(rep.abstained_slots)
        for slot in case.get("should_abstain", []):
            gf3_should += 1
            if slot in abst:
                gf3_hit += 1
        for slot in case.get("known_present", []):
            known_total += 1
            if slot in abst:
                known_wrong_abstain += 1

    def rate(num, den):
        return (num / den) if den else 0.0

    faith = rate(faithful, total_claims)
    preserve = 1.0 - rate(preserve_viol, total_claims)
    gf3_recall = rate(gf3_hit, gf3_should) if gf3_should else 1.0
    over_abst = rate(known_wrong_abstain, known_total)
    # 3-gram LOOP gate is intra-utterance (degenerate repetition inside one claim), not the natural
    # recurrence of a relation template across independent atomic claims. Gate on the worst single
    # claim; disclose the pooled cross-claim rate as an advisory (forensic register is templated).
    per_claim_tg = [_three_gram_repeat_rate([t]) for t in all_texts]
    tg = max(per_claim_tg) if per_claim_tg else 0.0
    tg_pooled = _three_gram_repeat_rate(all_texts)
    gram_per100 = rate(gram_errors, gram_words) * 100

    g: dict[str, GateResult] = {}
    g["atomic_claim_faithfulness"] = GateResult("atomic_claim_faithfulness", faith, 1.0, faith >= 1.0,
                                                f"{faithful}/{total_claims} claims traced")
    g["value_preservation"] = GateResult("value_preservation", preserve, 1.0, preserve >= 1.0,
                                          f"{preserve_viol} num/time/neg/direction violations")
    g["unsupported_claims"] = GateResult("unsupported_claims", unsupported, 0, unsupported == 0,
                                         f"{unsupported} untraceable claims (HARD)")
    g["gf3_abstention_recall"] = GateResult("gf3_abstention_recall", gf3_recall, 1.0, gf3_recall >= 1.0,
                                            f"{gf3_hit}/{gf3_should} missing-knowledge slots voiced")
    g["known_over_abstention"] = GateResult("known_over_abstention", over_abst, 0.05, over_abst <= 0.05,
                                            f"{known_wrong_abstain}/{known_total} known slots wrongly abstained")
    g["three_gram_repeat"] = GateResult("three_gram_repeat", tg, 0.02, tg < 0.02,
                                        f"worst-claim {tg:.4f}; pooled-advisory {tg_pooled:.3f} (templated register)")
    g["uid_loop"] = GateResult("uid_loop", uid_incidents, 0, uid_incidents == 0, f"{uid_incidents} loops (HARD)")
    g["english_grammar_per100w"] = GateResult("english_grammar_per100w", gram_per100, 1.0,
                                              gram_per100 <= 1.0, f"{gram_errors} err / {gram_words} words")
    if peak_rss_bytes is not None:
        gib = peak_rss_bytes / (1024 ** 3)
        g["peak_rss_gib"] = GateResult("peak_rss_gib", gib, 1.5, gib <= 1.5, f"{gib:.3f} GiB peak")
    # ② human blind fluency Likert is panel-only. passed=None (NOT True) so it never counts toward a
    #    PASS -- an unmeasured gate must not read as satisfied (audit #8).
    g["native_blind_fluency"] = GateResult("native_blind_fluency", -1.0, 4.0, None,  # type: ignore[arg-type]
                                           "DEFERRED -- blind human panel (B6-style), not machine-scored")
    return g


def print_gates(g: dict[str, GateResult]) -> bool:
    all_pass = True
    for r in g.values():
        if r.passed is None:                             # deferred / unmeasured -> shown, never counted
            print(f"  [DEFER] {r.name:28s} {r.detail}")
            continue
        mark = "PASS" if r.passed else "FAIL"
        if not r.passed:
            all_pass = False
        print(f"  [{mark}] {r.name:28s} {r.value:.4f} (thr {r.threshold})  {r.detail}")
    return all_pass
