# -*- coding: utf-8 -*-
"""DELIBERATOR organ ⑥ — option adjudicator: score each MCQ option by the ACE SUPPORT head against the
evidence, pick the best-supported (and, later, eliminate refuted ones). This is the reasoning circuit's
answer step built on D0's learned judge — No hand-rule word overlap, No LLM."""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


class Adjudicator:
    def __init__(self, ckpt: str = "ace_support.pt"):
        import sys
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        import torch
        from packages.reasoning_vm import learned_discriminator as LD
        from packages.reasoning_vm.ace import data as D
        from packages.reasoning_vm.ace.model import AceEncoder
        self.torch, self.D = torch, D
        self.dev = "cuda" if torch.cuda.is_available() else "cpu"
        emb = LD.Embeddings.load(D.EMB_DIR)
        self.tok = D.Tokenizer(emb)
        self.model = AceEncoder(self.tok.n_ids, warmstart=self.tok.warmstart_matrix(128)).to(self.dev)
        sd = torch.load(REPO / "data" / "graph_scale" / ckpt, map_location=self.dev)
        self.model.load_state_dict(sd, strict=False)
        self.model.eval()

    def _support_probs(self, claims: list[str], evidence: str):
        """Batched P(SUPPORTS/NEI/REFUTES) for each claim against one evidence passage."""
        torch, D = self.torch, self.D
        batch = [D.encode(self.tok, c, evidence) for c in claims]
        b = D.collate(batch, self.tok)
        b = {k: v.to(self.dev) for k, v in b.items()}
        with torch.no_grad(), torch.autocast(self.dev, dtype=torch.bfloat16, enabled=(self.dev == "cuda")):
            logits = self.model.support(b["ids"], b["seg"], b["feats"], b["pad"])
            probs = torch.softmax(logits.float(), dim=-1).cpu().numpy()
        return probs                                        # (n, 3): SUPPORTS, NEI, REFUTES

    def score_options(self, question: str, options: dict, evidence: str) -> dict:
        """Each option → a claim ("question + option"); score net support = P(SUPPORTS) − P(REFUTES)."""
        keys = list(options)
        claims = [f"{question} {options[k]}" for k in keys]
        p = self._support_probs(claims, evidence)
        return {k: float(p[i, 0] - p[i, 2]) for i, k in enumerate(keys)}

    def answer(self, question: str, options: dict, evidence: str) -> str | None:
        if not options:
            return None
        s = self.score_options(question, options, evidence)
        return max(s, key=s.get)
