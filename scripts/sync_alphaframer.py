# -*- coding: utf-8 -*-
"""Split-repo backup: mirror the AlphaFramer public perception protocol out of the ATANOR monorepo
into the standalone AlphaFramer repo (owner's 2026-07-12 split strategy).

THE STRATEGY: open-source the eyes/body (AlphaFramer perception protocol) to capture the ecosystem;
keep the mind (ATANOR core: graph engine, reasoning, learning, self-model) locked in the fortress.
So the load-bearing part of a "clean split" is not the concept — it is the LEAK GATE below.

THE FORTRESS GATE (why this file exists): after copying + rewriting a file's imports to be
self-contained, we scan the OUTPUT. If ANY `packages.*` import survives — or any forbidden brain
package is referenced — we ABORT and write nothing. A public file must be fully standalone; a
lingering monorepo import is the exact shape a brain leak would take. Belt (self-contained) AND
suspenders (explicit brain denylist).

Dev happens in the monorepo (Ultimate); this backs the public subset out to the repo. Idempotent:
run it after any change to the perception protocol and the public mirror follows. Never the reverse.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]           # the ATANOR monorepo (this worktree)
DEFAULT_TARGET = REPO_ROOT.parent / "AlphaFramer"         # the standalone public repo clone

# ── the PUBLIC manifest: only the clean perception protocol. Anything not here never ships. ──
MODULES: dict[str, str] = {
    "packages/perception/object_recognition.py": "alphaframer/object_recognition.py",
    "packages/perception/face_cortex.py":        "alphaframer/face_cortex.py",
    "packages/perception/spatial_memory.py":     "alphaframer/spatial_memory.py",
    "packages/perception/reconstruction_loss.py": "alphaframer/reconstruction_loss.py",
    "packages/perception/geo_anchor.py":         "alphaframer/geo_anchor.py",  # macro-geo binding
    "packages/imagination/splatra_cloud.py":     "alphaframer/geometry.py",   # shape vocabulary
}
TESTS: dict[str, str] = {
    "packages/perception/tests/test_object_recognition.py": "tests/test_object_recognition.py",
    "packages/perception/tests/test_spatial_memory.py":     "tests/test_spatial_memory.py",
    "packages/perception/tests/test_reconstruction_loss.py": "tests/test_reconstruction_loss.py",
    "packages/perception/tests/test_geo_anchor.py":         "tests/test_geo_anchor.py",
}

# import rewrites: monorepo path → standalone `alphaframer.*`, applied longest-first
REWRITES: list[tuple[str, str]] = [
    ("from packages.imagination.scene_compiler import _archetype, _hue",
     "from alphaframer.geometry import _archetype, _hue"),
    ("from packages.imagination.splatra_cloud import shape_spec as _shape_spec",
     "from alphaframer.geometry import shape_spec as _shape_spec"),
    ("from packages.imagination.splatra_cloud", "from alphaframer.geometry"),
    ("packages.imagination.splatra_cloud", "alphaframer.geometry"),
    ("from packages.perception.", "from alphaframer."),
    ("import packages.perception.", "import alphaframer."),
    ("packages.perception.", "alphaframer."),
]

# THE DENYLIST — a reference to any of these in a PUBLIC file is a brain leak → abort
FORBIDDEN = (
    "packages.graph_scale", "packages.reasoning_vm", "packages.cloud_brain",
    "packages.autonomy_kernel", "packages.base_brain", "packages.continuous_self",
    "packages.episodic_memory", "packages.affordance", "packages.flywheel", "packages.cgsr",
    "packages.answer_quality", "packages.os_action_lane", "packages.brain_link",
    "packages.graph_hub", "packages.perception_stream", "packages.imagination.scene_compiler",
    "packages.imagination.live_thought", "packages.imagination.motion_miner",
    "packages.imagination.particle_intent",
)

# geometry.py needs _archetype + _hue (used by spatial_memory) — pure, brain-free, appended here
_GEOMETRY_APPENDIX = '''

# ── shape/colour helpers (extracted brain-free from the monorepo's scene compiler) ──────────────
def _hue(seed: str) -> float:
    """A stable hue in [0,360) from an id — the same object is always the same colour."""
    return int(hashlib.sha1(str(seed).encode("utf-8")).hexdigest()[:6], 16) % 360


def _archetype(concept: dict[str, Any]) -> str:
    """Coarse particle shape from a concept's own type/description signals (never a name table)."""
    t = " ".join(str(concept.get(k, "")) for k in ("type", "kind", "category", "desc")).lower()
    label = str(concept.get("label", ""))
    if any(c in t for c in ("liquid", "fluid", "gas", "water", "액체", "기체", "물")) \
            or label in ("물", "불", "연기", "구름", "비", "바다", "강"):
        return "blob"
    if any(c in t for c in ("process", "event", "action", "행동", "과정", "현상", "운동")):
        return "swirl"
    if any(c in t for c in ("place", "location", "지역", "장소", "도시", "나라", "지방")):
        return "field"
    return "sphere"
