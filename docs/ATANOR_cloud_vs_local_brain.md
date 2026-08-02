# ATANOR — Cloud Brain vs Local Brain (the boundary, settled)

*2026-07-09. Written to end the back-and-forth: which lives where, and why the
local brain is the one that ultimately matters.*

## The one-line split

- **Cloud Brain = the shared, consensus-gated knowledge of the WORLD.** One graph,
  everyone reads it, it keeps growing in the cloud (alive when your PC is off).
- **Local Brain = the hyper-personalized knowledge of ONE user's life.** Your
  conversations, episodes, behaviour, interests, glasses — private, on-device.

Context understanding and hyper-personalized AGI are **Local, always.** They are
built from *your* moments; they must never leave your machine.

## The insight that reorders everything (the director's, 2026-07-09)

> A single person's surrounding life-events outnumber all the world's recorded
> knowledge. So the Local Brain — which *starts* as just a seed graph — will
> eventually grow to **thousands of times** the size of the entire Cloud Brain.

The Cloud is the shared **seed** everyone is handed. The Local is where the real
**mass** accrues, and with it the real AGI: a machine that knows *this* person's
world in a depth no shared model ever could. We are not building a big cloud with
small clients. We are building small shared seeds that each grow into vast,
private, personal minds.

## What lives where

| Concern | Cloud (shared) | Local (personal) |
|---|---|---|
| World facts (서울 is a city) | ✅ consensus-gated | reads a mirror |
| Web learning / book corpus | ✅ shared | — |
| Trained phase-space geometry | ✅ from world graph | also re-trains on personal graph |
| **Episodic memory** ("우리 그때 모터쇼") | ❌ | ✅ only here |
| **Behavioural interest** (dwell → 관심) | ❌ | ✅ only here |
| **Streaming prefilter** (typing → prime) | ❌ | ✅ only here |
| **Next-fact prediction** (personal) | ❌ | ✅ personal geometry |
| Smart-glasses / mic observations | ❌ | ✅ only here |
| User model, activity journal | ❌ | ✅ only here |

Rule of thumb: **is it a fact about the world, or a fact about the user?** World →
Cloud (gated, shareable). User → Local (private, never uploaded).

## The membrane (data flow rules)

- **Cloud → Local: read-only mirror.** The shared graph is available offline; the
  Local Brain stands on it as its seed and answers world-questions from it.
- **Local → Cloud: nothing personal, ever.** Only *generalizable, anonymized,
  consented* knowledge may ever flow up (opt-in), and only through the same
  consensus/evidence gates as any other contribution. Episodes, behaviour,
  glasses, preferences — these NEVER leave the device.
- **Privacy is structural, not a policy toggle.** The Local Brain is the vault;
  the membrane only lets impersonal knowledge out, and only when the user says so.

## Why this resolves the confusion

Earlier design talk crossed the boundary (predictive coding, temporal recall,
glasses) as if they were cloud features. They are not. They are the Local Brain's
reason for existing. The Cloud Brain's job is narrow and shared: keep a clean,
growing, hallucination-safe map of the world. Everything that makes ATANOR feel
like *your* mind — remembering the motor show, noticing you lingered at the
Genesis, finishing your sentence — is Local, private, and destined to dwarf the
cloud.

## Session mapping (2026-07-09 build)

Cloud-appropriate: consensus store, web firehose, book/PDF ingestion (shared
corpus), the world phase-space, closure candidates.
Local-only: `episodic_memory`, `streaming_prefilter`, behavioural interest
(`salience_from_behavior`), personal `fact_prediction`, user model, activity
journal. These degrade gracefully / are absent on the shared VM **by design** —
do not port them onto the cloud.
