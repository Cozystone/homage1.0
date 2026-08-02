# Morning brief — the night of 2026-07-29

Written for the owner, who went to sleep with "내일 아침까지 준비 다 되어있게 해줘". Everything below is
measured; where something is unmeasured it says so.

---

## What is running right now

| | state |
|---|---|
| ATANOR API (`:8502`) | **up**. The 5180 Realcity started polling `/api/realcity/city-edits` the moment it came back — the city had been asking an absent brain for edits. |
| Life daemon | **up on current code**, inner speech writing to `data/temporal_reasoning/life_daemon.log` again after six days of silence. |
| CARLA 0.9.15 | **up**, headless (`-RenderOffScreen`), RPC on 2000, all 12 towns installed (18 GB + 6.7 GB additional maps). |
| Depth corpus | **done — 26 episodes, 7,100 frames, 0 misregistered, 8 towns, all 8 weather conditions** in `D:\carla\episodes`. |

## The night's four repairs

**The autonomy was dead and the journal was hiding it.** The loop was genuinely awake — `life_stream.jsonl`
was being written every few seconds — but `curious_search` records in that stream numbered **zero, ever**.
The last genuine web expedition was 2026-07-23T18:37. What concealed the six-day gap was that the five
most recent journal "expeditions" were pytest artifacts; 166 of 1,357 topic-bearing rows were fiction.
They are now tagged `test_artifact: true` rather than deleted, the journal diverts under pytest, and
fetch failures record their message instead of only the exception class.

**ATANOR had written the diagnosis itself.** In its own stream: *"my answering body is not responding —
I cannot act on the world."* The API was down. That is now the first thing checked.

**Curiosity could not leave the house when things were going well.** Every road to the world was
deficit-driven: the orchestrator reaches the web only through `high_abstention`, which needs the rate at
or above 0.1, and the measured rate is 0.01. Three fixes, one root:

