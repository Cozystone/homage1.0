from __future__ import annotations


def score_patch_manifest(compression_ratio: float, reconstruction_error: float, risk_level: str) -> dict[str, float]:
    risk_penalty = {"low": 0.0, "medium": 0.15, "high": 0.4, "critical": 1.0}.get(risk_level, 0.4)
    return {
        "compression_score": min(1.0, compression_ratio / 8.0),
        "error_score": max(0.0, 1.0 - reconstruction_error * 100),
        "risk_penalty": risk_penalty,
    }
