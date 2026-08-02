# -*- coding: utf-8 -*-
"""G3 — the frozen-domain transfer testbed. Freeze B, solve A, measure B untouched.

This is the only instrument in the repository that can distinguish capability from
re-implementation, and plan v6 says why it has to exist: in one day four organs independently
hand-wrote the same discrimination operator. If consolidating that machinery does not make an
UNTOUCHED domain cheaper, the capability never generalised -- it was rebuilt, which is the disease.

THE ONE DESIGN DECISION EVERYTHING ELSE FOLLOWS FROM. The freeze covers B's OWN surface and
deliberately not the shared substrate. Transfer happens THROUGH shared machinery; if nothing shared
may change, transfer is impossible by construction and the gate can only ever read negative. If B's
own code may change, it is not transfer at all, it is editing the exam. So:

    frozen      B's domain modules, B's data, B's evaluation, B's baseline numbers
    permitted   the shared operators A and B both stand on
    measured    B's result and B's cost, re-run with the same evaluation

FOUR ANTI-CHEAT PROPERTIES, each one a way this test could otherwise be quietly won:

  1. PRE-REGISTRATION. The baseline and the direction of the claim are recorded and hashed at freeze
     time. "Lower is better" cannot be decided after seeing the number.
  2. UNTOUCHED IS VERIFIED, NOT PROMISED. The surface is content-hashed at freeze and re-hashed at
     measure. A changed surface makes the verdict INVALID -- never "no change", which is what a
     silent failure would look like.
  3. COST COUNTS, NOT ONLY SCORE. Consolidation is predicted to make B CHEAPER before it makes B
     better. A gate that only accepted score improvements would miss its own main effect.
  4. THE VERDICT IS REPORTED EITHER WAY. A negative result is the most valuable outcome available
     here, because it falsifies the diagnosis this whole plan rests on.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

REPO = Path(__file__).resolve().parents[2]
SEALED = REPO / "data" / "transfer_gate"

# Which way is better, fixed at freeze time so it cannot be flipped afterwards.
DIRECTIONS = ("higher_is_better", "lower_is_better")


@dataclass(frozen=True)
class Metric:
    """One pre-registered number, with the direction of the claim nailed down."""
    name: str
    baseline: float
    direction: str
    note: str = ""

    def __post_init__(self) -> None:
        if self.direction not in DIRECTIONS:
            raise ValueError(f"direction must be one of {DIRECTIONS}, got {self.direction!r}")

    def improved(self, now: float, *, tolerance: float = 0.0) -> bool:
        if self.direction == "higher_is_better":
            return now > self.baseline + tolerance
        return now < self.baseline - tolerance

    def regressed(self, now: float, *, tolerance: float = 0.0) -> bool:
        if self.direction == "higher_is_better":
            return now < self.baseline - tolerance
        return now > self.baseline + tolerance

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "baseline": self.baseline, "direction": self.direction,
                "note": self.note}


@dataclass(frozen=True)
class FrozenDomain:
    """Domain B, sealed. Nothing here may be edited after `frozen_at` without voiding the test."""
    name: str
    surface: tuple[str, ...]          # repo-relative paths that ARE this domain
    eval_entry: str                   # "package.module:function" returning {metric: value}
    metrics: tuple[Metric, ...]
    surface_hash: str
    frozen_at: str
    rationale: str = ""
    seal: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "surface": list(self.surface), "eval_entry": self.eval_entry,
                "metrics": [m.to_dict() for m in self.metrics], "surface_hash": self.surface_hash,
                "frozen_at": self.frozen_at, "rationale": self.rationale, "seal": self.seal}

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "FrozenDomain":
        return cls(name=str(row["name"]), surface=tuple(row["surface"]),
                   eval_entry=str(row["eval_entry"]),
                   metrics=tuple(Metric(**m) for m in row["metrics"]),
                   surface_hash=str(row["surface_hash"]), frozen_at=str(row["frozen_at"]),
                   rationale=str(row.get("rationale", "")), seal=str(row.get("seal", "")))


def _canonical(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def surface_files(surface: Iterable[str], root: Path | None = None) -> list[Path]:
    """Every file the declared surface expands to, sorted.

    A directory in the surface means the whole directory: a domain cannot be frozen by naming three
    of its files and quietly editing the fourth."""
    r = root or REPO
    out: list[Path] = []
    for entry in surface:
        p = r / entry
        if p.is_dir():
            out.extend(sorted(q for q in p.rglob("*")
                              if q.is_file() and "__pycache__" not in q.parts))
        elif p.is_file():
            out.append(p)
    return sorted(set(out))


def hash_surface(surface: Iterable[str], root: Path | None = None) -> str:
    """Content hash of the whole surface. Content, not mtime: a file restored byte-for-byte after
    an edit is genuinely untouched, and a file re-saved with no change is not a violation."""
    r = root or REPO
    parts = []
    for f in surface_files(surface, r):
        try:
            parts.append((str(f.relative_to(r)).replace("\\", "/"),
                          _sha256(f.read_text(encoding="utf-8", errors="replace"))))
        except OSError:
            parts.append((str(f), "UNREADABLE"))
    return _sha256(_canonical(parts))


def commits_touching(surface: Sequence[str], since_iso: str, root: Path | None = None
                     ) -> list[str]:
    """Commits after the freeze that touched the surface. A second, independent witness.

    The content hash and the git log can disagree -- an edit that was reverted leaves history but no
    hash change -- and both are reported rather than one being trusted. History says what was
    attempted; the hash says what stands."""
    r = root or REPO
    try:
        out = subprocess.run(
            ["git", "log", "--since", since_iso, "--format=%h %s", "--"] + list(surface),
            cwd=str(r), capture_output=True, text=True, timeout=60)
        return [ln for ln in out.stdout.splitlines() if ln.strip()]
    except Exception:
        return []


def freeze(name: str, surface: Sequence[str], eval_entry: str, metrics: Sequence[Metric], *,
           rationale: str = "", root: Path | None = None, path: Path | None = None) -> FrozenDomain:
    """Seal domain B. Refuses to overwrite an existing seal.

    Refusing is the point: a seal that can be re-cut after seeing A's result is not a seal, and
    re-freezing to 'update the baseline' is the most natural way this test would be lost."""
    r = root or REPO
    dest = path or (SEALED / f"{name}.json")
    if dest.exists():
        raise FileExistsError(
            f"{name} is already frozen at {dest}. Re-freezing would let the baseline be re-cut "
            f"after seeing the result; delete it deliberately if the test is being abandoned.")
    if not surface_files(surface, r):
        raise ValueError(f"surface for {name!r} matches no files; nothing would be frozen")

    domain = FrozenDomain(
        name=name, surface=tuple(surface), eval_entry=eval_entry, metrics=tuple(metrics),
        surface_hash=hash_surface(surface, r),
        frozen_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        rationale=rationale)
    from dataclasses import replace
    sealed = replace(domain, seal=_sha256(_canonical(domain.to_dict())))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(sealed.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return sealed


def load(name: str, *, path: Path | None = None) -> FrozenDomain | None:
    src = path or (SEALED / f"{name}.json")
    try:
        return FrozenDomain.from_dict(json.loads(src.read_text(encoding="utf-8")))
    except Exception:
        return None


def seal_intact(domain: FrozenDomain) -> bool:
    """Was the manifest itself edited? Guards the baseline, not the code."""
    body = {**domain.to_dict(), "seal": ""}
    return _sha256(_canonical(body)) == domain.seal


def sealed_domains(*, root: Path | None = None) -> list[str]:
    d = (root or REPO) / "data" / "transfer_gate" if root else SEALED
    try:
        return sorted(p.stem for p in d.glob("*.json"))
    except OSError:
        return []
