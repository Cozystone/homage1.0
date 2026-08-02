# -*- coding: utf-8 -*-
"""DoubtGate — the self-doubt circuit (real-time-thinking part 3). Real thinking must know when it does NOT
know: when the retrieved evidence does not actually contain/support the answer, HALT and ask for more
rather than fabricate. This fuses three signals the ACE encoder already produces into one confidence:

  • p_ans     — answerability head sigmoid: does this evidence contain an answer at all? (context-fit)
  • peak      — span sharpness: softmax(start)_max · softmax(end)_max. A confident reader spikes; a
                guessing reader is flat.
  • p_support — the NLI support head on (question ⊕ chosen-span) vs evidence: does the evidence SUPPORT
                the answer, or is it non-entailed / contradicted?

Below threshold → ABSTAIN ("need more evidence"), never a guess. This is the hallucination-0 spine of the
thinking loop. Weights + threshold are tuned on a val split and reported on held-out — measured, not
hand-set. No LLM.
"""
from __future__ import annotations

import numpy as np


class _Logistic:
    """Tiny standardized logistic regression (numpy) — the LEARNED combiner. No hand-set weights: the data
    decides how much each confidence signal is worth (a strong signal + two weak ones must not be averaged
    down). Stores feature mean/std so it deploys deterministically."""
    def __init__(self):
        self.w = None; self.b = 0.0; self.mu = None; self.sd = None

    def fit(self, X: np.ndarray, y: np.ndarray, iters: int = 4000, lr: float = 0.2, l2: float = 1e-3):
        X = np.asarray(X, np.float64); y = np.asarray(y, np.float64)
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-9
        Z = (X - self.mu) / self.sd
        self.w = np.zeros(Z.shape[1]); self.b = 0.0
        n = len(y)
        for _ in range(iters):
            p = 1.0 / (1.0 + np.exp(-(Z @ self.w + self.b)))
            g = p - y
            self.w -= lr * (Z.T @ g / n + l2 * self.w)
            self.b -= lr * g.mean()
        return self

    def prob(self, X: np.ndarray) -> np.ndarray:
        Z = (np.asarray(X, np.float64) - self.mu) / self.sd
        return 1.0 / (1.0 + np.exp(-(Z @ self.w + self.b)))


