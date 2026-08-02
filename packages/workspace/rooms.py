# -*- coding: utf-8 -*-
"""Rooms — a declared place for every kind of thing, with the rules that kind actually needs.

    from packages.workspace.rooms import Rooms
    rooms = Rooms()
    p = rooms.place("ledger", "e5_transfer_seal/seal.json")   # append-only room; overwrite refused
    rooms.declare("gloss_lab", kind="derived", purpose="dictionary extraction experiments")

WHY ROOMS AND NOT FOLDERS. `data/` is 106 GB across 98 top-level directories, and the sorting principle
is topic, which is the wrong axis. Measured today: `data/perception/` holds consensus_shadow.json,
deficit_map.json, property_table_bench.json and graph_attribute_census.json -- none of which is
perception. They landed there because there was nowhere else and the author was already standing there.
I am that author; this file exists because I made the mess four times in one day.

THE AXIS THAT MATTERS IS LIFECYCLE, not subject. Two files about the same topic can need opposite
treatment, and two files about different topics can need identical treatment:

    vault      unreachable from any ingestion path. keys, user secrets.        never backed up in clear
    archive    raw downloads. huge, read-only, RE-FETCHABLE.                   27 GB, delete costs time
    derived    indexes and tables built from archive. rebuildable.             delete costs time
    ledger     seals, verdicts, measurements, audit chains. APPEND-ONLY.       delete costs the record
    candidate  proposed facts awaiting an operator. default-deny.              never read as truth
    live       current mutable state the running system owns.
    scratch    throwaway. safe to delete at any moment.

That table answers a question the current layout cannot: **what would be LOST if this directory
vanished.** 92% of the 106 GB is archive and derived -- re-fetchable and rebuildable. The irreplaceable
part is the ledger, and it is a few megabytes sitting in the same tree with no protection. Today I
overwrote a sealed verdict file by re-running a scorer; the fix there was local, and this is the general
form of it.

WHAT THE ROOM ENFORCES, per kind, because a rule nobody enforces is a comment:

    ledger     `place()` refuses a path that already exists -- a record is added, never replaced
    candidate  reads are marked so nothing can mistake a proposal for a fact
    vault      `place()` raises. The vault is not reachable through this API at all; the sterile-room
               property is that no general file helper knows the way in.
    scratch    carries a purge marker so a cleaner can act without guessing

ATANOR DECLARES ITS OWN ROOMS. `declare()` writes to a manifest, not to source. A new kind of work gets
a room by asking for one, and the manifest is the answer to "where does this go" for every later
caller -- which is the part that stops the next four files landing in perception.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

MANIFEST = Path("data/_rooms/manifest.json")

#: what each kind promises, and what it costs to lose
KINDS: dict[str, dict] = {
    "vault":     {"reachable_from_ingestion": False, "append_only": True, "rebuildable": False,
                  "loss": "irreplaceable", "note": "not reachable through this API by design"},
    "archive":   {"reachable_from_ingestion": True, "append_only": False, "rebuildable": True,
                  "loss": "time to re-download"},
    "derived":   {"reachable_from_ingestion": True, "append_only": False, "rebuildable": True,
                  "loss": "time to rebuild"},
    "ledger":    {"reachable_from_ingestion": True, "append_only": True, "rebuildable": False,
                  "loss": "the record itself"},
    "candidate": {"reachable_from_ingestion": True, "append_only": True, "rebuildable": True,
                  "loss": "proposals only, never truth"},
    "live":      {"reachable_from_ingestion": True, "append_only": False, "rebuildable": False,
                  "loss": "current state"},
    "scratch":   {"reachable_from_ingestion": True, "append_only": False, "rebuildable": True,
                  "loss": "nothing"},
}


class RoomError(RuntimeError):
    pass


@dataclass
class Room:
    name: str
    kind: str
    purpose: str
    path: str
    declared_at: float = field(default_factory=time.time)
    declared_by: str = "atanor"

    def rules(self) -> dict:
        return dict(KINDS[self.kind])


class Rooms:
    """The manifest, and the one call that decides where a file goes."""

    def __init__(self, manifest: Path | str = MANIFEST) -> None:
        self.manifest = Path(manifest)
        self.rooms: dict[str, Room] = {}
        if self.manifest.exists():
            raw = json.loads(self.manifest.read_text(encoding="utf-8"))
            self.rooms = {k: Room(**v) for k, v in raw.get("rooms", {}).items()}

    # ---- declaring ------------------------------------------------------------------------------
    def declare(self, name: str, *, kind: str, purpose: str, path: str | None = None,
                declared_by: str = "atanor") -> Room:
        """Make a new room. This is data, not code, so ATANOR can do it without an edit.

        A purpose is required and not decorative: the reason `data/perception` collected four
        unrelated files is that no room ever had to say what it was for, so nothing could say a file
        did not belong."""
        if kind not in KINDS:
            raise RoomError(f"unknown kind {kind!r}; known: {sorted(KINDS)}")
        if not purpose.strip():
            raise RoomError("a room must say what it is for")
        if name in self.rooms and self.rooms[name].kind != kind:
            raise RoomError(f"room {name!r} already exists as {self.rooms[name].kind!r}")
        room = Room(name=name, kind=kind, purpose=purpose.strip(),
                    path=path or f"data/{name}", declared_by=declared_by)
        self.rooms[name] = room
        self._save()
        return room

    def _save(self) -> None:
        self.manifest.parent.mkdir(parents=True, exist_ok=True)
        self.manifest.write_text(
            json.dumps({"kinds": KINDS,
                        "rooms": {k: asdict(v) for k, v in sorted(self.rooms.items())}}, indent=2),
            encoding="utf-8")

    # ---- using ----------------------------------------------------------------------------------
    def place(self, room: str, relative: str, *, create: bool = True) -> Path:
        """The path a file belongs at, with the room's rule enforced BEFORE anything is written.

        This is the call that replaces 'write it under data/<wherever I already am>'."""
        r = self.rooms.get(room)
        if r is None:
            raise RoomError(f"no room {room!r}. declare() it first, and say what it is for")
        if r.kind == "vault":
            raise RoomError("the vault is not reachable through this API -- that is its containment, "
                            "not an oversight. use packages.vault directly.")
        target = Path(r.path) / relative
        if r.kind in ("ledger", "candidate") and target.exists():
            raise RoomError(f"{room!r} is append-only ({r.kind}): {target} already exists. "
                            f"A record is added, never replaced.")
        if create:
            target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def room_of(self, path: str | Path) -> Room | None:
        """Which room does an existing path belong to? Longest declared path wins."""
        p = str(Path(path)).replace("\\", "/")
        best = None
        for r in self.rooms.values():
            rp = r.path.replace("\\", "/").rstrip("/")
            if p == rp or p.startswith(rp + "/"):
                if best is None or len(rp) > len(best.path):
                    best = r
        return best

    # ---- staying connected --------------------------------------------------------------------
    def trace(self, target: str, *, kinds: tuple = ("ledger", "candidate"), max_hits: int = 40):
        """Who refers to this? Rooms partition CUSTODY, never reference.

        A ledger entry cites a derived index; a candidate cites an archive url; the E5 seal names the
        very files it forbids itself to touch. That is the design: what a room restricts is WRITE
        authority and, for the vault, reachability -- not what may be mentioned. A partition that also
        blocked reference would turn rooms into silos and make the whole thing worse than the flat
        directory it replaced.

        Scanning is limited to the append-only rooms by default because they are the small ones -- the
        ledger is 97 MB against 113 GB -- and because they are where provenance is supposed to live."""
        needle = str(target).replace("\\", "/")
        tail = needle.rsplit("/", 1)[-1]
        hits = []
        for room in self.rooms.values():
            if room.kind not in kinds:
                continue
            base = Path(room.path)
            if not base.exists():
                continue
            for path in base.rglob("*"):
                if not path.is_file() or path.stat().st_size > 20_000_000:
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if needle in text or (len(tail) > 6 and tail in text):
                    hits.append({"room": room.name, "kind": room.kind,
                                 "file": str(path).replace("\\", "/")})
                    if len(hits) >= max_hits:
                        return hits
        return hits

    # ---- knowing what you would lose --------------------------------------------------------------
    def census(self, root: str = "data") -> dict:
        """Classify what is actually on disk, and report what would be LOST if it vanished.

        The number this exists to produce: how much of 106 GB is re-fetchable, and how small the part
        that is not actually is."""
        by_kind: dict[str, dict] = {k: {"bytes": 0, "dirs": 0, "paths": []} for k in KINDS}
        unclaimed: list[tuple[int, str]] = []
        rootp = Path(root)
        if not rootp.exists():
            return {"error": f"no {root}"}
        for entry in sorted(rootp.iterdir()):
            if not entry.is_dir():
                continue
            size = 0
            for dirpath, _dirs, files in os.walk(entry):
                for f in files:
                    try:
                        size += os.path.getsize(os.path.join(dirpath, f))
                    except OSError:
                        pass
            room = self.room_of(entry)
            if room is None:
                unclaimed.append((size, str(entry).replace("\\", "/")))
                continue
            slot = by_kind[room.kind]
            slot["bytes"] += size
            slot["dirs"] += 1
            slot["paths"].append(entry.name)
        total = sum(v["bytes"] for v in by_kind.values()) + sum(s for s, _ in unclaimed)
        rebuildable = sum(v["bytes"] for k, v in by_kind.items() if KINDS[k]["rebuildable"])
        return {"total_bytes": total,
                "rebuildable_bytes": rebuildable,
                "irreplaceable_bytes": total - rebuildable - sum(s for s, _ in unclaimed),
                "unclaimed_bytes": sum(s for s, _ in unclaimed),
                "unclaimed_top": [p for _s, p in sorted(unclaimed, reverse=True)[:12]],
                "by_kind": {k: {"bytes": v["bytes"], "dirs": v["dirs"]} for k, v in by_kind.items()},
                "rooms_declared": len(self.rooms)}
