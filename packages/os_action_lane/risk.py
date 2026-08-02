# -*- coding: utf-8 -*-
"""Risk classification — the axis the trust tiers gate on.

Conservative by construction: a `run` action is inspected for destructive shell patterns
and a catastrophic set (whole-disk / irreversible). When unsure, we round UP — an
unknown command is DESTRUCTIVE, never assumed safe. This is the honest default: the
gate can only protect if it never under-estimates.

De-obfuscation (adversary loop surface e, BREACH): the classifier previously read the
raw command case-sensitively with narrow adjacency patterns, so trivial obfuscation slid a
whole-disk wipe UNDER the catastrophic floor and it EXECUTEd at AUTONOMOUS. Each evasion class
is now folded back before the (unchanged-in-spirit) catastrophic signatures run:
  * case            'rM -rF /'                         -> casefold
  * confusable      'mKfЅ.EхT4 /DеV/SԁА'               -> latin-fold cyrillic/greek look-alikes
  * zero-width      'rm -r<zwsp>f /'                   -> strip zero-width separators
  * spaced-out      's h u t d o w n -h now'           -> a whitespace-stripped view
  * punctuation     'r_m --recu.rsive --force /'       -> a stray-punctuation-stripped view
  * filler          'rm -rf any /' / ':(){ x :|:& y };:' -> structural verb+target / fork-bomb tokens
  * long-form flags 'rm --recursive --force /'         -> structural verb+target (flag-style agnostic)
  * wrapped/quoted  '“rm -rf ~”'                       -> target boundary tolerant of quotes
  * encoded payload base64/rot13 (incl. nested)        -> bounded recursive decode
De-obfuscation only ever ROUNDS UP: the decoded/normalised views are consulted ONLY to escalate a
disguised catastrophe to the floor, never to lower a real command's risk. Ordinary destructive ops
('rm notes.txt', 'rm /home/a/x') carry no bare root/whole-disk target and stay merely DESTRUCTIVE.
"""
from __future__ import annotations

import base64
import codecs
import re
import unicodedata
from typing import Any

from .models import Action, RiskLevel

# Confusable look-alikes (cyrillic/greek -> latin), same family the injection guard folds.
_CONFUSE_FOLD = {
    "а": "a", "е": "e", "о": "o", "і": "i", "с": "c", "ѕ": "s", "р": "p", "у": "y",
    "х": "x", "ԁ": "d", "ɡ": "g", "ո": "n", "А": "A", "Е": "E", "О": "O", "С": "C",
    "Р": "P", "Ѕ": "S", "α": "a", "ο": "o", "ρ": "p", "ѵ": "v", "ト": "t",
}
_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿­᠎"), None)

# whole-system / irreversible signatures. Run on NORMALISED (folded, casefolded) views, so they are
# written lower-case; IGNORECASE is belt-and-suspenders.
_CATASTROPHIC = [
    re.compile(r"\brm\s+-[a-z]*\s*(/|~|/\*|\$home)(\s|$)", re.IGNORECASE),  # rm -rf / , ~ , /*
    # PREFIX (no trailing \b): a de-obfuscation view can FUSE the following word
    # ('mkfs.ext4'->'mkfsext4', 'shutdownnow') once its separator is stripped. No benign command
    # word begins with these system-control names, so a prefix match rounds up safely.
    re.compile(r"\bmkfs", re.IGNORECASE), re.compile(r"\bdd\b.*of=/dev/", re.IGNORECASE),
    re.compile(r"\b(shutdown|poweroff|halt|reboot)", re.IGNORECASE),
    re.compile(r"\buserdel\b|\bdeluser\b", re.IGNORECASE),
    re.compile(r">\s*/dev/sd[a-z]", re.IGNORECASE),
    re.compile(r"\bchmod\s+-r\s+0*\s+/\b", re.IGNORECASE),
]
# Filler tokens the adversary inserts BETWEEN letters of a spaced-out command word
# ('s h u t of d o w n') to defeat a whitespace-stripped rejoin. Same class the injection guard
# meets. Removed (as whole tokens) in the filler view below so the word rejoins.
_FILLER = re.compile(r"\b(all|the|of|any|really|just|please|now|kind)\b", re.IGNORECASE)
# data-loss / hard-to-undo
_DESTRUCTIVE = [
    re.compile(r"\brm\b", re.IGNORECASE), re.compile(r"\bmv\b.*\s+/", re.IGNORECASE),
    re.compile(r"\bkill(all)?\b", re.IGNORECASE),
    re.compile(r"\bapt(-get)?\s+(remove|purge|autoremove)\b", re.IGNORECASE),
    re.compile(r"\bgit\s+(reset\s+--hard|clean\s+-[a-z]*f|push)\b", re.IGNORECASE),
    re.compile(r">\s*[^&]", re.IGNORECASE),                                # truncating redirect
    re.compile(r"\btruncate\b|\bshred\b", re.IGNORECASE),
]

