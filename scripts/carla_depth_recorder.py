# -*- coding: utf-8 -*-
"""Record registered RGB + depth + semantic episodes out of CARLA, as ground truth for depth.

RUNS UNDER A DIFFERENT PYTHON THAN THE REST OF ATANOR, on purpose:

    D:\\carla\\env38\\python.exe scripts/carla_depth_recorder.py --episodes 4 --frames 300

CARLA 0.9.15's client ships for Python 3.7/3.8 and this repository runs 3.13 (PyPI offers `carla`
0.9.5 for 3.13, which is four years stale). Rather than hold the whole engine back, the recorder is
a separate process that writes files, and ATANOR reads those files. For LEARNING depth that is not a
compromise at all -- nothing about supervised depth needs a live socket. A live bridge becomes
necessary only when ATANOR drives in CARLA, which is a later thing.

WHY SYNCHRONOUS MODE IS NOT OPTIONAL. The entire value of this data is that the depth pixel at
(x, y) is the depth OF the colour pixel at (x, y). In CARLA's default asynchronous mode the server
ticks freely and each sensor delivers whenever it is ready, so the RGB and depth images that arrive
together can be from different world states -- and the misregistration is small, plausible, and
invisible in a thumbnail. Training on it would teach depth that is subtly wrong everywhere.
Synchronous mode with a fixed delta makes the three sensors share one tick, and the frame numbers
are asserted equal below rather than assumed.

WHY THE DEPTH IS DECODED AND NOT SAVED AS AN IMAGE. CARLA's depth camera returns 24 bits of depth
packed across the B, G, R channels. `ColorConverter.LogarithmicDepth` renders that to something a
human can look at -- and throws away most of the precision, especially far away, which is exactly
where depth is hard. So the packed value is decoded to metres here:

    normalised = (R + G*256 + B*256*256) / (256**3 - 1)
    metres     = 1000 * normalised

and stored as float16 in an .npz. Saving the pretty version and training on it is a mistake that
produces a model that works near the camera and quietly fails at range.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

import numpy as np

try:
    import carla
except ImportError:                                       # a clearer failure than a traceback
    sys.exit("carla client not importable — run this with D:\\carla\\env38\\python.exe, not the repo python")

OUT = Path(r"D:\carla\episodes")

# --- MEMORY GUARD -------------------------------------------------------------------------------------
# Added 2026-07-30 after loading Town11 KILLED a running server: the streaming port started refusing
# connections, actor destruction timed out at 60 s, and CarlaUE4 died. Available RAM at the time was
# 5.1 GB. Town11/12/13/15 are CARLA Large Maps -- tile-streamed and far heavier than Town01-10 -- so a
# map switch is the single most memory-hungry thing this script does, and it was attempted without
# measuring first.
#
# THE NUMBERS BELOW ARE ANCHORED ON ONE OBSERVATION, NOT CALIBRATED, and they are written here rather
# than chosen silently. 5.1 GB is the only known failure point; LARGE_MAP_FLOOR is set well above it
# because a floor at the observed failure would be a floor that fails. ANY_MAP_FLOOR has no failure
# behind it at all -- it is a bare sanity check, and it is labelled as such so nobody later mistakes it
# for a measurement.
LARGE_MAPS = ("Town11", "Town12", "Town13", "Town15")
LARGE_MAP_FLOOR_GB = 8.0     # anchored on: 5.1 GB available killed the server on Town11
ANY_MAP_FLOOR_GB = 2.0       # no failure observed; a sanity floor, not a measurement


def _available_gb() -> float:
    """Available physical memory, with no third-party dependency.

    The first version of this used psutil and returned infinity when the import failed -- which is
    exactly what happened, because the recorder runs under D:\carla\env38 where psutil is not
    installed. A guard that cannot measure and therefore permits everything is not a guard; it is the
    fail-open shape this project has had to repair before. GlobalMemoryStatusEx is in the Windows API
    and needs nothing installed."""
    try:
        import ctypes

        class _MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        st = _MS()
        st.dwLength = ctypes.sizeof(_MS)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
            return st.ullAvailPhys / 2 ** 30
    except Exception:
        pass
    try:
        import psutil
        return psutil.virtual_memory().available / 2 ** 30
    except Exception:
        return -1.0             # UNMEASURABLE. Fails CLOSED for large maps -- see check_memory_for.


def check_memory_for(town: str | None) -> None:
    """Refuse a map load the machine cannot survive. Measured before, not diagnosed after."""
    avail = _available_gb()
    is_large = town is not None and town.replace("_Opt", "") in LARGE_MAPS
    if avail < 0:
        # Unmeasurable. Refuse the case known to be fatal; allow the case with no failure behind it.
        if is_large:
            raise SystemExit(f"REFUSING {town!r}: memory is unmeasurable here and a large map killed a "
                             f"server on 2026-07-30. Not guessing on the expensive case.")
        print("memory guard: memory unmeasurable; standard map allowed (no failure on record)", flush=True)
        return
    floor = LARGE_MAP_FLOOR_GB if is_large else ANY_MAP_FLOOR_GB
    kind = "LARGE MAP (tile-streamed)" if is_large else "standard map"
    print(f"memory guard: {avail:.1f} GB available, {kind} needs >= {floor:.1f} GB", flush=True)
    if avail < floor:
        raise SystemExit(
            f"REFUSING to load {town!r}: {avail:.1f} GB available, floor {floor:.1f} GB. Loading Town11 "
            f"at 5.1 GB killed a running server on 2026-07-30 -- streaming port refused, actor destroy "
            f"timed out, process died. Free memory first (`wsl --shutdown` reclaims a couple of GB) or "
            f"record from a standard map instead."
        )
IMG_W, IMG_H, FOV = 800, 600, 90.0

# Traffic Manager port. NOT 8000: see the comment at `set_autopilot` — 8000 is Docker's here, and
# handing CARLA's RPC to an HTTP server crashes the client process with no exception to catch.
TM_PORT = 8005

# --- STEREO, OFF BY DEFAULT --------------------------------------------------------------------------
# A single moving eye cannot recover scale: halve every distance and halve the motion and the images are
# identical. That is not a limitation of our net, it is a property of monocular vision, and the E5 exam
# measured its cost -- `ordinal_selfsup` produces order (Spearman 0.309) and no metres at all. TWO eyes at
# a KNOWN separation remove the ambiguity, because disparity times baseline is a distance rather than a
# ratio.
#
# WHAT A BASELINE BUYS, in this rig's own numbers. Focal length is f = W / (2 tan(fov/2)) = 800 / (2 tan45)
# = 400 px, and disparity = f * B / Z. So:
#
#     B = 0.065 m  (human interpupillary)   10 m -> 2.6 px    50 m -> 0.52 px   sub-pixel, unusable
#     B = 0.12  m  (compact automotive)     10 m -> 4.8 px    50 m -> 0.96 px
#     B = 0.50  m  (wide automotive)        10 m -> 20  px    50 m -> 4.0  px
#
# Human stereo also fails past roughly ten metres -- people judge distance further out from other cues --
# so 0.065 is the right default for a HUMAN-LIKE eye and is honestly near-field only. A driving rig that
# needs range wants 0.12-0.5. The number is recorded in every episode's meta so nothing downstream has to
# guess it, and the intrinsics go with it so disparity can be turned into metres by anyone.
DEFAULT_BASELINE_M = 0.065
N_NPC = 60          # NPC vehicles per episode
N_WALKER = 30       # pedestrians per episode

# CARLA's semantic tag ids, WRITTEN DOWN because guessing them cost a wrong reading already.
# 0.9.14 replaced the old 23-class set with this 29-class one, and reading 0.9.15 data with the old
# table put "Wall" at 1000m and "Building" at 5m — nonsense that looked like broken depth. The depth
# was fine; the table was stale. Id 11 is Sky, and its median depth being exactly 1000.00m (the far
# plane) is the single best check that a recording is registered and decoded correctly.
SEMANTIC_TAGS = {
    0: "Unlabeled", 1: "Roads", 2: "Sidewalks", 3: "Buildings", 4: "Walls", 5: "Fences",
    6: "Poles", 7: "TrafficLight", 8: "TrafficSigns", 9: "Vegetation", 10: "Terrain",
    11: "Sky", 12: "Pedestrians", 13: "Rider", 14: "Car", 15: "Truck", 16: "Bus", 17: "Train",
    18: "Motorcycle", 19: "Bicycle", 20: "Static", 21: "Dynamic", 22: "Other", 23: "Water",
    24: "RoadLine", 25: "Ground", 26: "Bridge", 27: "RailTrack", 28: "GuardRail",
}


def _decode_depth(image: "carla.Image") -> np.ndarray:
    """CARLA depth image -> metres, float32 HxW. See the module docstring for why not the converter."""
    raw = np.frombuffer(image.raw_data, dtype=np.uint8).reshape((image.height, image.width, 4))
    b, g, r = raw[:, :, 0].astype(np.float32), raw[:, :, 1].astype(np.float32), raw[:, :, 2].astype(np.float32)
    normalised = (r + g * 256.0 + b * 256.0 * 256.0) / (256.0 ** 3 - 1.0)
    return normalised * 1000.0


def _rgb(image: "carla.Image") -> np.ndarray:
    raw = np.frombuffer(image.raw_data, dtype=np.uint8).reshape((image.height, image.width, 4))
    return np.ascontiguousarray(raw[:, :, :3][:, :, ::-1])          # BGRA -> RGB


def _semantic(image: "carla.Image") -> np.ndarray:
    """The class id lives in the RED channel of the raw image. Converting with CityScapesPalette
    first would replace ids with display colours and lose the labels."""
    raw = np.frombuffer(image.raw_data, dtype=np.uint8).reshape((image.height, image.width, 4))
    return np.ascontiguousarray(raw[:, :, 2])


def _intrinsics(w: int, h: int, fov_deg: float) -> dict:
    f = w / (2.0 * math.tan(math.radians(fov_deg) / 2.0))
    return {"fx": f, "fy": f, "cx": w / 2.0, "cy": h / 2.0, "width": w, "height": h, "fov": fov_deg}


def _force_async(world) -> None:
    """Leave the server in a sane state before starting, not only after finishing.

    `record_episode` restores the original settings in a `finally`, which handles exceptions and
    does NOTHING for a native crash. After one of those the server stays in synchronous mode with a
    fixed delta, waiting for ticks nobody sends, and the next run inherits a world that looks alive
    and is frozen. So the state is asserted on the way in as well as on the way out."""
    s = world.get_settings()
    if s.synchronous_mode:
        s.synchronous_mode = False
        s.fixed_delta_seconds = None
        world.apply_settings(s)
        time.sleep(0.5)


def record_episode(client: "carla.Client", ep: int, frames: int, weather_name: str, seed: int,
                   baseline_m: float = 0.0,
                   town: str | None = None) -> dict:
    if town:
        # THE NAME IS RESOLVED AGAINST THE SERVER, not handed over as typed, and that fix is worth
        # the paragraph because I misdiagnosed it twice.
        #
        # CARLA's Large Maps live at a NESTED path -- `/Game/Carla/Maps/Town11/Town11` -- while the
        # normal towns are flat: `/Game/Carla/Maps/Town03`. Passing the short name "Town11" makes
        # the server look for `/Game/Carla/Maps/Town11`, which is a DIRECTORY and not a map, and the
        # load dies. Every one of Town11/12/13/15 is a Large Map, so every remaining town failed and
        # the pattern looked exactly like the large maps being too big for the machine.
        #
        # I concluded memory, twice, and acted on it: restarted the server, freed several GB. Then
        # `load_world('/Game/Carla/Maps/Town11/Town11')` loaded in 10.4 SECONDS with 3,166 spawn
        # points. It was never memory. Resolving the name against `get_available_maps()` -- the
        # server's own list -- removes the guess entirely.
        maps = list(client.get_available_maps())
        target = next((m for m in maps if m.rstrip("/").split("/")[-1] == town), None)
        if target is None:
            raise RuntimeError(f"no map named {town!r}; server offers {sorted(m.split('/')[-1] for m in maps)}")
        client.set_timeout(300.0)                # a Large Map is a long load, not a hung one
        client.load_world(target)
        time.sleep(3.0)
        client.set_timeout(60.0)
    world = client.get_world()
    _force_async(world)
    original = world.get_settings()
    rng = random.Random(seed)

    settings = world.get_settings()
    settings.synchronous_mode = True
    settings.fixed_delta_seconds = 0.05                    # 20 Hz world; every sensor shares the tick
    world.apply_settings(settings)

    bp = world.get_blueprint_library()
    actors: list = []
    try:
        world.set_weather(getattr(carla.WeatherParameters, weather_name))

        spawn = rng.choice(world.get_map().get_spawn_points())
        vehicle = world.spawn_actor(rng.choice(bp.filter("vehicle.*")), spawn)

        # THE TRAFFIC MANAGER PORT IS NOT THE DEFAULT, and this is the whole reason the first
        # collection run died. `set_autopilot(True)` with no port opens a Traffic Manager client on
        # 8000 — and on this machine 8000 is held by com.docker.backend.exe. The CARLA client then
        # speaks its RPC protocol to Docker's HTTP server and the process dies NATIVELY: no
        # traceback, no exception, nothing for a `try/except` to catch. Two collection runs ended
        # that way, each printing one line and exiting 0, and it was only found by walking the calls
        # one at a time until `set_autopilot` was the last thing printed.
        tm = client.get_trafficmanager(TM_PORT)
        tm.set_synchronous_mode(True)          # the TM must share the tick, or it fights the world
        vehicle.set_autopilot(True, TM_PORT)
        actors.append(vehicle)

        # NPC TRAFFIC, because an empty city cannot test what an object is.
        #
        # Every episode until now spawned the ego vehicle alone, and nothing else in the world moved
        # independently. Measured on those recordings, pedestrians and vehicles occupy 0.3% of a
        # frame -- so a grouping rule asked to find "the things that move on their own" had almost
        # nothing to find, and the test could not tell a good rule from a bad one. That is a defect in
        # the corpus that no care in the grouping code would have revealed, and it looked exactly like
        # a working recording: 400 frames, 0 dropped, clean semantic maps.
        #
        # It bites objecthood specifically. In a static world seen from a moving camera EVERY surface
        # is rigidly attached to every other, so "one rigid body" is the correct and useless answer.
        # Independent movers are what make the question have more than one answer.
        pts = world.get_map().get_spawn_points()
        for si in rng.sample(range(len(pts)), min(N_NPC, max(0, len(pts) - 1))):
            npc = world.try_spawn_actor(rng.choice(list(bp.filter("vehicle.*"))), pts[int(si)])
            if npc is not None:
                npc.set_autopilot(True, TM_PORT)
                actors.append(npc)
        # WALKERS ARE SKIPPED ON LARGE MAPS, and the reason is a native crash rather than a preference.
        # On Town15, `controller.ai.walker.go_to_location(...)` KILLS THE CLIENT PROCESS -- no traceback,
        # no exception, exit code 0 mid-line. Bisected by replaying this function call by call: `start()`
        # printed, `go_to_location` did not return. Large Maps stream their navigation mesh by tile, so a
        # target drawn from `get_random_location_from_navigation()` can sit in a tile that is not resident,
        # and the client dies reaching for it. try/except cannot catch it -- the process is gone.
        #
        # ep400 recorded fine because it ran immediately after the map load, with the tiles around the
        # spawn still resident; every later attempt died. That is why this looked intermittent.
        #
        # Depth ground truth does not need pedestrians. Objecthood work does -- an empty city cannot test
        # what an object is -- so episodes recorded this way carry `walkers_skipped` in their meta and
        # must not be used for that.
        is_large = world.get_map().name.split("/")[-1].replace("_Opt", "") in LARGE_MAPS
        if is_large:
            print("  walkers SKIPPED: large map, go_to_location crashes the client natively", flush=True)
        wbp = bp.filter("walker.pedestrian.*")
        cbp = bp.find("controller.ai.walker")
        for _ in range(0 if is_large else N_WALKER):
            loc = world.get_random_location_from_navigation()
            if loc is None:
                break
            w = world.try_spawn_actor(rng.choice(list(wbp)), carla.Transform(loc))
            if w is None:
                continue
            actors.append(w)
            c = world.try_spawn_actor(cbp, carla.Transform(), attach_to=w)
            if c is not None:
                actors.append(c)
                c.start()
                c.go_to_location(world.get_random_location_from_navigation())
        print(f"  traffic: {sum(1 for a in actors if a.type_id.startswith('vehicle'))} vehicles, "
              f"{sum(1 for a in actors if 'pedestrian' in a.type_id)} pedestrians", flush=True)

        # ONE transform for all three cameras. Different transforms would give three views of the
        # same instant, which is not registration -- the whole point is that pixel (x,y) is the same
        # ray in all three.
        cam_tf = carla.Transform(carla.Location(x=1.5, z=2.4))
        queues: dict[str, list] = {"rgb": [], "depth": [], "semantic": []}
        specs = {"rgb": "sensor.camera.rgb", "depth": "sensor.camera.depth",
                 "semantic": "sensor.camera.semantic_segmentation"}
        # THE RIGHT EYE SHARES THE TICK, like every other sensor here. Registration is the whole value of
        # this corpus -- pixel (x,y) must be the same instant in every stream -- and a stereo pair whose
        # two images come from different world states is worse than no stereo at all, because the
        # disparity it reports is part parallax and part motion with no way to tell them apart.
        if baseline_m:
            specs["rgb_right"] = "sensor.camera.rgb"
            queues["rgb_right"] = []
        for name, blueprint_id in specs.items():
            b = bp.find(blueprint_id)
            b.set_attribute("image_size_x", str(IMG_W))
            b.set_attribute("image_size_y", str(IMG_H))
            b.set_attribute("fov", str(FOV))
            tf = cam_tf
            if name == "rgb_right":
                tf = carla.Transform(carla.Location(x=1.5, y=float(baseline_m), z=2.4))
            s = world.spawn_actor(b, tf, attach_to=vehicle)
            s.listen(queues[name].append)
            actors.append(s)

        ep_dir = OUT / f"ep{ep:03d}"
        ep_dir.mkdir(parents=True, exist_ok=True)
        kept, dropped = 0, 0

        for _ in range(frames + 20):                       # a few extra ticks to prime the sensors
            world.tick()
            if not all(queues.values()):
                continue
            rgb_i, dep_i, sem_i = queues["rgb"].pop(0), queues["depth"].pop(0), queues["semantic"].pop(0)
            rgt_i = queues["rgb_right"].pop(0) if baseline_m else None

            # ASSERTED, not assumed. If the three sensors ever disagree on the frame number the data
            # is misregistered and must be discarded, not quietly written.
            if not (rgb_i.frame == dep_i.frame == sem_i.frame):
                dropped += 1
                continue

            depth_m = _decode_depth(dep_i)
            tf = vehicle.get_transform()
            extra = {"rgb_right": _rgb(rgt_i)} if rgt_i is not None else {}
            np.savez_compressed(
                ep_dir / f"{kept:05d}.npz",
                rgb=_rgb(rgb_i),
                depth_m=depth_m.astype(np.float16),        # 16 bits is ~0.5m at 1km, ~1mm up close
                semantic=_semantic(sem_i),
                pose=np.array([tf.location.x, tf.location.y, tf.location.z,
                               tf.rotation.pitch, tf.rotation.yaw, tf.rotation.roll], np.float32),
                frame=np.int64(rgb_i.frame),
                sim_time=np.float64(rgb_i.timestamp),
                **extra)                                   # rgb_right, only when --stereo was given
            kept += 1
            if kept >= frames:
                break

        meta = {"episode": ep, "frames": kept, "dropped_misregistered": dropped,
                "weather": weather_name, "map": world.get_map().name, "seed": seed,
                "walkers_skipped": bool(is_large),
                "stereo_baseline_m": float(baseline_m) if baseline_m else None,
                "stereo_note": (("right eye at y=+%.3f m, same tick, same intrinsics; "
                                 "disparity * %.1f / d_px = metres" % (baseline_m, 400.0 * baseline_m))
                                if baseline_m else "monocular"),
                "intrinsics": _intrinsics(IMG_W, IMG_H, FOV),
                "semantic_tags": SEMANTIC_TAGS,
                "depth_encoding": "float16 metres, decoded from packed 24-bit; NOT LogarithmicDepth",
                "sync": {"synchronous_mode": True, "fixed_delta_seconds": 0.05}}
        (ep_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return meta
    finally:
        try:
            client.get_trafficmanager(TM_PORT).set_synchronous_mode(False)
        except Exception:
            pass
        for a in reversed(actors):
            try:
                if hasattr(a, "stop"):
                    a.stop()
                a.destroy()
            except Exception:
                pass
        world.apply_settings(original)                     # never leave the server in sync mode


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stereo", type=float, default=0.0, metavar="BASELINE_M",
                    help=("record a second RGB camera at this separation in metres, sharing the tick. "
                          "0 (default) is monocular and leaves existing behaviour untouched. "
                          "%.3f is human interpupillary; automotive rigs use 0.12-0.5. See the geometry "
                          "note at the top: at f=400 px a 0.065 m baseline is sub-pixel past ~40 m."
                          % DEFAULT_BASELINE_M))
    ap.add_argument("--episodes", type=int, default=4)
    ap.add_argument("--frames", type=int, default=300)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=2000)
    ap.add_argument("--town", default=None, help="load this map once before recording (e.g. Town03)")
    ap.add_argument("--start", type=int, default=0, help="episode number to start numbering from")
    ap.add_argument("--weather", default=None,
                    help="force one weather; default picks whichever the corpus has least of")
    args = ap.parse_args()

    client = carla.Client(args.host, args.port)
    client.set_timeout(30.0)
    print("connected:", client.get_server_version(), "| client:", client.get_client_version())

    # Weather is varied across episodes so a depth learner cannot solve the task by memorising one
    # lighting condition -- the same reason a corpus is not drawn from one source.
    #
    # CHOSEN BY WHAT THE CORPUS IS SHORT OF, not by episode index, and the first version got this
    # wrong in a way worth keeping. `weathers[ep % len(weathers)]` looks balanced and is balanced
    # only if episode numbers are consecutive. The collection ran one process per town with --start
    # at 10, 14, 18, 22, ... — every offset a multiple of four — so `ep % 8` only ever landed on two
    # or three of the eight entries. Result: 12 of 14 episodes wet, ClearNoon once, and three
    # conditions never recorded at all. A depth learner trained on that would barely have seen a dry
    # road, and nothing in the run would have said so.
    #
    # Counting what is already on disk and taking the rarest is self-correcting: it does not care
    # how the run is split across processes, how it is restarted, or what order the towns come in.
    weathers = ["ClearNoon", "CloudySunset", "WetNoon", "HardRainNoon",
                "ClearSunset", "MidRainyNoon", "SoftRainSunset", "WetCloudyNoon"]

    def _rarest_weather() -> str:
        have = {w: 0 for w in weathers}
        for d in OUT.glob("ep*/meta.json"):
            try:
                w = json.loads(d.read_text(encoding="utf-8")).get("weather")
            except Exception:
                continue
            if w in have:
                have[w] += 1
        return min(weathers, key=lambda w: (have[w], weathers.index(w)))
    if args.town:
        print("towns available:", sorted({m.split("/")[-1] for m in client.get_available_maps()}))
    check_memory_for(args.town)
    OUT.mkdir(parents=True, exist_ok=True)
    all_meta = []
    for ep in range(args.start, args.start + args.episodes):
        t0 = time.time()
        try:
            # the map is switched at most ONCE, before the first episode, never between them
            m = record_episode(client, ep, args.frames, args.weather or _rarest_weather(),
                               seed=1000 + ep, baseline_m=args.stereo,
                               town=(args.town if ep == args.start else None))
        except Exception as exc:
            # One bad episode must not end a long collection run. A spawn point can be occupied, a
            # vehicle blueprint can fail — those cost one episode, not the corpus.
            print(f"ep{ep:03d}: FAILED {type(exc).__name__}: {str(exc)[:140]}", flush=True)
            continue
        m["seconds"] = round(time.time() - t0, 1)
        all_meta.append(m)
        print(f"ep{ep:03d}: {m['frames']} frames, {m['dropped_misregistered']} dropped, "
              f"{m['weather']}, {m['seconds']}s")
    prev = []
    idx = OUT / "index.json"
    if idx.exists():
        try: prev = json.loads(idx.read_text(encoding="utf-8"))
        except Exception: prev = []
    all_meta = prev + all_meta
    (OUT / "index.json").write_text(json.dumps(all_meta, indent=2), encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
