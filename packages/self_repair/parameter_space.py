# -*- coding: utf-8 -*-
"""The loop's own hand-picked constants, discovered and made searchable — graphite into diamond.

    from packages.self_repair.parameter_space import discover, as_moves
    discover()      # every tunable constant in the loop's own organs
    as_moves()      # each one, as something the escape search can try and score

THE IDEA, in the owner's words: same atoms, different bonding. Everything measured today said the
material was already present and the STRUCTURE was wrong — a lane behind a dead gate, an oracle 29.8x
larger than the file being read, 115M triples nobody consulted. Not one of those needed more compute
or more data. They needed the same substance arranged differently.

The escape vocabulary had the same shape of problem. It was four move types, and a PERSON chose the
four, from four escapes that person had already performed. That is a fixed space, and a fixed space
cannot compound: each search exhausts it and stops, which is exactly why the plateau fires the moment
an escape lands.

WHAT IS ACTUALLY SITTING THERE, measured rather than supposed:

    73 numeric constants in the loop's own organs
    56% of them round hand-picked values -- 12, 3, 2, 0.15, 0.5, 40, 6, 8

Forty-one dimensions nobody has ever searched, inside the machinery that decides what the loop can
propose, judge, keep and revert. `min_domains=2`. `min_checkable=12`. `margin=1.5`. `PLATEAU_AFTER=3`.
`min_familiar=0.35`. Every one is a number someone typed once.

WHY THIS IS THE COMPOUNDING AXIS AND NOT JUST MORE MOVES. The vocabulary now GROWS BY ITSELF: any
organ added later arrives with its own constants, and they become searchable without this file being
edited. A move space that grows as the system grows is the first thing here that could make the next
improvement easier than the last, which is the definition of compounding and the one thing the
enablement ledger has never seen.

WHAT IT CANNOT DO, so the ceiling is visible. It finds NUMBERS. A constant that should not be a
constant — a threshold that ought to be a learned function of the input — is invisible to it, and so
is any change of structure that is not a parameter. It converts hand-picked numbers into measured
ones. That is a real and bounded thing.

SAFETY IS INHERITED, not re-argued: every candidate is scored by enablement and reverted, the
forbidden list in `provisional` still governs what may be written, and a parameter that unlocks
nothing is recorded as unlocking nothing.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: the loop's own organs. Its OWN, deliberately -- searching the whole repository would mean tuning
#: things no gate here measures, and a search whose effects are unmeasured is not a search.
ORGANS = (
    "packages/self_repair/relation_fit.py",
    "packages/self_repair/pattern_proposer.py",
    "packages/self_repair/relation_discovery.py",
    "packages/self_repair/autorun.py",
    "packages/self_repair/plateau_escape.py",
    "packages/self_repair/oracle_acquire.py",
    "packages/meta_diagnosis/enablement.py",
)
#: constants that are not knobs. 0 and 1 are usually structural, and anything above this is a size
#: or a timeout rather than a decision.
_SKIP_VALUES = {0, 1, -1}
_MAX_SENSIBLE = 4096


@dataclass
class Parameter:
    file: str
    name: str
    value: float
    line: int
    kind: str            # default | module_constant

    def key(self) -> str:
        return f"{Path(self.file).stem}.{self.name}"

    def candidates(self) -> list:
        """Neighbouring values worth trying. Multiplicative for ratios, additive for counts —
        because halving a count of 2 and halving a threshold of 0.35 are not the same kind of step."""
        v = self.value
        if isinstance(v, float) and 0 < v < 1:
            return sorted({round(max(0.01, min(0.99, v * f)), 4) for f in (0.5, 0.75, 1.5, 2.0)} - {v})
        iv = int(v)
        return sorted({max(1, iv // 2), max(1, iv - 1), iv + 1, iv * 2} - {iv})


def discover() -> list:
    """Every numeric knob in the loop's own organs, with where it lives.

    Read from the AST rather than by regex: a default in a signature and a module constant are the
    two shapes a knob actually takes, and matching text would also catch array indices and slice
    bounds, which are not decisions."""
    found: list = []
    for rel in ORGANS:
        path = REPO / rel
        if not path.exists():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = node.args
                defaults = list(args.defaults) + list(args.kw_defaults or [])
                names = [a.arg for a in args.args[-len(args.defaults):]] if args.defaults else []
                names += [a.arg for a in args.kwonlyargs]
                for name, d in zip(names, defaults):
                    if isinstance(d, ast.Constant) and isinstance(d.value, (int, float)) \
                            and not isinstance(d.value, bool):
                        if d.value in _SKIP_VALUES or abs(d.value) > _MAX_SENSIBLE:
                            continue
                        found.append(Parameter(rel, f"{node.name}:{name}", d.value,
                                               getattr(d, "lineno", 0), "default"))
            elif isinstance(node, ast.Assign) and len(node.targets) == 1:
                t = node.targets[0]
                if isinstance(t, ast.Name) and t.id.isupper() \
                        and isinstance(node.value, ast.Constant) \
                        and isinstance(node.value.value, (int, float)) \
                        and not isinstance(node.value.value, bool):
                    if node.value.value in _SKIP_VALUES or abs(node.value.value) > _MAX_SENSIBLE:
                        continue
                    found.append(Parameter(rel, t.id, node.value.value,
                                           getattr(node, "lineno", 0), "module_constant"))
    return found


_ROUND = {0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.5, 0.6, 0.75, 0.8, 0.9,
          2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 40, 50, 60, 100}


def on_measured_path() -> set:
    """Which organs the enablement measurement actually EXECUTES.

    Without this, a knob in code the measurement never runs reports "unlocked nothing" in exactly the
    same words as a knob that runs and does nothing. Measured rather than assumed: 4 of the 7 organs
    listed here are on the path and 3 are not, so 4 of 17 knobs were being scored by a measurement
    that never called them. A zero has to be able to mean something before it is worth reporting."""
    import sys
    from packages.meta_diagnosis.enablement import snapshot
    hit = set()

    def _trace(frame, event, arg):
        if event == "call":
            f = frame.f_code.co_filename.replace("\\", "/")
            for o in ORGANS:
                if f.endswith(o):
                    hit.add(o)
        return None

    old = sys.gettrace()
    sys.settrace(_trace)
    try:
        snapshot(label="path trace")
    finally:
        sys.settrace(old)
    return hit


def report() -> dict:
    """What is searchable, and how much of it was typed once and never revisited."""
    params = discover()
    hand = [p for p in params if p.value in _ROUND]
    return {
        "organs": len(ORGANS),
        "parameters": len(params),
        "hand_picked_round_values": len(hand),
        "share_round": round(len(hand) / max(1, len(params)), 3),
        "search_space": sum(len(p.candidates()) for p in params),
        "top": [{"key": p.key(), "value": p.value, "try": p.candidates()} for p in hand[:12]],
        "grows_by_itself": ("an organ added later arrives with its own constants and becomes "
                            "searchable without editing this file -- which is the part that could "
                            "compound"),
        "ceiling": ("it finds NUMBERS. A threshold that ought to be a learned function of its input "
                    "is invisible here, and so is any structural change that is not a parameter"),
    }


def search_parameters(*, only=("min_familiar", "min_margin", "min_fire", "overlap"),
                      top_cues: int = 12) -> dict:
    """Try each knob's neighbours and score by ENABLEMENT — the honest test of this whole idea.

    Restricted by default to the knobs that gate what SURVIVES, because those are the ones whose
    movement enablement can see. A knob that only changes how many cues are considered moves the
    input, not the gate, and would confound the measurement. Pass `only=None` to search everything --
    slower, and the honest thing to do before claiming no knob pays."""
    from packages.meta_diagnosis.enablement import enablement_since, snapshot
    from packages.self_repair import pattern_proposer as pp
    from packages.self_repair import relation_fit as rf

    results, skipped = [], []
    baseline = snapshot(top_cues=top_cues, label="parameter search baseline")
    for p in discover():
        short = p.name.split(":")[-1]
        if only is not None and short not in only:
            continue
        for cand in p.candidates():
            token = _set_default(p, cand)
            if token is None:
                skipped.append({"key": p.key(), "to": cand,
                                "why": "could not rebind this default"})
                continue
            try:
                rf._PROFILE_CACHE.clear()
                e = enablement_since(baseline, top_cues=top_cues,
                                     label=f"{p.key()}={cand}", record=False)
                results.append({"key": p.key(), "from": p.value, "to": cand,
                                "enablement": e["enablement"],
                                "newly_possible": e["newly_possible"],
                                # RELATIONS TOO. Carrying only survivor pairs meant every win whose
                                # enablement came from a newly-NAMEABLE RELATION reported an empty
                                # unlock set -- so the divergent archive saw nothing to admit from a
                                # search that had just found three wins. What a move opens is both
                                # kinds, and a niche keyed on half of it is keyed on noise.
                                "relations_newly_nameable": e.get("relations_newly_nameable") or [],
                                "lost": e["no_longer_possible"]})
            finally:
                _restore_default(p, token)
                rf._PROFILE_CACHE.clear()
    wins = [r for r in results if r["enablement"] > 0]
    on = on_measured_path()
    for r in results:
        r["on_measured_path"] = any(o.endswith(f"{r['key'].split('.')[0]}.py") for o in on)
    unmeasured = sorted({r["key"] for r in results if not r["on_measured_path"]})
    return {"tried": len(results), "unlocked": len(wins), "skipped": skipped,
            "scored_but_never_executed": unmeasured,
            "zeros_that_mean_nothing": len([r for r in results
                                            if not r["on_measured_path"] and r["enablement"] == 0]),
            "wins": sorted(wins, key=lambda r: -r["enablement"])[:8],
            "all": results,
            "reading": ("a knob that unlocks nothing is recorded as unlocking nothing; the value of "
                        "the space is that it GROWS as organs are added, not that every knob pays")}


def _set_default(p: "Parameter", value):
    """Rebind one keyword default in the live function object, reversibly."""
    import importlib
    mod_name = p.file.replace("/", ".").replace(".py", "")
    try:
        mod = importlib.import_module(mod_name)
    except Exception:
        return None
    if p.kind == "module_constant":
        old = getattr(mod, p.name, None)
        if old is None:
            return None
        setattr(mod, p.name, value)
        return ("const", old)
    fn_name, arg = p.name.split(":", 1)
    fn = getattr(mod, fn_name, None)
    if fn is None:
        return None
    # KEYWORD-ONLY defaults live in __kwdefaults__; POSITIONAL-OR-KEYWORD ones live in __defaults__.
    # The first version only handled the former and silently skipped the rest, so a search that
    # reported "0 knobs unlocked anything" had never tried half of them. Silent skips are how a
    # measurement becomes a story.
    kw = fn.__kwdefaults__ or {}
    if arg in kw:
        old = kw[arg]
        kw[arg] = value
        return ("kw", fn, arg, old)
    import inspect
    try:
        names = list(inspect.signature(fn).parameters)
    except (TypeError, ValueError):
        return None
    defaults = list(fn.__defaults__ or ())
    if not defaults or arg not in names:
        return None
    # __defaults__ aligns with the LAST len(defaults) positional parameters
    positional = [n for n in names if n not in kw]
    tail = positional[-len(defaults):]
    if arg not in tail:
        return None
    idx = tail.index(arg)
    old = defaults[idx]
    defaults[idx] = value
    fn.__defaults__ = tuple(defaults)
    return ("pos", fn, idx, old)


def _restore_default(p: "Parameter", token):
    if not token:
        return
    if token[0] == "const":
        import importlib
        mod = importlib.import_module(p.file.replace("/", ".").replace(".py", ""))
        setattr(mod, p.name, token[1])
    elif token[0] == "kw":
        _, fn, arg, old = token
        (fn.__kwdefaults__ or {})[arg] = old
    else:
        _, fn, idx, old = token
        d = list(fn.__defaults__ or ())
        d[idx] = old
        fn.__defaults__ = tuple(d)


def as_moves(winners: list | None = None) -> list:
    """Winning knobs, as `Move` objects the composition search can pair with the hand-written ones.

    THIS IS THE JOIN between the two halves of the compounding argument. Axis one grew the move space
    by discovery; axis two asks whether two moves can beat both parts. Neither is worth much alone: a
    bigger space that is still searched one move deep exhausts itself exactly as fast, and composition
    over three hand-picked moves has already been measured and no pair won. Handing the discovered
    knobs to the pair search is the first time either question is asked with enough material to have
    an interesting answer.

    Takes the winners rather than every knob on purpose. Pairing things that individually do nothing
    tests almost nothing and costs a full survey each time."""
    from packages.self_repair.moves import Move

    out = []
    for w in (winners or []):
        stem, name = w["key"].split(".", 1)
        param = next((p for p in discover()
                      if p.key() == w["key"] and w["to"] in p.candidates()), None)
        if param is None:
            continue

        def _mk(prm, val):
            def _apply():
                return _set_default(prm, val)

            def _revert(tok):
                _restore_default(prm, tok)
            return _apply, _revert

        ap, rv = _mk(param, w["to"])
        out.append(Move("PARAMETER", f"{name}={w['to']}",
                        f"{w['key']} from {w['from']} to {w['to']}", ap, rv,
                        f"found by search, unlocked {w['enablement']} alone"))
    return out
