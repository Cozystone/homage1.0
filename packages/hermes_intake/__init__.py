"""Safe Hermes-Agent intake helpers.

This package scans files as inert text. It never imports or executes Hermes
runtime code.
"""

from .models import HermesIntakeReport
from .scanner import scan_repo

__all__ = ["HermesIntakeReport", "scan_repo"]
