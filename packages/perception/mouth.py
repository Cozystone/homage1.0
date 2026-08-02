# -*- coding: utf-8 -*-
"""A mouth ATANOR owns — the vocal tract, not a voice downloaded.

    from packages.perception.mouth import Gesture, say, imitate

WHAT WAS THERE. `FishTTSAdapter`'s own docstring says it is "an adapter shell with safe fallback
semantics" that "intentionally does not download weights, clone voices, or persist generated audio",
and it has one non-test importer. Searching the repository for `formant`, `glottal` or
`source_filter` returns nothing. ATANOR could ask an external engine to speak for it and had no mouth.

WHY SOURCE-FILTER AND NOT A NEURAL VOICE, which is the owner's own instinct and it is the right one.
Human phonation is a source and a filter: vocal folds make a buzz, the tract shapes it into
resonances, the lips radiate it. Modelling that directly is a few hundred lines of arithmetic, runs on
a CPU in real time, and every parameter MEANS something -- this is the pitch, this is where the tongue
is. A neural voice sounds better and is a large model behind a GPU, which is the opposite of the
constraint this project works under.

AND THE HISTORICAL OBJECTION IS ABOUT CONTROL, NOT SUBSTRATE. Formant synthesis sounded robotic
because its parameter trajectories were AUTHORED -- someone wrote down what the formants should do.
Nothing about the substrate requires that. If the trajectories are found by listening, the substrate
is not the ceiling.

WHICH IS WHY THE EAR HAD TO COME FIRST. `imitate` speaks, listens to itself with `ear.cochleagram`,
and moves toward what it heard. The oracle is free, unlimited and unlabelled: you do not need anyone
to tell you whether you sounded like the target, you listen. This is the owner's "자기가 말한 걸 또
자기가 들으며 자가개선", and it is the same principle as their clay proposal for vision -- keep a
thing as something you can MAKE, and score by whether what you made matches what you perceived.
Sound is the better-posed half of that idea: a waveform target is exact where a 3D shape target is not.

HONEST ABOUT THE CEILING. This will not sound like a person soon. What it is: a mouth that is ours,
runs anywhere, is scorable against an objective, and can improve without a human labelling anything.
A polished voice stays a plugin, the same tiering SPLATRA already uses.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

SR = 16000


@dataclass
class Gesture:
    """One articulatory posture held for a while — what the mouth is DOING, not what it says.

    Formants are the resonances of the tract, and they are the vowel: roughly (700, 1220, 2600) is an
    /a/, (300, 2300, 3000) an /i/, (350, 800, 2600) an /u/. Stored as numbers rather than as letters
    because the letters are a description of these, not the other way round."""
    f0: float = 120.0                      # pitch of the buzz, Hz
    formants: tuple = (700.0, 1220.0, 2600.0)
    bandwidths: tuple = (80.0, 90.0, 120.0)
    voiced: float = 1.0                    # 1 buzz, 0 breath, between = both
    amplitude: float = 0.5
    seconds: float = 0.18
    # --- voice quality: not extra machinery, the same organ held differently -------------------
    #: spectral tilt. Above 0 the source loses its highs and the voice goes soft and breathy; below,
    #: it keeps them and the voice goes pressed and hard. This is most of what "tone" is.
    tilt: float = 0.0
    #: cycle-to-cycle irregularity. A little is life; a lot is a creak, a tremble, or strain.
    jitter: float = 0.01
    #: silence before the source starts. A stop consonant is a closure and then a release, and the
    #: closure is not the absence of a sound -- it is part of one.
    silence: float = 0.0
    #: broadband noise at the release. What makes a /b/ a /b/ rather than a soft vowel onset.
    burst: float = 0.0


def coloured_by(hormones: dict, base: Gesture | None = None) -> Gesture:
    """The same posture, spoken from a different state — which is what tone IS.

    OWNER'S DESIGN, and the reason it is a few lines rather than a subsystem: emotion in a voice is
    not extra machinery bolted onto speech, it is the SAME parameters held differently. A person under
    stress does not acquire a new organ; their folds tense, their pitch rises, their cycles get less
    regular, their source loses its softness. Every one of those is already a field on `Gesture`.

    The mapping follows what the endocrine field already means elsewhere in this system rather than
    inventing a psychology for the voice:

        noradrenaline, cortisol   arousal and threat -> pitch up, cycles less regular, source pressed
        serotonin                 settledness        -> pitch down, steady, softer
        oxytocin                  warmth             -> breathier, gentler, quieter

    These are CORRELATES and the file should say so plainly: a listener hearing a raised, irregular,
    pressed voice would call it agitated, and that is a fact about the acoustics, not a claim that
    anything is felt. The same restraint the rest of the perception lane keeps."""
    L = dict(hormones or {})
    g = base or Gesture()

    def lv(k):
        return float(np.clip(L.get(k, 0.0), 0.0, 1.5))
    arousal = 0.6 * lv("noradrenaline") + 0.6 * lv("cortisol")
    calm = 0.5 * lv("serotonin")
    warm = 0.5 * lv("oxytocin")
    return Gesture(
        f0=float(np.clip(g.f0 * (1.0 + 0.35 * arousal - 0.12 * calm), 60.0, 350.0)),
        formants=g.formants, bandwidths=g.bandwidths,
        voiced=float(np.clip(g.voiced - 0.15 * warm, 0.0, 1.0)),
        amplitude=float(np.clip(g.amplitude * (1.0 + 0.30 * arousal - 0.15 * warm), 0.05, 1.0)),
        seconds=g.seconds,
        tilt=float(np.clip(g.tilt - 0.35 * arousal + 0.30 * (calm + warm), -0.9, 0.9)),
        jitter=float(np.clip(g.jitter + 0.05 * arousal - 0.005 * calm, 0.001, 0.12)),
        silence=g.silence, burst=g.burst)


def _glottal(n: int, f0: float, sr: int, jitter: float = 0.01, rng=None) -> np.ndarray:
    """The vocal folds: a pulse train, not a sine.

    A sine has one frequency and a voice has a whole harmonic stack -- the stack is what the tract
    then shapes, so a sine source cannot produce a vowel no matter what filter follows it. The small
    jitter is not decoration: a perfectly periodic source is the single most machine-like thing a
    synthesiser can do, and real folds never repeat exactly."""
    rng = rng or np.random.default_rng(0)
    out = np.zeros(n, dtype=np.float32)
    period = sr / max(20.0, f0)
    t = 0.0
    while t < n:
        i = int(t)
        if i < n:
            out[i] = 1.0
        t += period * (1.0 + jitter * float(rng.standard_normal()))
    return out


def _resonator(x: np.ndarray, f: float, bw: float, sr: int) -> np.ndarray:
    """One formant: a two-pole filter, the same maths as a tube resonance."""
    r = float(np.exp(-np.pi * bw / sr))
    theta = 2.0 * np.pi * f / sr
    a1, a2 = -2.0 * r * np.cos(theta), r * r
    g = (1.0 - 2.0 * r * np.cos(theta) + r * r)
    y = np.zeros_like(x)
    y1 = y2 = 0.0
    for i in range(len(x)):
        v = g * x[i] - a1 * y1 - a2 * y2
        y[i] = v
        y2, y1 = y1, v
    return y


def _one(g: Gesture, sr: int, rng) -> np.ndarray:
    n = max(1, int(g.seconds * sr))
    buzz = _glottal(n, g.f0, sr, jitter=g.jitter, rng=rng)
    breath = rng.standard_normal(n).astype(np.float32) * 0.5
    src = g.voiced * buzz + (1.0 - g.voiced) * breath
    if g.burst > 0.0:
        k = max(1, int(0.006 * sr))                     # a release is milliseconds long
        src[:k] += g.burst * rng.standard_normal(k).astype(np.float32)
    if g.tilt != 0.0:
        # one-pole tilt on the SOURCE, which is where breathiness and pressedness live -- the tract
        # is unchanged when a person softens their voice, the folds are.
        a = float(np.clip(g.tilt, -0.95, 0.95))
        acc = 0.0
        for i in range(n):
            acc = src[i] + a * acc
            src[i] = acc
    y = np.zeros(n, dtype=np.float32)
    for f, bw in zip(g.formants, g.bandwidths):
        y += _resonator(src, float(f), float(bw), sr)
    y = np.diff(np.concatenate([[0.0], y]))              # radiation at the lips: a difference
    peak = float(np.abs(y).max())
    y = (g.amplitude * y / peak).astype(np.float32) if peak > 0 else y.astype(np.float32)
    if g.silence > 0.0:
        y = np.concatenate([np.zeros(int(g.silence * sr), dtype=np.float32), y])
    return y


def glide(a: Gesture, b: Gesture, seconds: float = 0.06, steps: int = 10) -> list:
    """The move from one posture to another — and this is where speech actually lives.

    THE OWNER'S WORRY, WHICH WAS CORRECT. Held postures mumble by construction. /ba/, /da/ and /ga/
    have the SAME vowel; what distinguishes them is which direction F2 is coming from as the mouth
    opens. A synthesiser that only holds targets cannot say any of them, no matter how good the
    targets are, because their identity is not in a target at all.

    So a transition is a first-class thing here rather than a smoothing detail. Ten short gestures
    stepping between two postures, which is enough resolution for the ear to hear a direction."""
    out = []
    for i in range(steps):
        t = (i + 1) / steps
        out.append(Gesture(
            f0=a.f0 + (b.f0 - a.f0) * t,
            formants=tuple(f1 + (f2 - f1) * t for f1, f2 in zip(a.formants, b.formants)),
            bandwidths=b.bandwidths, voiced=a.voiced + (b.voiced - a.voiced) * t,
            amplitude=a.amplitude + (b.amplitude - a.amplitude) * t,
            seconds=seconds / steps, tilt=a.tilt + (b.tilt - a.tilt) * t,
            jitter=a.jitter + (b.jitter - a.jitter) * t))
    return out


def say(gestures, sr: int = SR, seed: int = 0) -> np.ndarray:
    """Turn postures into sound. Source, filter, radiation — the three things a mouth does."""
    rng = np.random.default_rng(seed)
    seq = [gestures] if isinstance(gestures, Gesture) else list(gestures)
    out = [_one(g, sr, rng) for g in seq]
    return np.concatenate(out) if out else np.zeros(1, dtype=np.float32)


def _heard(x, sr: int = SR) -> np.ndarray:
    """What the ear makes of a sound, as SHAPE rather than as level.

    A KNOWN BLIND SPOT, LEFT IN ON PURPOSE. This recovers F2 and F3 almost exactly and gets F1 wrong
    every time, always too high: at f0 155 Hz the source puts harmonics at 310, 465, 620 Hz, and their
    energy dominates the low bands where F1 lives, so the comparison is nearly blind to it.

    I tried the obvious repair -- subtract each frame's own mean, removing level and source tilt to
    leave the resonance pattern -- and it made the DISTANCE better and the ANSWER worse: F2 error went
    from about nothing to 89% while the score improved. Optimising my own proxy moved the search away
    from the truth, which was only visible because this experiment synthesises its targets and
    therefore HAS the truth to check against.

    That is the third time in one day that a proxy turned out to be anti-correlated with the goal it
    stood in for, so the rule is now explicit here: when ground truth exists, score on ground truth,
    and treat any hand-made distance as a suspect until it has been checked against it.

    THE ACTUAL FIX IS THE SEPARATION THIS FILE IS NAMED AFTER. The masking is not a quirk of the mel
    scale, it is the source showing through the filter: at f0 155 Hz the harmonics form a comb 155 Hz
    apart, and the low mel bands are narrower than that, so the comb prints itself on the very bands
    that carry F1. Averaging over time does not remove it because it is there in every frame.

    A truncated cepstrum removes it properly. The log spectrum of a voiced sound is the tract's slowly
    varying envelope PLUS the source's fast ripple; a DCT puts those at different quefrencies, so
    keeping the low coefficients keeps the tract and drops the source. That is what MFCCs have always
    been for, and it is the same source-filter split the synthesiser is built on -- the comparison
    should be made in the same terms as the thing being compared.

    Confirmed the way everything else here is: not by the distance getting smaller, but by the
    formant error against targets whose formants we set ourselves."""
    from scipy.fftpack import dct

    from packages.perception.ear import cochleagram
    c = cochleagram(x, sr).mean(0)
    return dct(c, type=2, norm="ortho")[1:14]        # drop c0: overall loudness is not identity


def distance(a: np.ndarray, b: np.ndarray) -> float:
    """How different two sounds are TO THE EAR, which is the only comparison that matters here.

    Not waveform difference: two identical-sounding vowels can be out of phase and differ hugely
    sample by sample. The ear's own representation is the judge, which is exactly why the ear had to
    exist before the mouth could be scored."""
    u, v = _heard(a), _heard(b)
    return float(np.linalg.norm(u - v) / max(1e-6, np.linalg.norm(v)))


def imitate(target: np.ndarray, *, rounds: int = 60, seed: int = 0, sr: int = SR) -> dict:
    """Move the mouth until what it hears itself make resembles what it heard.

    Deliberately the simplest search that can work -- propose a nearby posture, keep it if the ear
    says it is closer. No gradient, no model of the mapping. If a hill-climb over five numbers can
    close most of the gap, then the substrate carries the information and the interesting work is in
    the CONTROL, which is the claim this file rests on. If it cannot, the substrate is wrong and that
    is worth learning cheaply.

    Returns the posture found, the distance before and after, and the number of accepted moves, so a
    run that improved nothing cannot look like a run that worked."""
    rng = np.random.default_rng(seed)
    secs = max(0.12, len(target) / sr)
    # START WHERE LISTENING SAYS TO START. The first version began from one default posture and hill-
    # climbed, and the control caught it: the best of forty RANDOM postures scored 0.341 on /i/ while
    # the climb reached 0.435. A search that loses to guessing is not a search, and the fix is not a
    # cleverer step rule -- it is to stop pretending one starting point is enough. Listening to a
    # handful of postures first costs a handful of syntheses and is what the control was already
    # doing better.
    starts = [Gesture(seconds=secs)]
    for _ in range(11):
        starts.append(Gesture(
            f0=float(rng.uniform(80, 260)),
            formants=tuple(sorted(float(rng.uniform(lo, hi))
                                  for lo, hi in ((250, 900), (700, 2600), (2000, 3600)))),
            voiced=1.0, seconds=secs))
    scored = sorted(((distance(say(s, sr), target), i) for i, s in enumerate(starts)))
    g = starts[scored[0][1]]
    best = scored[0][0]
    start, accepted = distance(say(Gesture(seconds=secs), sr), target), 0
    for _ in range(rounds):
        c = Gesture(f0=float(np.clip(g.f0 * np.exp(0.10 * rng.standard_normal()), 60, 350)),
                    formants=tuple(float(np.clip(f * np.exp(0.09 * rng.standard_normal()), 150, 4000))
                                   for f in g.formants),
                    bandwidths=g.bandwidths,
                    voiced=float(np.clip(g.voiced + 0.15 * rng.standard_normal(), 0.0, 1.0)),
                    amplitude=g.amplitude, seconds=g.seconds)
        d = distance(say(c, sr), target)
        if d < best:
            g, best, accepted = c, d, accepted + 1
    return {"gesture": g, "distance_before": start, "distance_after": best,
            "improvement": start - best, "accepted_moves": accepted,
            "best_of_starts": scored[0][0]}


@dataclass
class Voice:
    """A mouth with a memory of postures it has found. The beginning of a repertoire.

    Deliberately data and not weights, for the same reason `naming.NameBook` is: a posture that turns
    out wrong is deleted, not trained away."""
    postures: dict = field(default_factory=dict)

    def learn(self, name: str, target: np.ndarray, **kw) -> dict:
        r = imitate(target, **kw)
        self.postures[name] = r["gesture"]
        return r

    def utter(self, names, sr: int = SR) -> np.ndarray:
        gs = [self.postures[n] for n in names if n in self.postures]
        return say(gs, sr) if gs else np.zeros(1, dtype=np.float32)
