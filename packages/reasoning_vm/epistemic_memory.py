# -*- coding: utf-8 -*-
""" B ① — EpistemicGraph: - + - .
: docs/ATANOR_brainlike_graph_design.md. = ** " "
 .** =KNOWN, is_a =INHERITED( ), =GUESSED — 
 , "X"()↔" X"() . .
 = KNOWN ; . No LLM.

 最 1 (=), (:=) → nearest-first
 .
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from typing import Any, Optional

KNOWN, INHERITED, INFERRED, ANALOGIZED, SCHEMA, GUESSED, UNKNOWN = (
    "KNOWN", "INHERITED", "INFERRED", "ANALOGIZED", "SCHEMA", "GUESSED", "UNKNOWN")
_DECAY = 0.88


class EpistemicGraph:
    def __init__(self, schema=None, spreading: bool = True, store_lookup=None):
        self.facts: dict[tuple, dict] = {}
        self.overrides: dict[tuple, dict] = {}
        self.isa: dict[str, list[str]] = defaultdict(list)
        self.children: dict[str, list[str]] = defaultdict(list)
        self.priors: dict[str, dict] = {}
        self.schema = schema
        self.spreading = spreading
        self.store_lookup = store_lookup
        self._by_pred: dict[str, list[tuple[str, str]]] = defaultdict(list)
        self._sa = None
        self._sa_dirty = True


    def add_fact(self, s: str, p: str, o: str, sources: int = 1) -> None:
        """k- : (s,p) ( ), alts.
 → ↑."""
        key = (s, p); cur = self.facts.get(key); sources = max(1, sources)
        if cur is None:
            self.facts[key] = {"o": o, "sources": sources, "alts": {}}
        elif cur["o"] == o:
            cur["sources"] += sources
        else:
            if sources > cur["sources"]:
                cur["alts"][cur["o"]] = cur["alts"].get(cur["o"], 0) + cur["sources"]
                cur["o"], cur["sources"] = o, sources
            else:
                cur["alts"][o] = cur["alts"].get(o, 0) + sources
        self._by_pred[p].append((s, o)); self._sa_dirty = True

    def add_override(self, s: str, p: str, o: str, sources: int = 1) -> None:
        self.overrides[(s, p)] = {"o": o, "sources": max(1, sources)}
        self._by_pred[p].append((s, o)); self._sa_dirty = True

    def add_isa(self, child: str, parent: str) -> None:
        if parent not in self.isa[child]:
            self.isa[child].append(parent)
            self.children[parent].append(child)
            self._sa_dirty = True

    def _analogize(self, s: str, p: str, max_depth: int) -> Optional[tuple]:
        """L3 — s ' p ' ( )."""
        cands = self._by_pred.get(p)
        if not self.spreading or not cands:
            return None
        from packages.reasoning_vm.spreading_activation import build_assoc_from_facts
        if self._sa_dirty or self._sa is None:
            self._sa = build_assoc_from_facts(self.facts, self.isa)
            self._sa_dirty = False
        energy = self._sa.activate(s, max_steps=max_depth)
        best_o, best_e = None, 0.0
        for node, o in cands:
            e = energy.get(node, 0.0)
            if node != s and e > best_e:
                best_o, best_e = o, e
        if best_o is None:
            return None
        conf = min(0.5, 0.34 + 1.5 * best_e)
        return best_o, round(conf, 3), round(best_e, 3)

    def _override_risk(self, parent: str, p: str) -> float:
        """ = . ."""
        kids = self.children.get(parent, ())
        if not kids:
            return 0.0
        over = sum(1 for c in kids if (c, p) in self.overrides)
        return over / len(kids)

    def add_prior(self, p: str, o: str, prob: float) -> None:
        self.priors[p] = {"o": o, "prob": prob}


    def _chain(self, s: str, max_depth: int) -> list[tuple[int, str]]:
        """s + nearest-first (BFS )."""
        out, seen = [(0, s)], {s}
        q = deque([(0, s)])
        while q:
            d, node = q.popleft()
            if d >= max_depth:
                continue
            for par in self.isa.get(node, ()):
                if par not in seen:
                    seen.add(par)
                    out.append((d + 1, par))
                    q.append((d + 1, par))
        return out

    @staticmethod
    def _known_conf(sources: int) -> float:
        return min(0.99, 0.85 + 0.035 * min(sources, 5))

    def answer(self, s: str, p: str, max_depth: int = 6) -> dict[str, Any]:
        """ . nearest-first ."""
        if self.store_lookup is not None and (s, p) not in self.facts and (s, p) not in self.overrides:
            vals = self.store_lookup(s, p)
            if vals:
                o = Counter(vals).most_common(1)[0][0]
                res = self._pack(o, KNOWN, self._known_conf(len(vals)), [f"store:{s}.{p}"])
                others = [a for a, _ in Counter(vals).most_common(4) if a != o][:3]
                if others:
                    res["alternatives"] = others
                return res
        for depth, node in self._chain(s, max_depth):
            hit = self.overrides.get((node, p)) or self.facts.get((node, p))
            if hit:
                if depth == 0:
                    conf = self._known_conf(hit["sources"])
                    res = self._pack(hit["o"], KNOWN, conf, [f"{node}.{p}"])
                    alts = hit.get("alts") or {}
                    if alts:
                        res["alternatives"] = [a for a, _ in sorted(alts.items(), key=lambda kv: -kv[1])[:3]]
                    return res
                risk = self._override_risk(node, p)
                conf = self._known_conf(hit["sources"]) * (1.0 - risk) * (0.97 ** depth)
                res = self._pack(hit["o"], INHERITED, conf,
                                 [f"{node}.{p} (상속 {depth}홉, override_risk {round(risk,2)})"])
                res["via"] = node
                return res
        if self.schema is not None:
            for _, node in self._chain(s, max_depth):
                sc = self.schema.answer(node, p)
                if sc is not None:
                    return self._pack(sc["answer"], SCHEMA, sc["confidence"], sc["path"])
        ana = self._analogize(s, p, max_depth)
        if ana is not None:
            o, conf, e = ana
            return self._pack(o, ANALOGIZED, conf, [f"확산활성 유추(공활성 {e})"])
        if p in self.priors:
            pr = self.priors[p]
            return self._pack(pr["o"], GUESSED, pr["prob"], [f"prior({p})"])
        return self._pack(None, UNKNOWN, 0.0, [])

    def _pack(self, o, etype, conf, path) -> dict[str, Any]:
        return {"answer": o, "epistemic_type": etype, "confidence": round(float(conf), 3),
                "path": path, "surface": self.hedge(etype, conf, o)}

    def explain(self, s: str, p: str, max_depth: int = 6) -> dict[str, Any]:
        """ — '' . () . =."""
        r = self.answer(s, p, max_depth)
        et = r["epistemic_type"]; o = r["answer"]
        if et == KNOWN:
            why = f"'{s}'에 대해 직접 아는 사실이라 확실합니다."
        elif et == INHERITED:
            via = r.get("via", "상위 개념")
            why = f"'{s}'은(는) '{via}'의 일종이고, '{via}'은(는) 일반적으로 그러하므로 '{s}'도 그럴 것으로 봅니다(확실치는 않습니다)."
        elif et == SCHEMA:
            why = f"'{s}' 같은 상황의 전형적인 도식에서 나온 답입니다. 특정 사례를 아는 게 아니라 보통 그렇다는 것입니다."
        elif et == ANALOGIZED:
            why = f"'{s}'과(와) 연상으로 이어진 비슷한 것에서 미루어 추측했습니다. 근거가 약하니 참고만 하세요."
        elif et == GUESSED:
            why = "뚜렷한 근거 없이 일반적 경향으로 추측한 것입니다."
        else:
            why = f"'{s}'의 '{p}'에 대해서는 근거가 없어 답할 수 없습니다."
        r["why"] = why
        return r

    _NEG = {"no", "not", "false", "cannot", "can't", "never", "없", "못", "아니"}

    def verify(self, s: str, p: str, o: str, max_depth: int = 6) -> dict[str, Any]:
        """(yes/no) — . '' ' '(≠). .
 AFFIRM()·REFUTE( )·UNCONFIRMED( )·UNKNOWN( )."""
        o_n = str(o).strip().lower()
        if p in ("is_a", "isa"):
            for depth, node in self._chain(s, max_depth):
                if depth == 0:
                    continue
                if node == o_n:
                    et = KNOWN if depth == 1 else INHERITED
                    conf = 0.9 if depth == 1 else round(0.9 * (0.9 ** (depth - 1)), 3)
                    return self._verdict("AFFIRM", et, conf, s, p, o_n,
                                         [f"{s} →is_a→ {o_n} ({depth}홉)"])
            return self._verdict("UNCONFIRMED", UNKNOWN, 0.0, s, p, o_n, ["is_a 경로 없음"])
        r = self.answer(s, p, max_depth)
        if r["epistemic_type"] == UNKNOWN:
            return self._verdict("UNKNOWN", UNKNOWN, 0.0, s, p, o_n, r["path"])
        cands = {str(r["answer"]).lower()} | {str(a).lower() for a in r.get("alternatives", [])}
        if any(o_n == c or o_n in c or c in o_n for c in cands if c):
            return self._verdict("AFFIRM", r["epistemic_type"], r["confidence"], s, p, o_n, r["path"])
        if any(tok in str(r["answer"]).lower() for tok in self._NEG):
            return self._verdict("REFUTE", r["epistemic_type"], r["confidence"], s, p, o_n, r["path"])
        return self._verdict("UNCONFIRMED", r["epistemic_type"], r["confidence"], s, p, o_n,
                             r["path"], actual=r["answer"])

    def _verdict(self, verdict, etype, conf, s, p, o, path, actual=None) -> dict[str, Any]:
        surf = {"AFFIRM": {KNOWN: f"네, {o}입니다.", INHERITED: f"네, 일반적으로 그렇습니다.",
                           SCHEMA: f"네, 보통 그렇습니다.", ANALOGIZED: f"아마 그럴 것 같습니다."},
                "REFUTE": {KNOWN: f"아니요, 그렇지 않습니다.", INHERITED: f"일반적으로는 아닙니다."},
                "UNCONFIRMED": {}, "UNKNOWN": {}}
        if verdict == "AFFIRM":
            s_txt = surf["AFFIRM"].get(etype, f"네, 그런 것 같습니다.")
        elif verdict == "REFUTE":
            s_txt = surf["REFUTE"].get(etype, "아니요, 그렇지 않은 것 같습니다.")
        elif verdict == "UNCONFIRMED":
            s_txt = (f"그렇다고 확인되진 않습니다. 제가 아는 값은 '{actual}'입니다."
                     if actual else "그렇다고 확인되진 않습니다.")
        else:
            s_txt = "그건 잘 모르겠습니다."
        out = {"verdict": verdict, "epistemic_type": etype, "confidence": round(float(conf), 3),
               "surface": s_txt, "path": path, "query": {"s": s, "p": p, "o": o}}
        if actual is not None:
            out["known_value"] = actual
        return out


    @staticmethod
    def hedge(etype: str, conf: float, o: Optional[str]) -> str:
        if etype == UNKNOWN or o is None:
            return "그건 잘 모르겠습니다."
        if etype == KNOWN:
            return f"{o}입니다."
        if etype == INHERITED:
            return f"일반적으로 {o}입니다." if conf >= 0.7 else f"{o}인 것으로 보입니다."
        if etype == INFERRED:
            return f"{o}인 것으로 보입니다."
        if etype == SCHEMA:
            return f"보통 {o}입니다."
        if etype == ANALOGIZED:
            return f"비슷한 경우로 미루어 {o}일 것 같습니다."
        if etype == GUESSED:
            return f"확실치 않지만 {o} 아닐까 싶습니다."
        return f"{o}."

    def is_confabulation(self, res: dict) -> bool:
        """ = KNOWN . ( ) — ."""
        return res["epistemic_type"] == KNOWN and res["confidence"] < 0.5
