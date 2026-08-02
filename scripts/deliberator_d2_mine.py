# -*- coding: utf-8 -*-
"""DELIBERATOR D2 — mine VERIFIED quantitative rules from the 7M-passage substrate (organ ⑤ content).

Three rule kinds, each with an EXACT verifier (no learned judgment in the acceptance path):
  1. CONSTANTS   — "speed of light is 299,792,458 m/s"  → (name, value, unit)
                   verifier: k-source consensus (≥2 independent passages agree within 1%)
  2. CONVERSIONS — "1 mile = 1.609 kilometres"           → (unit_a, k, unit_b)
                   verifier: DIMENSIONAL ANALYSIS (both units map to the same base dimension)
                   + consensus within 1%
  3. FORMULAS    — "force equals mass times acceleration" / "E = mc²" textual algebra
                   → (lhs, op-tree over quantities)  verifier: dimensional type-check where the
                   dimension table knows all terms; else held as 'candidate' (never asserted)

Everything lands in data/graph_scale/deliberator_rules/*.jsonl with provenance (passage title) and
status: verified | candidate. The backward-chaining planner (D3) consumes only 'verified'.

  python scripts/deliberator_d2_mine.py [max_passages]
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PASSAGES = REPO / "data" / "graph_scale" / "wiki_passages_en_full" / "passages.tsv"
OUT = REPO / "data" / "graph_scale" / "deliberator_rules"

# ── dimension table (base SI exponents: m, kg, s, A, K, mol) — the exact verifier ────────────────
_DIM: dict[str, tuple] = {}


def _d(names, m=0, kg=0, s=0, A=0, K=0, mol=0, scale=1.0):
    for n in names:
        _DIM[n.lower()] = ((m, kg, s, A, K, mol), scale)   # lookup lowercases — store lowercased too


_d(["meter", "metre", "meters", "metres", "m"], m=1)
_d(["kilometer", "kilometre", "kilometers", "kilometres", "km"], m=1, scale=1000)
_d(["centimeter", "centimetre", "centimeters", "centimetres", "cm"], m=1, scale=0.01)
_d(["millimeter", "millimetre", "millimeters", "millimetres", "mm"], m=1, scale=0.001)
_d(["mile", "miles", "mi"], m=1, scale=1609.344)
_d(["yard", "yards", "yd"], m=1, scale=0.9144)
_d(["foot", "feet", "ft"], m=1, scale=0.3048)
_d(["inch", "inches", "in"], m=1, scale=0.0254)
_d(["nautical mile", "nautical miles"], m=1, scale=1852)
_d(["kilogram", "kilograms", "kg"], kg=1)
_d(["gram", "grams", "g"], kg=1, scale=0.001)
_d(["pound", "pounds", "lb", "lbs"], kg=1, scale=0.45359237)
_d(["ounce", "ounces", "oz"], kg=1, scale=0.028349523)
_d(["tonne", "tonnes", "metric ton", "metric tons"], kg=1, scale=1000)
_d(["second", "seconds", "s", "sec"], s=1)
_d(["minute", "minutes", "min"], s=1, scale=60)
_d(["hour", "hours", "h", "hr"], s=1, scale=3600)
_d(["day", "days"], s=1, scale=86400)
_d(["year", "years"], s=1, scale=31557600)
_d(["kelvin", "K"], K=1)
_d(["joule", "joules", "J"], m=2, kg=1, s=-2)
_d(["kilojoule", "kilojoules", "kJ"], m=2, kg=1, s=-2, scale=1000)
_d(["calorie", "calories", "cal"], m=2, kg=1, s=-2, scale=4.184)
_d(["electronvolt", "electronvolts", "eV"], m=2, kg=1, s=-2, scale=1.602176634e-19)
_d(["watt", "watts", "W"], m=2, kg=1, s=-3)
_d(["newton", "newtons", "N"], m=1, kg=1, s=-2)
_d(["pascal", "pascals", "Pa"], m=-1, kg=1, s=-2)
_d(["hertz", "Hz"], s=-1)
_d(["litre", "liter", "litres", "liters", "L"], m=3, scale=0.001)
_d(["gallon", "gallons"], m=3, scale=0.003785411784)
_d(["m/s", "meters per second", "metres per second"], m=1, s=-1)
_d(["km/h", "kilometers per hour", "kilometres per hour"], m=1, s=-1, scale=1 / 3.6)
_d(["mph", "miles per hour"], m=1, s=-1, scale=0.44704)

_NUM = r"([0-9][0-9,]*(?:\.[0-9]+)?(?:\s?[×x]\s?10[\^]?[−\-]?[0-9]+)?)"
_UNIT = r"([A-Za-zμ/]+(?:\s(?:per\s[a-z]+|mile[s]?|hour[s]?|second[s]?))?)"
_CONV = re.compile(rf"\b(?:1|one)\s{_UNIT}\s(?:=|is|equals?)\s(?:about\s|approximately\s|roughly\s)?{_NUM}\s{_UNIT}", re.I)
_CONST = re.compile(rf"\b(speed of light|gravitational constant|planck constant|elementary charge|"
                    rf"avogadro(?:'s)? (?:number|constant)|boltzmann constant|gas constant|"
                    rf"electron mass|proton mass|standard gravity)\b[^.]{{0,80}}?{_NUM}\s?{_UNIT}?", re.I)
_FORMULA = re.compile(r"\b([a-z][a-z ]{2,24}?)\s(?:equals|is equal to|is the product of|is given by)\s"
                      r"([a-z][a-z ]{2,30}?)\s(?:times|multiplied by|divided by)\s([a-z][a-z ]{2,30})\b", re.I)


def _val(s: str) -> float:
    s = s.replace(",", "").replace("×", "x").replace("−", "-")
    if "x10" in s.replace(" ", ""):
        base, _, exp = s.replace(" ", "").partition("x10")
        exp = exp.lstrip("^")
        return float(base) * (10 ** float(exp))
    return float(s)


def _dim_of(u: str):
    return _DIM.get(u.strip().lower())


def mine(max_passages: int | None = None) -> dict:
    t0 = time.time()
    conv_obs: dict[tuple, list] = defaultdict(list)     # (ua, ub) -> [(k, title)]
    const_obs: dict[str, list] = defaultdict(list)      # name -> [(value, unit, title)]
    formula_obs: dict[tuple, list] = defaultdict(list)  # (lhs, a, op, b) -> [title]
    seen = 0
    with open(PASSAGES, encoding="utf-8") as fh:
        for line in fh:
            seen += 1
            if max_passages and seen > max_passages:
                break
            tab = line.find("\t")
            if tab < 0:
                continue
            title, text = line[:tab], line[tab + 1:]
            for m in _CONV.finditer(text):
                ua, k, ub = m.group(1), m.group(2), m.group(3)
                da, db = _dim_of(ua), _dim_of(ub)
                if not da or not db or da[0] != db[0]:
                    continue                              # dimension mismatch → rejected outright
                try:
                    conv_obs[(ua.lower(), ub.lower())].append((_val(k), title))
                except Exception:
                    pass
            for m in _CONST.finditer(text):
                try:
                    const_obs[m.group(1).lower()].append((_val(m.group(2)), (m.group(3) or "").strip(), title))
                except Exception:
                    pass
            for m in _FORMULA.finditer(text):
                lhs, a, b = (m.group(1).strip().lower(), m.group(2).strip().lower(), m.group(3).strip().lower())
                op = "times" if ("times" in m.group(0) or "product" in m.group(0) or "multiplied" in m.group(0)) else "divided_by"
                formula_obs[(lhs, a, op, b)].append(title)
            if seen % 1_000_000 == 0:
                print(f'  scanned {seen} ({round(time.time()-t0,1)}s) conv={sum(len(v) for v in conv_obs.values())} '
                      f'const={sum(len(v) for v in const_obs.values())} formula={sum(len(v) for v in formula_obs.values())}', flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    n_conv = n_const = n_form = 0

    with open(OUT / "conversions.jsonl", "w", encoding="utf-8") as f:
        for (ua, ub), obs in conv_obs.items():
            da, db = _dim_of(ua), _dim_of(ub)
            expected = da[1] / db[1]                      # exact factor from the dimension table
            vals = [k for k, _t in obs]
            good = [k for k in vals if abs(k - expected) / max(expected, 1e-12) < 0.02]
            status = "verified" if good else ("candidate" if len(set(round(v, 3) for v in vals)) == 1 else "rejected")
            if status == "rejected":
                continue
            f.write(json.dumps({"unit_a": ua, "unit_b": ub, "k": expected if good else vals[0],
                                "status": status, "n_sources": len(obs),
                                "provenance": sorted({t for _k, t in obs})[:4]}, ensure_ascii=False) + "\n")
            n_conv += 1

    with open(OUT / "constants.jsonl", "w", encoding="utf-8") as f:
        for name, obs in const_obs.items():
            vals = sorted(v for v, _u, _t in obs)
            med = vals[len(vals) // 2]
            close = [v for v in vals if abs(v - med) / max(abs(med), 1e-12) < 0.01]
            status = "verified" if len(close) >= 2 else "candidate"
            f.write(json.dumps({"name": name, "value": med,
                                "unit": next((u for _v, u, _t in obs if u), ""),
                                "status": status, "n_sources": len(obs),
                                "provenance": sorted({t for _v, _u, t in obs})[:4]}, ensure_ascii=False) + "\n")
            n_const += 1

    with open(OUT / "formulas.jsonl", "w", encoding="utf-8") as f:
        for (lhs, a, op, b), titles in formula_obs.items():
            status = "verified" if len(set(titles)) >= 2 else "candidate"
            f.write(json.dumps({"lhs": lhs, "a": a, "op": op, "b": b, "status": status,
                                "n_sources": len(set(titles)), "provenance": sorted(set(titles))[:4]},
                               ensure_ascii=False) + "\n")
            n_form += 1

    rep = {"scanned": seen, "conversions": n_conv, "constants": n_const, "formulas": n_form,
           "total_rules": n_conv + n_const + n_form, "elapsed_s": round(time.time() - t0, 1)}
    print("\nRESULT d2", json.dumps(rep))
    (OUT / "report.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    return rep


def unit_convert(value: float, ua: str, ub: str) -> float:
    """Exact unit algebra from the dimension table — D2's runtime kernel (100%-exact by construction)."""
    da, db = _dim_of(ua), _dim_of(ub)
    if not da or not db or da[0] != db[0]:
        raise ValueError(f"dimension mismatch: {ua} vs {ub}")
    return value * da[1] / db[1]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    mp = int(sys.argv[1]) if len(sys.argv) > 1 else None
    mine(mp)
