# -*- coding: utf-8 -*-
"""The front end of hearing — what the cochlea does, before anything is learned.

    from packages.perception.ear import listen, cochleagram

WHAT ATANOR HAD, AND IT WAS NOT AN EAR. `voice_loop` has eighteen importers and consists of ASR and
TTS adapters: they hand speech to an external engine and hand back TEXT. Every sound that is not
speech is invisible to it, and even for speech what arrives is letters, not sound. Searching the whole
repository for `melspectrogram`, `log_mel`, `stft` or `cochlea` returns nothing. There was no ear.

THIS LAYER IS NOT LEARNED, ON PURPOSE. The cochlea is a filter bank with logarithmic frequency spacing
and logarithmic amplitude, and building it is not a shortcut around learning -- it is the organ. What
must be learned is what comes after: which sounds are the same thing, which is the ear's version of
the question `learned_signature` already answers for the eye, and the free oracle for it is
co-occurrence with what is seen. Nothing here does that yet; this is the surface it will run on.

THE OWNER'S CONSTRAINT, WHICH IS THE HARD ONE. "모든 종류의 소리를 인간이 듣듯이 알아야 하고, 소리마다
구분 라벨을 붙일 수 없고 그러면 안 되니까" -- every kind of sound, the way a person hears, and you
cannot and must not put a label on each one. Infant research says the same thing from the other side:
eight-month-olds segment a continuous stream into word-like units after two minutes of exposure, using
transitional probabilities alone, and the same mechanism works on non-linguistic tone sequences. So
the design is statistics over a fixed sensory surface, not a taxonomy of sounds.

NO AUDIO IS STORED, which is the eye's rule applied unchanged. A capture is reduced to a band-by-frame
array of floats and the samples are dropped; nothing is written to disk or sent anywhere.
"""
from __future__ import annotations

import numpy as np

SR = 16000
#: Human hearing runs roughly 20 Hz to 20 kHz; at 16 kHz sampling the top is 8 kHz, and the useful
#: floor for a room is well above the DC rumble.
F_LO, F_HI = 50.0, 7600.0
N_BANDS = 40
WIN, HOP = 512, 160        # 32 ms window, 10 ms hop -- the standard resolution for speech and close
                           # enough for transients that a door click is not smeared into the room.


def _mel(f):
    return 2595.0 * np.log10(1.0 + np.asarray(f, dtype=np.float64) / 700.0)


def _unmel(m):
    return 700.0 * (10.0 ** (np.asarray(m, dtype=np.float64) / 2595.0) - 1.0)