class DoubtGate:
    def __init__(
        self,
        reader,
        combiner: "_Logistic | None" = None,
        threshold: float = 0.5,
        *,
        support_reader=None,
        answerability_threshold: float = 0.90,
        support_net_threshold: float = 0.90,
    ):
        self.r = reader                                   # a loaded MultiHopReader (model/tok/D/torch/dev)
        self.combiner = combiner                          # learned; None → geo-mean fallback
        self.threshold = threshold
        self.support_reader = support_reader
        self.answerability_threshold = float(answerability_threshold)
        self.support_net_threshold = float(support_net_threshold)
        if not 0.0 <= self.answerability_threshold <= 1.0:
            raise ValueError("answerability_threshold must be between 0 and 1")
        if not 0.0 <= self.support_net_threshold <= 1.0:
            raise ValueError("support_net_threshold must be between 0 and 1")

    @staticmethod
    def features(sig: dict) -> list[float]:
        """The feature vector the combiner learns over — same order at fit and inference."""
        return [sig["p_ans"], float(np.clip(sig["peak"] * 20.0, 0, 1)),
                float(np.clip(0.5 + 0.5 * sig.get("p_sup_net", 0.0), 0, 1))]

    def fit(self, sigs: list[dict], labels: list[int]) -> "DoubtGate":
        X = np.array([self.features(s) for s in sigs], np.float64)
        self.combiner = _Logistic().fit(X, np.array(labels))
        return self

    def signals(self, question: str, evidence: str) -> dict:
        """The three raw confidence signals + the decoded span, in one forward pass (+1 for support)."""
        torch, D = self.r.torch, self.r.D
        er = D.encode(self.r.tok, question, evidence)
        b = D.collate([er], self.r.tok)
        b = {k: v.to(self.r.dev) for k, v in b.items()}
        with torch.no_grad(), torch.autocast(self.r.dev, dtype=torch.bfloat16,
                                             enabled=(self.r.dev == "cuda")):
            ans_logit, start, end = self.r.model(b["ids"], b["seg"], b["feats"], b["pad"])
        p_ans = float(torch.sigmoid(ans_logit.float())[0].cpu())
        off, plen, ch = er["p_off"], er["p_len"], er["p_char"]
        if not ch or plen == 0:
            return {"p_ans": p_ans, "peak": 0.0, "p_support": 0.5, "answer": "", "conf": 0.0}
        s = torch.softmax(start[0, off:off + plen].float(), -1).cpu().numpy()
        e = torch.softmax(end[0, off:off + plen].float(), -1).cpu().numpy()
        bi = int(np.argmax(s))
        bj = bi + int(np.argmax(e[bi:bi + 30]))
        peak = float(s[bi] * e[min(bj, len(e) - 1)])
        answer = evidence[ch[bi][0]:ch[min(bj, len(ch) - 1)][1]]
        # support: is the answer entailed by the evidence? (claim = question + answer)
        try:
            probs = self.r._support(question + " " + answer, [evidence])[0]
            p_support = float(probs[0] - probs[2] * 0.0 + 0.0)   # P(SUPPORTS); see fuse for net use
            p_sup_net = float(probs[0] - probs[2])               # SUPPORTS − REFUTES
        except Exception:
            p_support, p_sup_net = 0.5, 0.0
        sig = {"p_ans": p_ans, "peak": peak, "p_support": p_support, "p_sup_net": p_sup_net,
               "answer": answer}
        sig["conf"] = self.fuse(sig)
        return sig

    def fuse(self, sig: dict) -> float:
        """Confidence in [0,1]. Learned combiner if fitted; else fall back to the answerability head alone
        (the measured best single signal — never average it down with weak ones)."""
        if self.combiner is not None:
            return float(self.combiner.prob(np.array([self.features(sig)]))[0])
        return float(sig["p_ans"])

    def decide(self, question: str, evidence: str) -> dict:
        """Answer if confident; else ABSTAIN — the honest halt."""
        sig = self.signals(question, evidence)
        if sig["conf"] < self.threshold or not sig["answer"]:
            return {"answer": "", "abstain": True, "confidence": round(sig["conf"], 4), "signals": sig}
        return {"answer": sig["answer"], "abstain": False, "confidence": round(sig["conf"], 4),
                "signals": sig}

    def judge_answer(self, question: str, answer: str, evidence: list[str]) -> dict:
        """Bind a proposed answer to one evidence row without retrieval reuse.

        A row is accepted only when the answerability reader and the separately
        trained support reader clear their thresholds on that same row.
        Missing support authority is fail-closed.

        The fixed 0.90/0.90 defaults reuse the sealed EAD-0 mechanism
        predicate. They establish a non-circular boundary only, not a fresh
        capability or calibration claim.
        """
        texts = [str(item) for item in evidence if str(item).strip()]
        if not str(answer).strip() or not texts:
            return {
                "accepted": False,
                "confidence": 0.0,
                "reason": "answer_or_evidence_missing",
                "signals": {},
            }
        if self.support_reader is None:
            return {
                "accepted": False,
                "confidence": 0.0,
                "reason": "support_reader_unavailable",
                "signals": {},
            }

        p_ans = np.asarray(self.r._relevance(question, texts), dtype=np.float64)
        support = np.asarray(
            self.support_reader._support(f"{question} {answer}", texts),
            dtype=np.float64,
        )
        if (
            p_ans.ndim != 1
            or support.ndim != 2
            or support.shape != (len(texts), 3)
            or len(p_ans) != len(texts)
            or not np.isfinite(p_ans).all()
            or not np.isfinite(support).all()
            or np.any((p_ans < 0.0) | (p_ans > 1.0))
            or np.any((support < 0.0) | (support > 1.0))
        ):
            raise ValueError("invalid evidence-answer discriminator signals")

        p_sup_net = support[:, 0] - support[:, 2]
        joint = np.minimum(p_ans, np.clip(p_sup_net, 0.0, 1.0))
        accepted_rows = (
            (p_ans >= self.answerability_threshold)
            & (p_sup_net >= self.support_net_threshold)
        )
        best = int(np.argmax(joint))
        accepted = bool(np.any(accepted_rows))
        if accepted:
            indices = np.flatnonzero(accepted_rows)
            best = int(indices[int(np.argmax(joint[indices]))])
        return {
            "accepted": accepted,
            "confidence": float(joint[best]),
            "reason": "evidence_answer_supported" if accepted else "evidence_answer_not_supported",
            "signals": {
                "evidence_index": best,
                "evidence_count": len(texts),
                "p_ans": float(p_ans[best]),
                "p_support": float(support[best, 0]),
                "p_nei": float(support[best, 1]),
                "p_refute": float(support[best, 2]),
                "p_sup_net": float(p_sup_net[best]),
                "answerability_threshold": self.answerability_threshold,
                "support_net_threshold": self.support_net_threshold,
            },
        }
