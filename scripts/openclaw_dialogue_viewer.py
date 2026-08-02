# -*- coding: utf-8 -*-
"""Live viewer for the ATANOR <-> openclaw dialogue — watch the real conversation in real time.

A tiny stdlib http.server (no framework, no CDN, self-contained):
  GET /              -> an HTML page that polls /turns every ~1s and appends new turns as chat
                        bubbles (ATANOR left, openclaw right; distinct colours; timestamp; topic
                        header; smooth auto-scroll; a small "live" pulse). Theme-aware (light/dark).
  GET /turns?since=K -> the rows of data/advisor_loop/openclaw_dialogue_live.jsonl with i>K, as JSON.

  python -X utf8 scripts/openclaw_dialogue_viewer.py            # http://localhost:8677
  python -X utf8 scripts/openclaw_dialogue_viewer.py --port 8677 --file <path.jsonl>
"""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

REPO = Path(__file__).resolve().parents[1]
LIVE = REPO / "data" / "advisor_loop" / "openclaw_dialogue_live.jsonl"

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>ATANOR &harr; openclaw &mdash; live</title>
<style>
  :root{
    --bg:#f6f7f9; --panel:#ffffff; --ink:#12151a; --muted:#6b7480; --line:#e6e8ec;
    --atanor:#0b5cff; --atanor-bg:#eef3ff; --atanor-ink:#0a2a66;
    --openclaw:#0f9d78; --openclaw-bg:#e9f7f1; --openclaw-ink:#0a4d3a;
    --shadow:0 1px 2px rgba(16,22,32,.06),0 6px 22px rgba(16,22,32,.06);
  }
  @media (prefers-color-scheme:dark){
    :root{
      --bg:#0c0e12; --panel:#12151b; --ink:#e8ebf0; --muted:#8b94a3; --line:#222833;
      --atanor:#5b8cff; --atanor-bg:#16223f; --atanor-ink:#cfe0ff;
      --openclaw:#3fd7a8; --openclaw-bg:#102a24; --openclaw-ink:#bff2df;
      --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 30px rgba(0,0,0,.35);
    }
  }
  *{box-sizing:border-box}
  html,body{height:100%}
  body{
    margin:0; background:var(--bg); color:var(--ink);
    font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    display:flex; flex-direction:column; align-items:center;
  }
  header{
    position:sticky; top:0; z-index:5; width:100%;
    background:color-mix(in srgb,var(--panel) 88%,transparent);
    backdrop-filter:saturate(1.4) blur(10px);
    border-bottom:1px solid var(--line);
  }
  .head-in{max-width:860px; margin:0 auto; padding:14px 20px; display:flex; align-items:center; gap:14px}
  .title{font-weight:650; letter-spacing:.2px; white-space:nowrap}
  .title .a{color:var(--atanor)} .title .o{color:var(--openclaw)}
  .topic{color:var(--muted); font-size:13px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1}
  .topic b{color:var(--ink); font-weight:600}
  .live{display:flex; align-items:center; gap:7px; color:var(--muted); font-size:12px; white-space:nowrap}
  .dot{width:9px; height:9px; border-radius:50%; background:var(--openclaw); box-shadow:0 0 0 0 var(--openclaw);
       animation:pulse 1.8s infinite}
  .dot.stale{background:var(--muted); animation:none}
  @keyframes pulse{0%{box-shadow:0 0 0 0 color-mix(in srgb,var(--openclaw) 70%,transparent)}
                   70%{box-shadow:0 0 0 8px transparent} 100%{box-shadow:0 0 0 0 transparent}}
  main{width:100%; max-width:860px; flex:1; padding:22px 20px 40px; display:flex; flex-direction:column; gap:14px}
  .row{display:flex; width:100%}
  .row.ATANOR{justify-content:flex-start}
  .row.openclaw{justify-content:flex-end}
  .bubble{max-width:74%; padding:11px 14px; border-radius:16px; box-shadow:var(--shadow);
          border:1px solid var(--line); animation:rise .28s ease both}
  @keyframes rise{from{opacity:0; transform:translateY(8px)} to{opacity:1; transform:none}}
  .row.ATANOR .bubble{background:var(--atanor-bg); border-top-left-radius:5px}
  .row.openclaw .bubble{background:var(--openclaw-bg); border-top-right-radius:5px}
  .who{font-size:11.5px; font-weight:700; letter-spacing:.4px; text-transform:uppercase; margin-bottom:3px}
  .row.ATANOR .who{color:var(--atanor-ink)}
  .row.openclaw .who{color:var(--openclaw-ink)}
  .text{white-space:pre-wrap; word-wrap:break-word}
  .meta{margin-top:6px; font-size:11px; color:var(--muted); display:flex; gap:8px; flex-wrap:wrap; align-items:center}
  .tag{border:1px solid var(--line); border-radius:999px; padding:1px 7px; font-size:10.5px}
  .src a{color:var(--muted); text-decoration:none; border-bottom:1px dotted var(--muted)}
  .src a:hover{color:var(--ink)}
  .empty{color:var(--muted); text-align:center; margin-top:12vh; font-size:14px}
  footer{color:var(--muted); font-size:11.5px; padding:0 0 22px}
