# -*- coding: utf-8 -*-
"""D1 latency surgery — in-process cProfile of the live answer entry (_chat_atanor_impl),
so we see WHERE the warm 4-5s goes, stage by stage. Mirrors the engine's sys.path."""
from __future__ import annotations
import cProfile, io, pstats, sys, time, asyncio
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "api"))
# EXACT replica of app.main._configure_local_package_paths: reverse-sorted so `model` is
# inserted AFTER `user_model` and wins `import model` (the self-vendoring shadow trap).
_pkgs = ROOT / "packages"
for _d in sorted(_pkgs.iterdir(), reverse=True):
    if (_d / "pyproject.toml").exists() or (_d / _d.name / "__init__.py").exists():
        if str(_d) not in sys.path:
            sys.path.insert(0, str(_d))

from app.routers.dual_brain import _chat_atanor_impl, AtanorChatRequest  # noqa: E402


def _ask(q: str):
    req = AtanorChatRequest(message=q, language="ko", web_search=False)
    return asyncio.get_event_loop().run_until_complete(_chat_atanor_impl(req))


def main() -> int:
    # warm every lazy loader first (pack, stores, cartridge, Kiwi) so the profile shows the
    # STEADY-STATE per-query cost, not one-time cold builds.
    print("warming…", flush=True)
    for q in ("서울은 어디야", "행복이 뭐야", "중력 왜생기는거임"):
        try:
            _ask(q)
        except Exception as e:
            print("  warm err:", type(e).__name__, str(e)[:80])
    # timed warm runs
    probe = ["행복이 뭐야", "블랙홀이 뭐야", "민주주의가 뭐야", "커피가 뭐야"]
    print("=== warm per-query wall ===")
    for q in probe:
        t = time.time()
        try:
            r = _ask(q)
            print(f"  {time.time()-t:5.2f}s  ({r.get('answer_kind') if isinstance(r,dict) else '?'}) {q}")
        except Exception as e:
            print(f"  ERR {type(e).__name__}: {str(e)[:80]}  {q}")
    # cProfile a single representative query
    print("=== cProfile: '블랙홀이 뭐야' (cumulative top 25) ===")
    pr = cProfile.Profile()
    pr.enable()
    _ask("블랙홀이 뭐야")
    pr.disable()
    st = pstats.Stats(pr, stream=sys.stdout)
    st.sort_stats("cumulative").print_stats(25)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
