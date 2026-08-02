from __future__ import annotations

from typing import Any


def optional_solver_backends() -> dict[str, Any]:
    backends: dict[str, Any] = {"simulated_annealing": True, "greedy_baseline": True}
    try:
        import dimod  # type: ignore  # noqa: F401

        backends["dimod_available"] = True
    except Exception:
        backends["dimod_available"] = False
    try:
        import neal  # type: ignore  # noqa: F401

        backends["neal_available"] = True
    except Exception:
        backends["neal_available"] = False
    return backends