def filterbank(sr: int = SR, n_fft: int = WIN, n_bands: int = N_BANDS) -> np.ndarray:
    """Triangular filters spaced evenly on the mel scale — the cochlea's logarithmic frequency map.

    Written out rather than imported so hearing does not depend on a package being installed. It is
    forty lines of arithmetic and it is the same arithmetic everywhere."""
    edges = _unmel(np.linspace(_mel(F_LO), _mel(F_HI), n_bands + 2))
    bins = np.floor((n_fft + 1) * edges / sr).astype(int)
    bins = np.clip(bins, 0, n_fft // 2)
    fb = np.zeros((n_bands, n_fft // 2 + 1), dtype=np.float32)
    for i in range(n_bands):
        lo, mid, hi = bins[i], bins[i + 1], bins[i + 2]
        if mid > lo:
            fb[i, lo:mid] = np.linspace(0, 1, mid - lo, endpoint=False)
        if hi > mid:
            fb[i, mid:hi] = np.linspace(1, 0, hi - mid, endpoint=False)
    return fb


_FB = None


def cochleagram(x: np.ndarray, sr: int = SR) -> np.ndarray:
    """Sound as the ear delivers it: (frames, bands) of log energy.

    Log on both axes because the ear is logarithmic on both. A whisper and a shout differ by a factor
    of a thousand in pressure and by a manageable amount here, which is why the same representation
    can serve a quiet room and a passing truck without a gain schedule chosen by hand."""
    global _FB
    x = np.asarray(x, dtype=np.float32).ravel()
    if x.size < WIN:
        x = np.pad(x, (0, WIN - x.size))
    n = 1 + (x.size - WIN) // HOP
    idx = np.arange(WIN)[None, :] + HOP * np.arange(n)[:, None]
    frames = x[idx] * np.hanning(WIN).astype(np.float32)
    power = np.abs(np.fft.rfft(frames, axis=1)) ** 2
    if _FB is None or _FB.shape[1] != power.shape[1]:
        _FB = filterbank(sr, WIN, N_BANDS)
    return np.log(power @ _FB.T + 1e-8).astype(np.float32)


def onsets(cg: np.ndarray) -> np.ndarray:
    """Where energy rises — the ear's equivalent of the eye's 'something changed'.

    Spectral flux, rectified: only increases count. A sound ENDING is not an event in the same sense
    as a sound starting, which is why the negative half is discarded rather than taken in absolute
    value; the two are different things and averaging them would hide both."""
    if len(cg) < 2:
        return np.zeros(len(cg), dtype=np.float32)
    d = np.diff(cg, axis=0)
    flux = np.maximum(d, 0.0).sum(1)
    return np.concatenate([[0.0], flux]).astype(np.float32)


def microphones() -> list:
    """What can be listened with, checked rather than assumed — by STABLE id, not by display name.

    THE BUG THIS EXISTS TO AVOID, and it cost a capture. The device here is called 마이크(USB Audio).
    ffmpeg writes that to stderr in the console codepage, Python decodes it as something else, and the
    mangled string handed back to ffmpeg matches no device -- so a machine with a working microphone
    reported "nothing to listen with". Nothing was wrong with the ear or the hardware; a name made a
    round trip through a lossy channel.

    Every DirectShow device also has an ASCII alternative name, a pair of GUIDs, which cannot be
    mangled by any codepage. Those are preferred and the display names come after, so a device is
    still findable if the alternative line is missing."""
    import re
    import subprocess
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-list_devices", "true", "-f", "dshow",
                              "-i", "dummy"], capture_output=True, text=True, timeout=60,
                             errors="replace").stderr or ""
    except Exception:
        return []
    stable, shown = [], []
    lines = out.splitlines()
    for i, ln in enumerate(lines):
        if not re.search(r'"[^"]*"\s*\(audio\)', ln):
            continue
        m = re.search(r'"([^"]+)"\s*\(audio\)', ln)
        if m:
            shown.append(m.group(1))
        for nxt in lines[i + 1:i + 3]:
            alt = re.search(r'Alternative name\s+"([^"]+)"', nxt)
            if alt:
                stable.append(alt.group(1))
                break
    return stable + shown


def envelope(x, sr: int = SR) -> np.ndarray:
    """The spectral shape of a sound, with its overall loudness taken out."""
    c = cochleagram(x, sr).mean(0)
    return c - c.mean()


def same_word_different_throat(a: np.ndarray, b: np.ndarray, max_shift: int = 8) -> tuple:
    """Compare two sounds as WORDS rather than as voices. Returns (distance, shift).

    THE PROBLEM, measured before this existed. Four vowels spoken by three synthetic throats, and the
    nearest neighbour of every single one was another vowel from the SAME throat: same-vowel 0%,
    same-speaker 100%. Comparing spectra directly compares voices, and the word is buried under the
    speaker completely rather than merely obscured.

    TWO THINGS DIFFER BETWEEN SPEAKERS AND ONLY ONE IS HANDLED BY THE SOURCE-FILTER SPLIT. Pitch is
    the source and drops out with the cepstral truncation. Vocal tract LENGTH is the filter itself: a
    shorter tract puts every resonance higher by roughly one factor -- about 1.17 for a woman against
    a man, 1.3 for a child -- and that is the envelope moved, not noise on it.

    A UNIFORM SCALING OF FREQUENCY IS A TRANSLATION ON A LOG AXIS, and the cochlea is a log axis, so
    the correction is to slide one spectrum along the bands and take the best fit. No learning, no
    labels, no model of who is speaking. Same twelve sounds:

        plain          same vowel   0%    same speaker 100%
        shift-aligned  same vowel  75%    same speaker  25%

    and the shift it chooses tracks the throat rather than the vowel: -2 bands for the woman on all
    four vowels, -3 or -4 for the child. It is measuring the speaker, which is what lets the word
    through.

    HONEST BOUNDS. Those throats were synthesised with a UNIFORM scale factor, and real ones are not
    uniform -- the pharynx and the oral cavity grow at different rates, so a single shift is an
    approximation of a real speaker rather than a description of one. 75% is also not 100%. What this
    establishes is that the mechanism is right and cheap, not that speaker normalisation is finished.
    """
    ea, eb = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    best, at = float("inf"), 0
    for s in range(-max_shift, max_shift + 1):
        rb = np.roll(eb, s)
        sa, sb = (ea[s:], rb[s:]) if s > 0 else ((ea[:s], rb[:s]) if s < 0 else (ea, rb))
        if len(sa) < 12:
            continue
        d = float(np.linalg.norm(sa - sb) / np.sqrt(len(sa)) * np.sqrt(len(ea)))
        if d < best:
            best, at = d, s
    return best, at


class Talker:
    """A voice, calibrated once and then listened THROUGH — which is how people do it.

    WHAT THIS REPLACES AND WHY. `same_word_different_throat` searches for the best band-shift per
    COMPARISON, and it works: 0% to 75% same-vowel on a small set. But asked how humans manage a
    stranger, the literature does not describe that at all.

        Joos 1948                a vowel is heard against the OTHER vowels that talker produces.
        Ladefoged & Broadbent    a carrier phrase before a target changes what the target is heard
        1957                     as -- the voice is calibrated first, the word decided after.

    Refitting per comparison is a different thing: it lets a confusable pair be bent into agreement,
    and it treats the same person as a new stranger every time they speak. Measured over six vowels
    and four throats:

        plain                             same vowel 33%   same speaker 67%
        per-pair shift                               62%                38%
        one shift per voice (this)                   71%                29%
        intrinsic, no context at all                 54%                42%

    And the reason is in the spread. Estimated from ONE word, the woman's shift ranges -5 to -2;
    estimated from a handful of her words it is -2 and stays there. A single word is a bad estimate
    of a throat, which is exactly Joos's point arriving as a number.

    The calibration it finds is monotone in the true tract length -- +1, 0, -2, -4 for scales 0.91,
    1.00, 1.17, 1.30 -- so it is measuring the speaker rather than fitting the words.

    Still synthetic, still uniform scaling, still not 100%. What is established is that calibrating
    per VOICE beats calibrating per comparison, and that a stranger's first word is interpretable at
    54% before any calibration exists at all."""

    def __init__(self, max_shift: int = 8):
        self.max_shift = max_shift
        self.shift = 0
        self.heard = 0

    @staticmethod
    def _roll(v, s):
        r = np.roll(v, s)
        if s > 0:
            r[:s] = v[0]
        elif s < 0:
            r[s:] = v[-1]
        return r

    def calibrate(self, theirs: list, reference: list) -> int:
        """Set the eyeglass from a stretch of this voice, against a voice already known.

        Not from one word. The point of the mean is that whatever they happened to say averages out
        and what remains is the throat."""
        if not theirs or not reference:
            return self.shift
        t = np.mean([np.asarray(x, dtype=np.float64) for x in theirs], axis=0)
        r = np.mean([np.asarray(x, dtype=np.float64) for x in reference], axis=0)
        self.shift = int(min(range(-self.max_shift, self.max_shift + 1),
                             key=lambda s: float(np.linalg.norm(r - self._roll(t, s)))))
        self.heard = len(theirs)
        return self.shift

    def hear(self, x) -> np.ndarray:
        """One sound from this voice, put on the calibrated scale."""
        return self._roll(np.asarray(x, dtype=np.float64), self.shift)


def without_knowing_the_voice(v) -> np.ndarray:
    """A stranger's first word, before any calibration exists — the intrinsic route.

    Its own spectral centre of mass stands in for the throat, since a shorter tract puts everything
    higher. Weaker than calibrating (54% against 71%) and it needs NOTHING, which is what makes it
    the right thing to fall back on rather than refusing to listen until enough has been heard."""
    v = np.asarray(v, dtype=np.float64)
    w = np.maximum(v - v.min(), 1e-9)
    c = float((w * np.arange(len(v))).sum() / w.sum())
    return Talker._roll(v, int(round(len(v) / 2 - c)))


def listen(seconds: float = 3.0, sr: int = SR, device: str | None = None):
    """One capture from whatever microphone this machine has, as a cochleagram.

    TWO ROUTES, because one of them is not installed and a missing package is not a missing sense.
    `sounddevice` is the tidy way and is absent here; ffmpeg is present and can open the same DirectShow
    device. The eye already learned the general form of this -- do not accept the first refusal, and do
    not mistake "the library I reached for is missing" for "this machine cannot hear".

    Returns None when there is genuinely nothing to listen with, which is a fact about now rather than
    a verdict: a microphone can be plugged in a minute later.

    THE SAMPLES DO NOT SURVIVE THIS CALL. They become a (frames, bands) float array and are dropped --
    nothing is written to disk or sent anywhere, exactly as `eyes.grab` drops pixels."""
    try:
        import sounddevice as sd
        rec = sd.rec(int(seconds * sr), samplerate=sr, channels=1, dtype="float32", device=device)
        sd.wait()
        return cochleagram(rec[:, 0], sr)
    except Exception:
        pass
    import subprocess
    mics = [device] if device else microphones()
    for m in mics:
        try:
            out = subprocess.run(
                ["ffmpeg", "-v", "quiet", "-f", "dshow", "-i", f"audio={m}", "-t", str(seconds),
                 "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"],
                capture_output=True, timeout=int(seconds) + 60).stdout
            if out:
                return cochleagram(np.frombuffer(out, dtype=np.float32), sr)
        except Exception:
            continue
    return None


def from_file(path, sr: int = SR):
    """A cochleagram from a media file, resampled through ffmpeg so any container works."""
    import subprocess
    try:
        out = subprocess.run(
            ["ffmpeg", "-v", "quiet", "-i", str(path), "-f", "f32le", "-ac", "1",
             "-ar", str(sr), "-"], capture_output=True, timeout=180).stdout
        if not out:
            return None
        return cochleagram(np.frombuffer(out, dtype=np.float32), sr)
    except Exception:
        return None
