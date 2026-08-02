# -*- coding: utf-8 -*-
"""DELIBERATOR organ ② (v0) — multi-hop reader. Given a question + candidate paragraphs, the circuit
SELECTS evidence by the learned SUPPORT head (not word overlap), then EXTRACTS the answer with the span
head over the selected evidence. This is backward chaining's first rung: score → select → read. The full
chainer (computed sub-queries from unbound premises) layers on top. No LLM."""
from __future__ import annotations

from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]


class MultiHopReader:
    def __init__(self, ckpt: str = "ace_support.pt"):
        import sys
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        import torch
        self.torch = torch
        self.dev = "cuda" if torch.cuda.is_available() else "cpu"
        if str(ckpt).startswith("ace2"):
            # ACE2 lane (E9): byte-BPE + model2, SAME downstream head API (ans/start/end/support),
            # so every reader method below works unchanged. data2's encode/collate don't take the
            # tokenizer the way ACE1's do — a 2-line shim keeps the call sites identical. Versioning
            # doctrine: ace2_* checkpoints only reach the live readers if Phase C beat the incumbent.
            from packages.reasoning_vm.ace import data2 as D2
            from packages.reasoning_vm.ace.model2 import Ace2Encoder

            class _D2Shim:
                EMB_DIR = None
                @staticmethod
                def encode(_tok, q, ctx, ans_start=-1, ans_text=""):
                    return D2.encode(q, ctx, ans_start, ans_text)
                @staticmethod
                def collate(batch, tok):
                    return D2.collate(batch, tok)
            self.D = _D2Shim
            self.tok = D2.tokenizer()
            self.model = Ace2Encoder(self.tok.get_vocab_size()).to(self.dev)
        else:
            from packages.reasoning_vm import learned_discriminator as LD
            from packages.reasoning_vm.ace import data as D
            from packages.reasoning_vm.ace.model import AceEncoder
            self.D = D
            emb = LD.Embeddings.load(D.EMB_DIR)
            self.tok = D.Tokenizer(emb)
            self.model = AceEncoder(self.tok.n_ids, warmstart=self.tok.warmstart_matrix(128)).to(self.dev)
        self.model.load_state_dict(torch.load(REPO / "data" / "graph_scale" / ckpt, map_location=self.dev),
                                   strict=False)
        self.model.eval()

    def _support(self, claim: str, evidences: list[str]) -> np.ndarray:
        torch, D = self.torch, self.D
        batch = [D.encode(self.tok, claim, ev) for ev in evidences]
        b = D.collate(batch, self.tok)
        b = {k: v.to(self.dev) for k, v in b.items()}
        with torch.no_grad(), torch.autocast(self.dev, dtype=torch.bfloat16, enabled=(self.dev == "cuda")):
            logits = self.model.support(b["ids"], b["seg"], b["feats"], b["pad"])
            return torch.softmax(logits.float(), -1).cpu().numpy()      # (n,3) SUPPORTS/NEI/REFUTES

    def _span(self, question: str, evidence: str) -> tuple[str, float]:
        """Best answer span in ONE evidence passage + its score (so the caller can pick across passages,
        avoiding the truncation of a long concatenation)."""
        torch, D = self.torch, self.D
        er = D.encode(self.tok, question, evidence)
        b = D.collate([er], self.tok)
        b = {k: v.to(self.dev) for k, v in b.items()}
        with torch.no_grad(), torch.autocast(self.dev, dtype=torch.bfloat16, enabled=(self.dev == "cuda")):
            _ans, start, end = self.model(b["ids"], b["seg"], b["feats"], b["pad"])
        off, plen, ch = er["p_off"], er["p_len"], er["p_char"]
        if not ch or plen == 0:
            return "", -1e18
        s = start[0, off:off + plen].float().cpu().numpy()
        e = end[0, off:off + plen].float().cpu().numpy()
        best, bi, bj = -1e18, 0, 0
        for i in np.argsort(s)[::-1][:8]:
            i = int(i)
            j = i + int(np.argmax(e[i:i + 30]))
            v = float(s[i] + e[j])
            if v > best:
                best, bi, bj = v, i, j
        return evidence[ch[bi][0]:ch[min(bj, len(ch) - 1)][1]], best

    def _relevance(self, claim: str, evidences: list[str]) -> np.ndarray:
        """P(relevant) per paragraph from the answerability head (HotpotQA-tuned retrieval organ)."""
        torch, D = self.torch, self.D
        batch = [D.encode(self.tok, claim, ev) for ev in evidences]
        b = D.collate(batch, self.tok)
        b = {k: v.to(self.dev) for k, v in b.items()}
        with torch.no_grad(), torch.autocast(self.dev, dtype=torch.bfloat16, enabled=(self.dev == "cuda")):
            ans_logit, _s, _e = self.model(b["ids"], b["seg"], b["feats"], b["pad"])
            return torch.sigmoid(ans_logit.float()).cpu().numpy()

    # leading tokens of an English polar (yes/no) question — a ROUTER prior only; the actual yes/no
    # decision is made by the learned support head, never by this cue.
    _POLAR = {"is", "are", "was", "were", "do", "does", "did", "has", "have", "had", "can", "could",
              "will", "would", "should", "am", "if", "which"}   # 'which' handled by span unless truly polar

    def _is_polar(self, question: str) -> bool:
        w = question.strip().lower().split()
        return bool(w) and w[0] in self._POLAR and w[0] != "which"

    def answer(self, question: str, paragraphs: list[tuple[str, str]], k: int = 2,
               chain: bool = True, rank: str = "support") -> dict:
        """paragraphs: [(title, text)]. Select top-k supporting paras; extract the answer.

        chain=True is BACKWARD-CHAINING v1: the selected paragraphs' TITLES are the bridge entities the
        2-hop question refers to indirectly, so we INJECT them into the query. The span head, now seeing
        the bridge names, can compose the second hop — reusing the organ, no LLM, no question parsing.

        Polar (yes/no) questions — which the span head structurally cannot answer — are routed to the
        support judge over the selected evidence: yes if SUPPORTS outweighs REFUTES. Measured 0.574 on
        HotpotQA yes/no (majority 0.509), zero new training — reusing the D0/D1 organ."""
        if not paragraphs:
            return {
                "answer": "",
                "support": [],
                "support_indices": [],
                "answer_index": None,
            }
        texts = [t for _title, t in paragraphs]
        if rank == "ans":
            score = self._relevance(question, texts)                 # HotpotQA-tuned retrieval organ
        else:
            score = self._support(question, texts)[:, 0]             # P(SUPPORTS)
        order = np.argsort(-score)
        picked = [int(i) for i in order[:k]]
        titles = [paragraphs[i][0] for i in picked]
        if self._is_polar(question):                                 # yes/no via the support judge
            ev = " ".join(paragraphs[i][1] for i in picked)
            probs = self._support(question, [ev])[0]                 # [P_SUP, P_NEI, P_REF]
            return {"answer": "yes" if probs[0] >= probs[2] else "no", "support": titles,
                    "support_indices": picked, "answer_index": None,
                    "support_scores": [round(float(score[i]), 3) for i in picked], "type": "yesno"}
        q = question + (" " + " ".join(titles) if chain else "")     # inject bridge entities
        best_ans, best_sc, best_idx = "", -1e18, None
        for i in picked:                                             # per-paragraph (no truncation)
            a, sc = self._span(q, paragraphs[i][1])
            if a and a not in titles and sc > best_sc:               # answer isn't just an echoed title
                best_ans, best_sc, best_idx = a, sc, i
        if not best_ans:                                            # fall back: allow title-echo answers
            for i in picked:
                a, sc = self._span(q, paragraphs[i][1])
                if sc > best_sc:
                    best_ans, best_sc, best_idx = a, sc, i
        return {"answer": best_ans, "support": titles,
                "support_indices": picked, "answer_index": best_idx,
                "support_scores": [round(float(score[i]), 3) for i in picked]}

    def answer_iterative(self, question: str, paragraphs: list[tuple[str, str]], max_hops: int = 2,
                         gate=None) -> dict:
        """INTERNAL MONOLOGUE — explicit backward chaining. Instead of injecting all selected titles at
        once, discover the bridge entity ONE hop at a time: rank → pick the most-relevant passage → its
        TITLE is the bridge entity → forge the next sub-query (question ⊕ bridges-so-far) → re-rank the
        REMAINING passages against it. The forged sub-query sequence is the reasoning trail (No-LLM,
        inspectable). If a DoubtGate is given, hop count is ADAPTIVE: stop early once the evidence-so-far
        answers confidently (don't over-think a 1-hop question); keep digging while confidence is low."""
        if not paragraphs:
            return {"answer": "", "support": [], "monologue": []}
        remaining = list(range(len(paragraphs)))
        trail, picked, monologue = [], [], []
        q = question
        for hop in range(max_hops):
            if not remaining:
                break
            texts = [paragraphs[i][1] for i in remaining]
            rel = self._relevance(q, texts)
            j = int(np.argmax(rel))
            idx = remaining.pop(j)
            picked.append(idx)
            trail.append(paragraphs[idx][0])                        # title = bridge entity
            q_next = question + " " + " ".join(trail)               # forge the next sub-query
            monologue.append({"hop": hop + 1, "subquery": q, "picked": paragraphs[idx][0],
                              "relevance": round(float(rel[j]), 3)})
            if gate is not None and hop + 1 < max_hops:             # adaptive stop
                ev = " ".join(paragraphs[i][1] for i in picked)
                sig = gate.signals(q_next, ev)
                if sig.get("answer") and sig["conf"] >= gate.threshold:
                    q = q_next
                    break
            q = q_next
        if self._is_polar(question):                                # yes/no over the chained evidence
            ev = " ".join(paragraphs[i][1] for i in picked)
            probs = self._support(question, [ev])[0]
            return {"answer": "yes" if probs[0] >= probs[2] else "no", "support": trail,
                    "monologue": monologue, "type": "yesno"}
        best_ans, best_sc = "", -1e18
        for i in picked:
            a, sc = self._span(q, paragraphs[i][1])
            if a and a not in trail and sc > best_sc:
                best_ans, best_sc = a, sc
        if not best_ans:
            for i in picked:
                a, sc = self._span(q, paragraphs[i][1])
                if sc > best_sc:
                    best_ans, best_sc = a, sc
        return {"answer": best_ans, "support": trail, "monologue": monologue}
