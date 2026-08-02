# -*- coding: utf-8 -*-
"""First boot: ATANOR reads the machine it woke up on, and settles into it.

    from packages.workspace.onboarding import onboard
    report = onboard()            # runs once; writes data/_onboarding/profile.json
    report = onboard(probe_senses=True)   # also opens cameras/mics (spends user grants)

WHAT ONBOARDING IS. When ATANOR is installed on a new machine it does not yet know what body it has:
what senses are attached, how much it can compute, where things belong, what kind of PC this is. This is
the one-time sequence that finds all of that and configures ATANOR to fit -- the adaptation the owner
asked for, run once at first boot and refreshable on demand.

It is assembly, not new capability. Every step calls a part built already:

    sensorium.discover     the eyes and ears actually attached (union of every enumeration path)
    device_profile.profile the compute the OS hands out -- cores, RAM, disk, GPU
    rooms.Rooms.census     what is on disk and what it would cost to lose
    formats                which file kinds are present, screened by bytes not name

WHERE THE LINE IS, because "freely use the PC" has an edge that matters. Onboarding OBSERVES and
CONFIGURES ITSELF. It reads whether a folder EXISTS and how big it is -- because that decides where
ATANOR puts its own working files and whether the big triple store fits -- but it does not read the
CONTENTS of a user's files. 'Pictures exists and is 40 GB' is a placement fact; 'what those pictures
are' is not onboarding's business and waits for the user to ask. Nothing here takes a permission the
user did not grant, and the sensory probe that DOES spend a grant is opt-in.

THE OUTPUT IS A SETTLED SELF. The report is not a list of facts; it is a set of DECISIONS -- which
perception path, which evidence cascade, how many fetch host-slots, where working files go -- each
traceable to what was measured. Re-running it re-decides, so moving ATANOR to a stronger or weaker
machine is just onboarding again.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

ONBOARD_DIR = Path("data/_onboarding")
PROFILE = ONBOARD_DIR / "profile.json"
# user directories whose SIZE and PRESENCE inform placement -- never their contents
USER_DIRS = ("Documents", "Pictures", "Videos", "Downloads", "Music", "Desktop")


@dataclass
class Onboarding:
    at: float = field(default_factory=time.time)
    machine: dict = field(default_factory=dict)
    senses: dict = field(default_factory=dict)
    disk: dict = field(default_factory=dict)
    user_context: dict = field(default_factory=dict)
    decisions: dict = field(default_factory=dict)
    boundary: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _machine() -> dict:
    from packages.workspace.device_profile import profile
    d = profile()          # no camera query here; that is the opt-in sensory probe below
    m = d.as_dict()
    m["os_release"] = platform.release()
    return m


def _senses(probe: bool) -> dict:
    from packages.perception.sensorium import sensory_self
    return sensory_self(probe_them=probe)


def _disk() -> dict:
    """What is on disk and what it would cost to lose -- placement, not inspection."""
    from packages.workspace.rooms import Rooms
    try:
        census = Rooms().census()
    except Exception as exc:
        census = {"error": str(exc)}
    drives = {}
    if platform.system() == "Windows":
        import string
        for letter in string.ascii_uppercase:
            root = f"{letter}:/"
            if os.path.exists(root):
                try:
                    drives[letter] = round(shutil.disk_usage(root).free / 1e9, 1)
                except OSError:
                    pass
    else:
        try:
            drives["/"] = round(shutil.disk_usage("/").free / 1e9, 1)
        except OSError:
            pass
    return {"census": census, "free_by_drive_gb": drives}


def _user_context() -> dict:
    """The SHAPE of the machine's user space: which standard folders exist and how large.

    Presence and size only. This is what tells ATANOR whether this is a media-heavy machine, where its
    own working files should live, and whether the large stores fit -- none of which needs a single
    user file to be read."""
    home = Path(os.path.expanduser("~"))
    folders = {}
    for d in USER_DIRS:
        p = home / d
        if not p.is_dir():
            continue
        size = 0
        files = 0
        # size is sampled shallowly -- top two levels -- so onboarding is fast and never walks a
        # whole media library; the number only has to be good enough to choose placement
        for depth_root, dirs, fs in os.walk(p):
            rel = os.path.relpath(depth_root, p).count(os.sep)
            if rel >= 2:
                dirs[:] = []
                continue
            for f in fs:
                try:
                    size += os.path.getsize(os.path.join(depth_root, f))
                    files += 1
                except OSError:
                    pass
        folders[d] = {"exists": True, "approx_gb": round(size / 1e9, 2), "sampled_files": files}
    return {"home_present": home.exists(), "standard_folders": folders,
            "note": "presence and size only; no user file content is read"}


def _decide(machine: dict, senses: dict, disk: dict) -> dict:
    """Turn measurements into ATANOR's settings. Each decision cites what drove it."""
    tier = machine.get("tier", "unknown")
    ram = machine.get("ram_gb", 0)
    cores = machine.get("cpu_cores", 1)
    cuda = machine.get("has_cuda", False)
    biggest_drive = max(disk.get("free_by_drive_gb", {"": 0}).values(), default=0)

    d: dict = {}
    d["perception"] = ("gpu encoder" if cuda else "cpu encoder (103 KB signature net runs on cpu)")
    d["perception_because"] = f"has_cuda={cuda}"

    eyes = senses.get("vision", {}).get("live", 0) or senses.get("vision", {}).get("found", 0)
    d["vision_geometry"] = ("multi-view" if eyes and eyes >= 2 else
                            "monocular" if eyes == 1 else "no camera found")
    d["vision_because"] = f"{eyes} camera(s) discovered"

    if tier in ("tiny", "small"):
        d["evidence"] = "table + local corpora; web tier held back (its rate limit hurts small most)"
        d["load_triple_store"] = False
    else:
        d["evidence"] = "full cascade table -> local -> web"
        d["load_triple_store"] = biggest_drive > 80
    d["evidence_because"] = f"tier={tier}, biggest free drive={biggest_drive} GB"

    d["fetch_host_slots"] = max(2, min(cores * 2, 64 if ram >= 8 else 8))
    d["fetch_because"] = f"{cores} cores, {ram} GB ram"

    # where ATANOR's own working files go: the roomiest drive, so the machine's main disk stays free
    drives = disk.get("free_by_drive_gb", {})
    if drives:
        best = max(drives, key=drives.get)
        d["workspace_drive"] = f"{best}: ({drives[best]} GB free)"
        d["workspace_because"] = "roomiest drive, to keep the system disk clear"

    ears = senses.get("hearing", {}).get("found", 0)
    if ears:
        d["hearing"] = f"{ears} microphone(s) found, unusable until an audio encoder exists"
    return d


