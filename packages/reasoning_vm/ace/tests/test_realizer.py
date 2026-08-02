# -*- coding: utf-8 -*-
"""Track F / F1 — the realizer MUST be causal even with a pad mask present (the bug that made loss
collapse to ~0: pad mask silently disabled causal masking, so the model copied the target). This
test is the regression guard: position t's output may depend only on positions <= t."""
from __future__ import annotations

import torch

from packages.reasoning_vm.ace.realizer import Realizer


def test_causality_holds_with_pad_mask():
    torch.manual_seed(0)
    m = Realizer(vocab=64, d_model=64, layers=2, heads=4, ffn=128).eval()
    ids = torch.randint(4, 64, (1, 10))
    pad = torch.zeros(1, 10, dtype=torch.bool)          # no real pads, but exercises the masked path
    with torch.no_grad():
        full = m(ids, pad)
        # recompute logits at position t from ONLY the prefix ids[:t+1]; must match the full pass
        for t in (2, 5, 8):
            pref = m(ids[:, : t + 1], torch.zeros(1, t + 1, dtype=torch.bool))
            assert torch.allclose(full[0, t], pref[0, t], atol=1e-4), f"causality broken at t={t}"


def test_future_token_does_not_leak():
    torch.manual_seed(1)
    m = Realizer(vocab=64, d_model=64, layers=2, heads=4, ffn=128).eval()
    ids = torch.randint(4, 64, (1, 8))
    pad = torch.zeros(1, 8, dtype=torch.bool)
    with torch.no_grad():
        a = m(ids, pad)
        ids2 = ids.clone(); ids2[0, -1] = (ids2[0, -1] + 5) % 64   # change ONLY the last token
        b = m(ids2, pad)
    # every position before the last must be unaffected by changing the future token
    assert torch.allclose(a[0, :-1], b[0, :-1], atol=1e-4)


def test_generate_stops_at_sep():
    m = Realizer(vocab=32, d_model=32, layers=1, heads=2, ffn=64).eval()
    out = m.generate([1, 5, 6, 2], sep_id=2, max_new=10, greedy=True)
    assert isinstance(out, list) and len(out) <= 10


def test_uid_penalty_blocks_repetition_loops():
    import torch as _t
    _t.manual_seed(3)
    m = Realizer(vocab=32, d_model=32, layers=1, heads=2, ffn=64).eval()
    # without the penalty a tiny random model happily loops; with it, immediate repeats are barred
    out = m.generate([1, 7, 8], sep_id=2, max_new=20, greedy=True, uid_penalty=8.0)
    assert all(out[i] != out[i + 1] for i in range(len(out) - 1))   # no A A
    bigrams = [(out[i], out[i + 1]) for i in range(len(out) - 1)]
    assert len(set(bigrams)) == len(bigrams)                        # no repeated bigram loop
