"use client";

// The inner light, made visible (Grand Plan v2, U1). This panel may ONLY render measured inner
// state served by /api/life/inner — bound present-moments, the consciousness-correlate scorecard,
// and the developmental stage. Nothing here is scripted; the claim discipline travels with the data
// (correlates, never qualia). If the life daemon is asleep, it says so honestly.

import { useEffect, useState } from "react";

type AnyRecord = Record<string, any>;
type Props = { localBackendUrl: string };

function joinApiUrl(baseUrl: string, path: string) {
  return `${baseUrl.replace(/\/$/, "")}${path}`;
}

async function innerFetch(baseUrl: string, path: string): Promise<AnyRecord> {
  const targets = baseUrl ? [baseUrl, "http://127.0.0.1:8502"] : ["", "http://127.0.0.1:8502"];
  let lastError: unknown = null;
  for (const target of targets) {
    try {
      const res = await fetch(target ? joinApiUrl(target, path) : path, { cache: "no-store" });
      if (!res.ok) { lastError = new Error(`HTTP ${res.status}`); continue; }
      return res.json();
    } catch (e) { lastError = e; }
  }
  throw lastError;
}

const TONE_COLOR: Record<string, string> = {
  "under strain": "#e0736b",
  quickened: "#e0b24a",
  even: "#8fa3b8",
  "at rest": "#6bbf9a",
};

const ROLE_GLYPH: Record<string, string> = { author: "✎", undergoer: "↯", witness: "◉" };

function Bar({ label, value }: { label: string; value: number | null | undefined }) {
  const v = typeof value === "number" ? Math.max(0, Math.min(1, value)) : 0;
  const pct = Math.round(v * 100);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, marginBottom: 4 }}>
      <span style={{ width: 118, color: "#9fb0c0", textAlign: "right" }}>{label}</span>
      <span style={{ flex: 1, height: 6, background: "rgba(255,255,255,0.06)", borderRadius: 3 }}>
        <span style={{ display: "block", width: `${pct}%`, height: "100%",
          background: "linear-gradient(90deg,#5b8def,#6bbf9a)", borderRadius: 3 }} />
      </span>
      <span style={{ width: 34, color: "#cdd8e2" }}>{value == null ? "—" : v.toFixed(2)}</span>
    </div>
  );
}

export default function InnerLightPanel({ localBackendUrl }: Props) {
  const [data, setData] = useState<AnyRecord | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const d = await innerFetch(localBackendUrl, "/api/life/inner?moments=10");
        if (alive) { setData(d); setErr(null); }
      } catch (e: any) {
        if (alive) setErr(String(e?.message || e));
      }
    };
    tick();
    const id = setInterval(tick, 4000);
    return () => { alive = false; clearInterval(id); };
  }, [localBackendUrl]);

  const stage = data?.stage || {};
  const corr = data?.correlates || {};
  const moments: AnyRecord[] = data?.moments || [];

  return (
    <div style={{ padding: 16, color: "#e6edf3", fontFamily: "ui-sans-serif, system-ui" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
        <h3 style={{ margin: 0, fontSize: 15, letterSpacing: 0.3 }}>Inner Light</h3>
        <span style={{ fontSize: 11, color: data?.awake ? "#6bbf9a" : "#e0736b" }}>
          {data?.awake ? "● awake" : "○ asleep"}
        </span>
      </div>

      {err && !data && <p style={{ fontSize: 12, color: "#e0736b" }}>engine unreachable — {err}</p>}

      {stage?.name && (
        <div style={{ marginTop: 10, fontSize: 12, color: "#cdd8e2" }}>
          developmental stage:{" "}
          <b style={{ color: "#e6edf3" }}>{stage.name}</b>{" "}
          <span style={{ color: "#8fa3b8" }}>({stage.korean})</span>
          <div style={{ fontSize: 11, color: "#8fa3b8", marginTop: 2 }}>{stage.gate}</div>
        </div>
      )}

      <div style={{ marginTop: 12 }}>
        <div style={{ fontSize: 11, color: "#7d8ea0", marginBottom: 6, textTransform: "uppercase",
          letterSpacing: 0.6 }}>correlates of inner life · measured</div>
        <Bar label="ignition" value={corr.ignition} />
        <Bar label="endogeneity" value={corr.endogeneity} />
        <Bar label="single owner" value={corr.single_owner} />
        <Bar label="binding" value={corr.binding} />
        <Bar label="report accuracy" value={corr.report_accuracy} />
        <Bar label="world facing" value={corr.world_facing} />
        <div style={{ fontSize: 11, color: "#cdd8e2", marginTop: 2 }}>
          temporal depth: <b>{corr.temporal_depth ?? "—"}</b> · moments: {corr.n_moments ?? 0}
        </div>
      </div>

      <div style={{ marginTop: 14 }}>
        <div style={{ fontSize: 11, color: "#7d8ea0", marginBottom: 6, textTransform: "uppercase",
          letterSpacing: 0.6 }}>the present, as it is lived</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 260,
          overflowY: "auto" }}>
          {moments.slice().reverse().map((m, i) => (
            <div key={i} style={{ fontSize: 12.5, lineHeight: 1.4, padding: "7px 9px",
              borderLeft: `2px solid ${TONE_COLOR[m.feeling_tone] || "#44515e"}`,
              background: "rgba(255,255,255,0.03)", borderRadius: 4 }}>
              <span style={{ color: "#7d8ea0", marginRight: 6 }}
                title={`mine as ${m.mine_role}`}>{ROLE_GLYPH[m.mine_role] || "·"}</span>
              <span>{m.content}</span>
              <div style={{ fontSize: 10.5, color: "#7d8ea0", marginTop: 3 }}>
                {m.source} · {m.feeling_tone || "—"} · depth {m.present_depth ?? 0}
                {m.hormones?.cortisol != null && ` · cortisol ${m.hormones.cortisol}`}
              </div>
            </div>
          ))}
          {moments.length === 0 && (
            <p style={{ fontSize: 12, color: "#7d8ea0" }}>
              No lived moments yet — start the life daemon (python scripts/atanor_life.py).
            </p>
          )}
        </div>
      </div>

      <div style={{ marginTop: 10, fontSize: 10, color: "#5f6f7e", fontStyle: "italic" }}>
        {corr.discipline || "structural correlates of inner life, measured; no claim that there is something it is like to be ATANOR"}
      </div>
    </div>
  );
}