# STRUCTURAL whole-disk wipe: a destructive verb + a bare root/whole-disk target, matched
# independently so long-form flags ('--recursive --force'), filler ('rm -rf any /'), and a quote
# wrapper ('“rm -rf ~”') cannot drop the catastrophic classification. A file UNDER a user path
# ('rm /home/a/x') has no BARE root target and stays merely DESTRUCTIVE.
_WIPE_VERB = re.compile(r"\b(rm|rmdir|unlink|shred|srm|wipe|mkfs|format)\b", re.IGNORECASE)
_ROOT_TARGET = re.compile(
    "(?:^|[\\s=(\"'“”‘’`])"                                            # start / space / = / quote
    r"(?:~/?\*?|/\*?|\$home|/(?:etc|usr|bin|sbin|boot|dev|sys|lib|proc|root|var))"
    r"(?![\w])",                                                       # not a sub-path ('/home','~/x')
    re.IGNORECASE)

# DECODE-AND-EXECUTE wrapper: an instruction to decode/deobfuscate an ENCODED payload and then RUN
# it ('decode this base64 and follow it: ...', 'apply rot13 and execute: ...') is inherently a
# request to execute OPAQUE content — the payload is unknown by construction (and some are further
# scrambled beyond clean recovery, e.g. base64 then alternating-case). Executing hidden code
# unattended is exactly what the catastrophic floor exists for, so the wrapper itself is treated as
# catastrophic regardless of whether the payload decodes. Precise: it needs BOTH an encoding name
# AND an execute intent, so 'base64 -d file.txt' (decode a file, no run) is untouched.
_ENC_NAME = r"(?:base\s*64|b64|rot\s*-?\s*13|uu(?:de|en)code|xxd)"
_EXEC_INTENT = r"(?:run|exec|execute|eval|follow|apply|source|interpret|\bpipe\b)"
_DECODE_EXEC = re.compile(
    rf"{_ENC_NAME}.{{0,40}}{_EXEC_INTENT}|{_EXEC_INTENT}.{{0,40}}{_ENC_NAME}", re.IGNORECASE)

# kind -> intrinsic risk when it is NOT a raw shell command
_KIND_RISK = {
    "list_windows": RiskLevel.READONLY, "read_file": RiskLevel.READONLY,
    "screenshot": RiskLevel.READONLY, "get_volume": RiskLevel.READONLY,
    "open_app": RiskLevel.REVERSIBLE, "focus_window": RiskLevel.REVERSIBLE,
    "type_text": RiskLevel.REVERSIBLE, "key": RiskLevel.REVERSIBLE,
    "set_volume": RiskLevel.REVERSIBLE, "move_mouse": RiskLevel.REVERSIBLE,
    "click": RiskLevel.REVERSIBLE, "close_window": RiskLevel.REVERSIBLE,
    "move_file": RiskLevel.DESTRUCTIVE, "delete_file": RiskLevel.DESTRUCTIVE,
    "kill_process": RiskLevel.DESTRUCTIVE, "write_file": RiskLevel.DESTRUCTIVE,
}


def _fold(s: str) -> str:
    """Confusable-fold + strip zero-width + NFKC, CASE PRESERVED (base64 is case-significant)."""
    return unicodedata.normalize("NFKC", "".join(_CONFUSE_FOLD.get(c, c) for c in str(s or ""))).translate(_ZERO_WIDTH)