def onboard(*, probe_senses: bool = False, save: bool = True) -> Onboarding:
    """Run the first-boot adaptation once, and write the settled self-profile.

    `probe_senses` opens cameras and microphones to confirm what they are, which spends the user's
    device grants; it defaults OFF so that a bare onboarding never touches a permission."""
    machine = _machine()
    senses = _senses(probe_senses)
    disk = _disk()
    user = _user_context()
    o = Onboarding(
        machine=machine, senses=senses, disk=disk, user_context=user,
        decisions=_decide(machine, senses, disk),
        boundary=("onboarding observes and configures itself; it reads folder presence and size, "
                  "never user file contents; sensory probing is opt-in and a refused device is "
                  "recorded, never bypassed"),
    )
    if save:
        ONBOARD_DIR.mkdir(parents=True, exist_ok=True)
        PROFILE.write_text(json.dumps(o.as_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return o


def is_onboarded() -> bool:
    return PROFILE.exists()


def summary(o: Onboarding) -> str:
    m, d = o.machine, o.decisions
    lines = [
        f"ATANOR settled onto: {m.get('platform')} {m.get('machine')}, "
        f"{m.get('cpu_cores')} cores, {m.get('ram_gb')} GB, tier {m.get('tier')}, "
        f"GPU {'yes' if m.get('has_cuda') else 'no'}",
        f"  senses    : {o.senses.get('vision', {}).get('found', 0)} eye(s), "
        f"{o.senses.get('hearing', {}).get('found', 0)} ear(s)",
        f"  perception: {d.get('perception')}  |  vision {d.get('vision_geometry')}",
        f"  evidence  : {d.get('evidence')}",
        f"  fetch     : {d.get('fetch_host_slots')} host slots",
        f"  workspace : {d.get('workspace_drive', 'default')}",
    ]
    return "\n".join(lines)
