"""Locked Korean surface layer for English-first CGSR outputs."""

from .consistency_gate import check_korean_surface
from .translate_surface import realize_korean_surface

__all__ = ["check_korean_surface", "realize_korean_surface"]