</style>
</head>
<body>
<header>
  <div class="head-in">
    <div class="title"><span class="a">ATANOR</span> &harr; <span class="o">openclaw</span></div>
    <div class="topic" id="topic"></div>
    <div class="live"><span class="dot" id="dot"></span><span id="livetxt">connecting&hellip;</span></div>
  </div>
</header>
<main id="feed"><div class="empty" id="empty">Waiting for the conversation to begin&hellip;</div></main>
<footer id="foot"></footer>
<script>
(function(){
  var last = 0, feed = document.getElementById('feed'), empty = document.getElementById('empty');
  var topicEl = document.getElementById('topic'), dot = document.getElementById('dot');
  var liveTxt = document.getElementById('livetxt'), foot = document.getElementById('foot');
  var topicSet = false, misses = 0, count = 0;

  function nearBottom(){ return (window.innerHeight + window.scrollY) >= (document.body.scrollHeight - 140); }
  function stamp(ts){ try{ return new Date(ts*1000).toLocaleTimeString(); }catch(e){ return ''; } }
  function esc(s){ var d=document.createElement('div'); d.textContent=(s==null?'':String(s)); return d.innerHTML; }

  function add(t){
    if(empty){ empty.remove(); empty=null; }
    if(!topicSet && t.topic){ topicEl.innerHTML = 'topic: <b>'+esc(t.topic)+'</b>'; topicSet=true; }
    var row=document.createElement('div'); row.className='row '+(t.speaker==='ATANOR'?'ATANOR':'openclaw');
    var b=document.createElement('div'); b.className='bubble';
    var who = t.speaker==='ATANOR' ? 'ATANOR &middot; engine' : 'openclaw &middot; gpt-5.4';
    var meta = '<span>#'+t.i+'</span><span>'+stamp(t.ts)+'</span>';
    if(t.act){ meta += '<span class="tag">'+esc(t.act)+'</span>'; }
    if(t.source){
      var u = String(t.source), safe = /^https?:\/\//.test(u) ? u : '';
      meta += '<span class="src">web: '+(safe?('<a href="'+esc(safe)+'" target="_blank" rel="noopener">'+esc(u)+'</a>'):esc(u))+'</span>';
    }
    b.innerHTML = '<div class="who">'+who+'</div><div class="text">'+esc(t.text)+'</div><div class="meta">'+meta+'</div>';
    row.appendChild(b); feed.appendChild(row);
  }

  function poll(){
    fetch('/turns?since='+last, {cache:'no-store'}).then(function(r){ return r.json(); }).then(function(rows){
      dot.classList.remove('stale');
      if(rows.length){
        var stick = nearBottom();
        rows.forEach(function(t){ if(t.i>last){ add(t); last=t.i; count++; } });
        misses = 0;
        if(stick){ window.scrollTo({top:document.body.scrollHeight, behavior:'smooth'}); }
      } else { misses++; }
      liveTxt.textContent = count+' turns · live';
      if(misses>10){ dot.classList.add('stale'); liveTxt.textContent = count+' turns · idle'; }
      foot.textContent = 'polling /turns every 1s — last id '+last;
    }).catch(function(){
      dot.classList.add('stale'); liveTxt.textContent='reconnecting…';
    });
  }
  poll(); setInterval(poll, 1000);
})();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    live_path: Path = LIVE

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            return
        if parsed.path == "/turns":
            try:
                since = int(parse_qs(parsed.query).get("since", ["0"])[0])
            except Exception:
                since = 0
            rows = self._read_rows(since)
            self._send(200, json.dumps(rows, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")
            return
        self._send(404, b"not found", "text/plain; charset=utf-8")

    def _read_rows(self, since: int) -> list:
        out = []
        if not self.live_path.exists():
            return out
        try:
            with self.live_path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)          # a partial trailing line (mid-write) is skipped
                    except Exception:
                        continue
                    if isinstance(r, dict) and int(r.get("i", 0)) > since:
                        out.append(r)
        except Exception:
            return out
        return out

    def log_message(self, *a) -> None:      # keep the console quiet (the dialogue owns stdout)
        return


def main() -> int:
    ap = argparse.ArgumentParser(description="Live web viewer for the ATANOR <-> openclaw dialogue")
    ap.add_argument("--port", type=int, default=8677)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--file", default=str(LIVE), help="the live JSONL to serve")
    args = ap.parse_args()

    Handler.live_path = Path(args.file)
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://localhost:{args.port}"
    print(f"ATANOR <-> openclaw live viewer -> {url}", flush=True)
    print(f"  serving: {Handler.live_path}", flush=True)
    print("  Ctrl+C to stop", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped", flush=True)
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
