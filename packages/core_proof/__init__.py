"""ATANOR core proof utilities."""

__all__ = ["run_three_core_answer_path_proof"]


def run_three_core_answer_path_proof(*args, **kwargs):
    from .three_core_answer_path import run_three_core_answer_path_proof as _run

    return _run(*args, **kwargs)
