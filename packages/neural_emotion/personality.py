from __future__ import annotations

from .models import PersonalityProfile


def default_profile() -> PersonalityProfile:
    return PersonalityProfile()


def cautious_operator_profile() -> PersonalityProfile:
    return PersonalityProfile(warmth=0.58, curiosity_baseline=0.38, caution_baseline=0.62, energy_baseline=0.24, formality=0.72)