* `intrinsic_drive` — a complete organ with **zero runtime callers** (built-but-unwired #9) — is now
  offered a turn from `Life.step()` on beats that produced no other act.
* An unimplemented want was spending the 15-minute budget. `converse` did nothing, stamped
  `last_act_at`, returned `acted=True`; a permanently hungry social stake would have eaten the floor
  forever and `explore` would never once have run. Found while verifying the fix above, and it would
  have silently defeated it.
* One road per deficit meant there was no other road. ATANOR asked for this itself: *"the measure did
  not move. Next time I should try a different road, not the same one harder."* `_road_for` now
  re-routes after `_ROAD_PATIENCE` attempts with no fall in severity. Measured: `speech_weak` had taken
  `self_improve` **300 times** at a flat 0.50 and now takes `self_diagnose`.

The expedition journal's last genuine entry is now today, not six days ago.

## The eye

The contract was already fixed and was not mine to invent: `attention`, `face_cortex`, `open_vocab`,
`scene_graph` and `vjepa_harness` all take HxWx3 uint8. The missing organ was **frame acquisition**, so
`packages/eye` adds the door, not a language. Screen, window, video file, camera and recorded CARLA
episodes all produce one `Frame`, and `source` is provenance that no perception organ may branch on.

**Speed**, after the owner's "프레임수가 너무 낮은데 사람 눈은 아니잖아":

```
  PIL ImageGrab      8–14 fps   (and SLOWER on small regions — it grabs the whole desktop and crops)
  mss                  60 fps   at 1080p
  dxcam                          a look costs 29 µs on a still screen
```

Two lanes, which is the part that makes it eye-like. Every frame gets change energy on a 32×18 grey
thumbnail (microseconds); only movers reach `frame_signature` (18 ms at 1080p, which alone would cap the
eye at ~54 fps). Fast/low-detail says THAT something moved; slow/high-detail says WHAT it is.

**Measured on CARLA frames** (800x600), which is the processing side and does not depend on the
screen changing:

```
  end to end          48.3 fps    — dominated by npz decompression from disk, not by perception
  fast lane           12.5 us     ->  80,145 fps ceiling
  slow lane (gate)     6.55 ms    ->     153 fps ceiling      (524x the fast lane)
```

So perception itself sustains ~150 fps and the episode loader is what caps this particular test. On a
live source there is no decompression, and the ceiling is the fast lane until something moves. In a
moving-vehicle scene 366 of 400 frames reached the gate — the world really is changing — and the gate
still suppressed 364 of those as mid-motion, attending to 2.

**MEASURED, later the same day**, against continuously rendering windows — the number this section
had been carrying as a gap:

```
  CARLA window, vehicle driving      31.5 fps fresh   attended 0.3%
  CARLA window, sample() fast lane   53.2 fps fresh
  City Sample viewport, idle         39.1 fps fresh   gate: predicted 235/236
  City Sample viewport, camera moving 32.6 fps fresh  gate: moving_wait 200, attended 5
```

Capture is ~32-39 fps and is GATE-bound, not capture-bound: `frame_signature` at 1929x1089 costs
more than the grab, which is why the thumbnail lane runs 1.7x faster on the same window. The idle
City Sample reading is the two-lane design working: 39 fps of fresh frames with essentially zero
recognition spend, because the pixels are redrawn but the scene is not changing.

Getting there required fixing a defect of mine. `WindowSource.grab()` rebuilt frame meta and copied
only `backend`, silently dropping `fresh` — the flag added precisely so a cached repeat could not be
counted as a capture. Two measurements therefore read "0 new frames" while the gate, on the SAME
looks, reported `moving_wait` 103 times out of 314. A guard dropped on one path is worse than no
guard, because the zero it produces looks like a measurement.

**Superseded note:** the original text below said this was unmeasurable because stdout goes to a
pipe. That was true of the desktop-screenshot attempt and irrelevant once a rendering window was
available. This session's stdout goes to
a pipe, not a visible console, so the attempt to make the screen change did not change it — 0 fresh
frames in 207,581 looks. Frames now carry `fresh` so a cached repeat can never be counted as a capture.
The real number gets taken against CARLA or City Sample, which render continuously.

**Lower bound, not this machine.** The floor is PIL + the thumbnail lane: no dxcam, no mss, no GPU.
dxcam is taken when present and never required.

## Depth ground truth — verified, not assumed

`scripts/carla_depth_recorder.py`, run under `D:\carla\env38\python.exe` (CARLA's client is Python
3.7/3.8; this repo is 3.13, and PyPI's `carla` for 3.13 is 0.9.5, four years stale). Synchronous mode
with a fixed delta, and the three sensors' frame numbers are **asserted equal**, not assumed — in
async mode RGB and depth can come from different world states, and the misregistration is small,
plausible and invisible in a thumbnail.

Verification on a real frame:

```
  registration   RGB edges ∩ depth edges / union = 0.114
                 depth shifted 6px               = 0.046      (2.5× — genuinely aligned)
  depth range    min 3.2 m   median 25.1 m   max 1000.00 m
  by label       Roads 5.2 m · RoadLine 5.7 m · Sidewalks 11.0 m
                 Vegetation 38.2 m · Buildings 52.3 m · Sky 1000.00 m
```

Sky sitting exactly on the 1000 m far plane, with roads nearest, is the single best check that the
24-bit packed depth was decoded correctly. (`ColorConverter.LogarithmicDepth` is for looking at, not
for training — it throws away precision exactly where depth is hard.)

`scripts/carla_corpus_audit.py` re-runs that check over the WHOLE corpus, sampling frames from every
episode, and reads the disk rather than a run log — a log says what a process believed, the disk says
what exists. Final state:

```
  episodes 26 good, 0 broken · 7,100 frames · misregistered dropped 0
  towns    Town01–07, Town10HD
  weather  all 8 conditions present, imbalance 5:2
  depth    26/26 episodes pass (Sky on the 1000m far plane)
```

It caught two things a log could not. First, the collection printed four episode lines and I nearly
reported "4 of 32 succeeded" — the disk held fourteen, `tail -6` had cut the rest. Second, weather was
picked by `weathers[ep % 8]`, which is balanced only if episode numbers are consecutive, and the run
used `--start` at 10, 14, 18, 22 — every offset a multiple of four. So the index landed on two or
three of eight entries: **12 of 14 episodes wet, three conditions never recorded**. A depth learner
trained on it would barely have seen a dry road and nothing would have said so. Weather is now chosen
by counting what is on disk and taking the rarest, which is self-correcting across restarts and
process splits; the top-up pass it drove closed all three gaps.

## Three bugs worth keeping on the record

1. **`video_mode` + `get_latest_frame()` hangs forever on a static desktop.** My first benchmark of it
   read 120 fps only because the terminal printing the benchmark was changing the screen — the
   measurement created the condition it was measuring. Removed; no capture thread.
2. **dxcam cannot open the eye alone.** Desktop Duplication reports change, not state, so on an idle
   machine `grab()` returns None forever including the first call. Primed from mss (which reads state)
   and updated from dxcam (which reads change) — each API doing what it was built for.
3. **`set_autopilot(True)` killed two collection runs, natively, with no traceback.** The default
   Traffic Manager port is 8000 and **8000 is Docker's on this machine**; CARLA spoke its RPC to
   Docker's HTTP server and the process vanished, printing one line and exiting 0. Found by walking the
   calls one at a time. Now `TM_PORT = 8005`.

## What is waiting for you

* **City Sample is not installed.** Epic Games Launcher is, but the demo needs your Epic login, which I
  cannot do. Start that download when you wake — D: has 1.25 TB free.
* **The eye's real frame rate under motion** — measurable the moment something renders continuously.
* **`_frontier_topic()` produces weak queries.** The forced expedition went out on the topic
  `"identical"` and brought back 0 consensus-backed sentences. Curiosity now leaves the house; what it
  asks for when it gets there is the next thing to fix.
* **GTA V Enhanced, later:** it installs BattlEye for GTA Online. Story-mode automation is a different
  matter from Online, and having synthetic input and screen capture running while Online is open
  carries a real account-ban risk. Worth isolating to story mode when that stage arrives.

## On the transfer question

You said you consider CARLA → City Sample / GTA depth transfer to be inference rather than something
to prove — ATANOR keeps evolving, and it recognises depth in a new rendering the way a person does when
they start playing a new game. That is a reasonable position and the pipeline is built for it: nothing
here forbids generalisation.

The one thing I would keep is the **measurement**, not as a gate but as information. Learn depth in
CARLA, freeze it, and read the error on City Sample frames. If it transfers, that is the first
continuous-modality evidence this project has. If it degrades, the number says by how much and where —
which is what tells you whether the next step is more CARLA variety, or fine-tuning on the target, or
something structural. Same instrument either way; only the interpretation differs.