'''


def _rewrite(text: str) -> str:
    for src, dst in REWRITES:
        text = text.replace(src, dst)
    return text


def _gate(rel: str, text: str) -> list[str]:
    """Return the leaks found in one public file — empty means clean. A surviving `packages.` import
    (self-containment broken) or any forbidden brain package is a leak."""
    leaks: list[str] = []
    for f in FORBIDDEN:
        if f in text:
            leaks.append(f"{rel}: forbidden reference '{f}'")
    # any residual monorepo import after rewriting = not self-contained = potential leak
    for m in re.finditer(r"^\s*(?:from|import)\s+(packages\.[\w.]+)", text, re.MULTILINE):
        leaks.append(f"{rel}: unresolved monorepo import '{m.group(1)}'")
    return leaks


def _readme() -> str:
    return '''# AlphaFramer

**A spatial-context perception protocol. The eye that never keeps a frame.**

AlphaFramer turns raw camera input into the smallest honest description of a space — object
identities, where they are, the surfaces and paths through them — and **stores no frame**. It is the
perception layer meant to become the shared "reference frame" for smart glasses and humanoid robots.

## Three principles

**1. No-Frame doctrine.** A camera frame is distilled and discarded — never written to disk. Only
distilled geometry leaves: an object's label, its normalised position, its geometric *signature*
(not pixels), and the walkable affordances. Privacy is structural, not a policy toggle.

**2. Semantic-Bottleneck honesty.** *If you cannot rebuild it, you did not understand it.* AlphaFramer
does not lean on a generative model's plausible hallucinations. A deliberately **deterministic**
reconstruction is the training tool: the machine rebuilds a scene from its context alone and measures
what it lost (`reconstruction_loss`). The gaps it names — size, colour, layout — become the next
lessons. A generative decoder is barred from the truth signal on purpose.

**3. Episodic memory recombination.** Spaces you passed through become a timeline you can query.
"Where did I walk earlier?" replays the recorded geometry — the room where it was, rebuilt from
distilled structure, never from a saved image.

## What's here (v0)

| module | what it does |
|---|---|
| `object_recognition` | re-recognise the same object across sightings by its visual signature (multi-view drift-robust, conservative threshold, honest about uncertainty) |
| `spatial_memory` | record a space as distilled geometry (no frame) and rebuild it as a point-cloud scene |
| `reconstruction_loss` | the semantic-bottleneck audit — a deterministic rebuild + a topology loss + the measured curriculum |
| `face_cortex` | geometric face identity (an embedding compared by cosine; an unknown face is an honest gap, never a guessed name) |
| `geometry` | the structural shape vocabulary (a form per graph type) + LoD budget for bounded rendering |

Pure Python, no network, no frame storage. `pip install -e .` then `pytest`.

---

