# -*- coding: utf-8 -*-
"""REGRESSION LOCK: acquisition_daemon must never shadow a Python stdlib module.

Root cause (fixed): the promotion queue lived in ``packages/acquisition_daemon/queue.py``. The
reboot launcher (``scripts/start_atanor_after_reboot.ps1``) puts EVERY ``packages/<dir>`` on
PYTHONPATH, so that file became importable as the top-level module ``queue`` and shadowed the
stdlib ``queue`` — which lacks ``SimpleQueue`` in our version. The engine crashed at startup with
``queue has no attribute SimpleQueue``. The module is now ``promotion_queue.py``.

These gates reproduce the exact startup path condition in a FRESH interpreter (a subprocess with the
reboot-script PYTHONPATH), so the shadowing can never silently return.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# repo root: tests -> acquisition_daemon -> packages -> <root>
_ROOT = Path(__file__).resolve().parents[3]
_PKG = Path(__file__).resolve().parents[1]


def _reboot_pythonpath() -> str:
    """Exactly the launcher's construction: ProjectRoot + every packages/<dir>, os.pathsep-joined."""
    pkg_dirs = sorted(str(p) for p in (_ROOT / "packages").iterdir() if p.is_dir())
    return os.pathsep.join([str(_ROOT)] + pkg_dirs)


def test_stdlib_queue_reachable_under_reboot_pythonpath():
    """GATE (c): with the reboot-script PYTHONPATH set, a fresh ``import queue`` resolves to the
    STDLIB (``queue.SimpleQueue`` exists), not to our package module."""
    env = dict(os.environ, PYTHONPATH=_reboot_pythonpath())
    child = (
        "import queue\n"
        "assert hasattr(queue, 'SimpleQueue'), 'stdlib queue.SimpleQueue missing -> shadowed'\n"
        "f = (getattr(queue, '__file__', '') or '').replace(chr(92), '/')\n"
        "assert 'acquisition_daemon' not in f, 'queue resolved to our package: ' + f\n"
        "import sys; sys.stdout.write(f)\n"
    )
    proc = subprocess.run([sys.executable, "-c", child], env=env,
                          capture_output=True, text=True)
    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    # the resolved stdlib queue must NOT be our shadowing file
    assert "acquisition_daemon" not in proc.stdout.replace("\\", "/")


def test_our_promotion_queue_also_importable_under_reboot_pythonpath():
    """With the SAME path condition, our real module is reachable under its non-shadowing name and
    the daemon package imports cleanly (so the fix did not merely hide the module)."""
    env = dict(os.environ, PYTHONPATH=_reboot_pythonpath())
    child = (
        "import queue\n"
        "assert hasattr(queue, 'SimpleQueue')\n"
        "from packages.acquisition_daemon.promotion_queue import AcquisitionQueue, result_to_item\n"
        "from packages.acquisition_daemon import AcquisitionQueue as AQ\n"
        "assert AQ is AcquisitionQueue\n"
    )
    proc = subprocess.run([sys.executable, "-c", child], env=env,
                          capture_output=True, text=True)
    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"


def test_no_shadowing_module_file_remains():
    """Structural lock: the shadowing ``queue.py`` is gone; ``promotion_queue.py`` carries the logic;
    and no OTHER file directly under this package collides with a stdlib top-level module name."""
    assert not (_PKG / "queue.py").exists(), "old shadowing acquisition_daemon/queue.py still present"
    assert (_PKG / "promotion_queue.py").exists(), "promotion_queue.py missing"

    stdlib = set(sys.stdlib_module_names) | set(sys.builtin_module_names)
    collisions = sorted(p.name for p in _PKG.glob("*.py") if p.stem in stdlib)
    assert collisions == [], f"stdlib-shadowing module files under acquisition_daemon: {collisions}"
