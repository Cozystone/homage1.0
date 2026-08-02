# -*- coding: utf-8 -*-
"""G1: duplication measured by SHAPE, and the honest limit of what a shape can see."""
from __future__ import annotations

import textwrap

from packages.operator_census.census import recurring, signature_of


def _fn(src: str):
    import ast
    return ast.parse(textwrap.dedent(src)).body[0]


def test_the_same_computation_under_different_names_collides():
    """Identifiers are dropped before hashing, so vocabulary cannot decide a match."""
    a = _fn("""
        def alpha(rows, ceiling):
            out = {}
            for r in rows:
                for w in r:
                    out[w] = out.get(w, 0) + 1
            return {w for w, n in out.items() if n > ceiling}
    """)
    b = _fn("""
        def zulu(docs, limit):
            tally = {}
            for d in docs:
                for t in d:
                    tally[t] = tally.get(t, 0) + 1
            return {t for t, c in tally.items() if c > limit}
    """)
    assert signature_of(a)[0] == signature_of(b)[0]


def test_a_different_computation_does_not_collide_however_similar_it_reads():
    """This is the limit that matters. Both of these 'discriminate against the alternatives', and
    they are NOT the same computation -- one cuts on an absolute share, the other on a ratio to the
    mean. A shape detector is syntactic, so it sees a family as two members, correctly."""
    share_cut = _fn("""
        def f(rows, ceiling):
            out = {}
            for r in rows:
                for w in r:
                    out[w] = out.get(w, 0) + 1
            return {w for w, n in out.items() if n > ceiling}
    """)
    ratio_to_mean = _fn("""
        def g(profiles, key):
            rates = {k: p.get(key, 0.0) for k, p in profiles.items()}
            mean = sum(rates.values()) / len(rates)
            return {k: r / mean for k, r in rates.items()}
    """)
    assert signature_of(share_cut)[0] != signature_of(ratio_to_mean)[0]


def test_trivial_bodies_are_not_operators(tmp_path):
    """A two-node body is shared by everything and says nothing."""
    (tmp_path / "packages" / "a").mkdir(parents=True)
    (tmp_path / "packages" / "b").mkdir(parents=True)
    for organ in ("a", "b"):
        (tmp_path / "packages" / organ / "m.py").write_text(
            "def f(x):\n    return x\n", encoding="utf-8")
    assert recurring(tmp_path, min_spread=2) == []


def test_spread_counts_organs_not_copies(tmp_path):
    """Two copies inside one organ are refactoring debt; the same shape in many organs is the
    thing plan v6 is about."""
    body = ("def f(rows, ceiling):\n"
            "    out = {}\n"
            "    for r in rows:\n"
            "        for w in r:\n"
            "            out[w] = out.get(w, 0) + 1\n"
            "    return {w for w, n in out.items() if n > ceiling}\n")
    (tmp_path / "packages" / "solo").mkdir(parents=True)
    (tmp_path / "packages" / "solo" / "m.py").write_text(body + "\n" + body.replace("def f", "def g"),
                                                         encoding="utf-8")
    assert recurring(tmp_path, min_spread=2) == []          # two copies, ONE organ

    for organ in ("x", "y"):
        (tmp_path / "packages" / organ).mkdir(parents=True)
        (tmp_path / "packages" / organ / "m.py").write_text(body, encoding="utf-8")
    got = recurring(tmp_path, min_spread=2)
    assert got and got[0].spread >= 2