*AlphaFramer is the open perception protocol of the ATANOR project. The reasoning core is separate.*
'''


def _license() -> str:
    return ("MIT License\n\nCopyright (c) 2026 ATANOR / Cozystone\n\n"
            "Permission is hereby granted, free of charge, to any person obtaining a copy of this "
            "software and associated documentation files (the \"Software\"), to deal in the Software "
            "without restriction, including without limitation the rights to use, copy, modify, merge, "
            "publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons "
            "to whom the Software is furnished to do so, subject to the following conditions:\n\n"
            "The above copyright notice and this permission notice shall be included in all copies or "
            "substantial portions of the Software.\n\nTHE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT "
            "WARRANTY OF ANY KIND, EXPRESS OR IMPLIED.\n")


def _pyproject() -> str:
    return ('[build-system]\nrequires = ["setuptools>=61"]\nbuild-backend = "setuptools.build_meta"\n\n'
            '[project]\nname = "alphaframer"\nversion = "0.0.1"\n'
            'description = "A spatial-context perception protocol — the eye that never keeps a frame."\n'
            'requires-python = ">=3.10"\ndependencies = ["numpy"]\n\n'
            '[tool.setuptools.packages.find]\ninclude = ["alphaframer*"]\n')


def _init() -> str:
    return ('# -*- coding: utf-8 -*-\n"""AlphaFramer — a spatial-context perception protocol '
            '(no-frame, semantic-bottleneck honest)."""\n'
            'from .object_recognition import recognize_object, instance_stats\n'
            'from .spatial_memory import record_snapshot, recall_snapshot, reconstruct_scene, detect_spatial_recall\n'
            'from .reconstruction_loss import cycle_audit, topology_score\n\n'
            '__all__ = ["recognize_object", "instance_stats", "record_snapshot", "recall_snapshot",\n'
            '           "reconstruct_scene", "detect_spatial_recall", "cycle_audit", "topology_score"]\n')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=str(DEFAULT_TARGET), help="AlphaFramer repo clone path")
    ap.add_argument("--dry-run", action="store_true", help="show the plan + run the gate; write nothing")
    ap.add_argument("--commit", action="store_true", help="git add+commit in the target after a clean sync")
    args = ap.parse_args()
    target = Path(args.target)

    planned: list[tuple[str, str, str]] = []           # (rel_dest, content, source)
    all_leaks: list[str] = []
    for src, dst in {**MODULES, **TESTS}.items():
        raw = (REPO_ROOT / src).read_text(encoding="utf-8")
        out = _rewrite(raw)
        if dst == "alphaframer/geometry.py":
            out += _GEOMETRY_APPENDIX
        all_leaks += _gate(dst, out)
        planned.append((dst, out, src))

    print(f"AlphaFramer sync — {len(planned)} files, source={REPO_ROOT.name}")
    for dst, _, src in planned:
        print(f"  {src}  ->  {dst}")

    if all_leaks:
        print("\n❌ LEAK GATE FAILED — aborting, nothing written:")
        for lk in all_leaks:
            print(f"   - {lk}")
        return 2
    print("\n✅ leak gate CLEAN — no monorepo/brain references in any public file")

    checksum = hashlib.sha1("".join(c for _, c, _ in planned).encode("utf-8")).hexdigest()[:12]
    if args.dry_run:
        print(f"[dry-run] would write to {target} (content sha {checksum})")
        return 0

    if not (target / ".git").exists():
        print(f"❌ target {target} is not a git clone — clone the AlphaFramer repo there first")
        return 3
    (target / "alphaframer").mkdir(parents=True, exist_ok=True)
    (target / "tests").mkdir(parents=True, exist_ok=True)
    (target / "alphaframer" / "__init__.py").write_text(_init(), encoding="utf-8")
    for dst, content, _ in planned:
        (target / dst).write_text(content, encoding="utf-8")
    (target / "README.md").write_text(_readme(), encoding="utf-8")
    (target / "LICENSE").write_text(_license(), encoding="utf-8")
    (target / "pyproject.toml").write_text(_pyproject(), encoding="utf-8")
    (target / ".gitignore").write_text("__pycache__/\n*.pyc\n*.egg-info/\ndata/\n.pytest_cache/\n", encoding="utf-8")
    manifest = {"synced_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "content_sha": checksum,
                "files": [d for d, _, _ in planned], "gate": "clean",
                "contract": "no-frame perception protocol; ATANOR reasoning core is NOT included"}
    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(planned)+5} files to {target}")

    if args.commit:
        subprocess.run(["git", "-C", str(target), "add", "-A"], check=True)
        msg = f"sync: AlphaFramer perception protocol (sha {checksum}) — leak gate clean"
        r = subprocess.run(["git", "-C", str(target), "commit", "-m", msg], capture_output=True, text=True)
        print(r.stdout.strip() or r.stderr.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