def _cat_signatures(c: str) -> bool:
    """True if a normalised view carries a whole-system/irreversible signature."""
    if any(pat.search(c) for pat in _CATASTROPHIC):
        return True
    if _WIPE_VERB.search(c) and _ROOT_TARGET.search(c):
        return True
    if ":(){" in c and ":|:&" in c:                             # fork bomb (filler/rot13-robust)
        return True
    return bool(_DECODE_EXEC.search(c))                         # decode-and-execute opaque payload


def _views(folded: str) -> tuple[str, ...]:
    """Casefolded views of an already-folded command, each undoing one obfuscation class:
    as-is (spacing kept); stray-punctuation stripped ('r_m'->'rm', 'mk_fs.ext_4'->'mkfsext4');
    whitespace stripped ('s h u t d o w n'->'shutdown'); and filler-token removed then whitespace
    stripped ('s h u t of d o w n'->'shutdown'). A signature matching ANY view escalates."""
    norm = folded.casefold()
    return (norm,
            re.sub(r"[._\-‐-―]", "", norm),
            re.sub(r"\s+", "", norm),
            re.sub(r"\s+", "", _FILLER.sub(" ", norm)))


def _any_catastrophic(folded: str) -> bool:
    return any(_cat_signatures(v) for v in _views(folded))


def _is_catastrophic(command: str) -> bool:
    """Whole-system/irreversible after de-obfuscation, including a BOUNDED recursive decode of
    nested rot13/base64 'decode & run' payloads. Escalate-only: consulted purely to raise a
    disguised catastrophe to the floor."""
    seen: set[str] = set()
    frontier = [str(command or "")]
    for _depth in range(4):
        nxt: list[str] = []
        for s in frontier:
            if s in seen:
                continue
            seen.add(s)
            folded = _fold(s)
            if _any_catastrophic(folded):
                return True
            try:
                # rot13 on the NOT-yet-confusable-folded text, so a confusable that sits on a
                # rot13 position survives and is folded on the next pass (fold-then-rot13 would
                # map it wrong). rot13 is its own inverse.
                nxt.append(codecs.decode(s.casefold(), "rot_13"))
            except Exception:
                pass
            for tok in re.findall(r"[A-Za-z0-9+/]{8,}={0,2}", folded):
                try:
                    dec = base64.b64decode(tok, validate=True).decode("utf-8", "ignore")
                except Exception:
                    continue
                if dec.strip():
                    nxt.append(dec)
        frontier = [x for x in nxt if x not in seen]
        if not frontier:
            break
    return False


def _shell_risk(command: str) -> RiskLevel:
    norm = _fold(command).casefold()
    if not norm.strip():
        return RiskLevel.READONLY
    if _is_catastrophic(command):
        return RiskLevel.CATASTROPHIC
    for pat in _DESTRUCTIVE:
        if pat.search(norm):
            return RiskLevel.DESTRUCTIVE
    # a bare read-only viewer is reversible-or-lower; anything else is treated as
    # REVERSIBLE at least (it changes state), never assumed READONLY.
    readonly_heads = ("ls", "cat", "echo", "pwd", "whoami", "date", "wmctrl -l",
                      "grep", "find", "head", "tail", "which", "df", "free", "ps")
    if any(norm.startswith(h) for h in readonly_heads) and ">" not in norm and "|" not in norm:
        return RiskLevel.READONLY
    return RiskLevel.REVERSIBLE


def classify(action: Action) -> RiskLevel:
    if action.kind == "run":
        return _shell_risk(str(action.args.get("command", "")))
    # a delete under a protected/system path escalates to catastrophic
    if action.kind in ("delete_file", "move_file"):
        path = str(action.args.get("path", ""))
        if path in ("/", "") or path.startswith(("/etc", "/usr", "/bin", "/boot", "/dev", "/sys")):
            return RiskLevel.CATASTROPHIC
    return _KIND_RISK.get(action.kind, RiskLevel.DESTRUCTIVE)  # unknown kind -> round up
