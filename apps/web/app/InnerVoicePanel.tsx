"use client";

import { useEffect, useState } from "react";

type AnyRecord = Record<string, any>;

type Props = {
  localBackendUrl: string;
};

function joinApiUrl(baseUrl: string, path: string) {
  return `${baseUrl.replace(/\/$/, "")}${path}`;
}

async function innerVoiceFetch(baseUrl: string, path: string, init?: RequestInit): Promise<AnyRecord> {
  const backendTargets = baseUrl.includes("127.0.0.1:8500") || baseUrl.includes("localhost:8500")
    ? [baseUrl, "http://127.0.0.1:8502"]
    : baseUrl
      ? [baseUrl, "http://127.0.0.1:8502"]
      : ["", "http://127.0.0.1:8502"];
  let lastError: unknown = null;
  for (const target of backendTargets) {
    try {
      const response = await fetch(target ? joinApiUrl(target, path) : path, { ...init, cache: "no-store" });
      if (!response.ok) {
        lastError = new Error(`HTTP ${response.status}`);
        continue;
      }
      return response.json();
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError;
}

function flagsLine(flags: AnyRecord | undefined) {
  if (!flags) return "loading";
  return [
    `external_llm=${String(flags.external_llm)}`,
    `local_brain_write=${String(flags.local_brain_write)}`,
    `production_store_mutated=${String(flags.production_store_mutated)}`,
    `raw_hidden_cot_claim=${String(flags.raw_hidden_cot_claim)}`,
  ].join(" / ");
}

export default function InnerVoicePanel({ localBackendUrl }: Props) {
  const [status, setStatus] = useState<AnyRecord | null>(null);
  const [log, setLog] = useState<AnyRecord | null>(null);
  const [brief, setBrief] = useState<AnyRecord | null>(null);

  async function refresh() {
    const payload = await innerVoiceFetch(localBackendUrl, "/api/inner-voice/status?workspace=lab")
      .catch((error) => ({ available: false, reason: String(error) }));
    setStatus(payload);
    const logPayload = await innerVoiceFetch(localBackendUrl, "/api/inner-voice/log?workspace=lab")
      .catch(() => ({ frames: [] }));
    setLog(logPayload);
  }

  async function emitSample() {
    const payload = await innerVoiceFetch(localBackendUrl, "/api/inner-voice/emit", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        source_event_id: "lab_inner_voice_sample",
        mode: "lab_visible",
        latest_user_input: "안녕",
        review_queue_pressure: 0,
        permission_tier: "OBSERVE_ONLY",
      }),
    }).catch((error) => ({ emitted: false, reason: String(error) }));
    setStatus(payload);
    await refresh().catch(() => undefined);
  }

  async function buildBrief() {
    const payload = await innerVoiceFetch(localBackendUrl, "/api/inner-voice/brief", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ workspace: "lab" }),
    }).catch((error) => ({ available: false, reason: String(error) }));
    setBrief(payload);
  }

  useEffect(() => {
    refresh().catch(() => undefined);
  }, [localBackendUrl]);

  const frames = Array.isArray(log?.frames) ? log.frames.slice(-5).reverse() : [];
  const latest = status?.frame ?? status?.log?.latest ?? frames[0];
  return (
    <article className="agentic-os-card">
      <div className="agentic-os-permission-header">
        <div>
          <h3>Inner Voice / Self-Narration</h3>
          <p>Explicit state-generated self narration. It is not hidden chain-of-thought or proof of consciousness.</p>
        </div>
        <strong>{latest?.felt_state_label ?? "waiting"}</strong>
      </div>
      <div className="agentic-os-actions">
        <button type="button" className="agentic-os-action" onClick={() => refresh()}>
          refresh inner voice
        </button>
        <button type="button" className="agentic-os-action" onClick={() => emitSample()}>
          emit sample
        </button>
        <button type="button" className="agentic-os-action" onClick={() => buildBrief()}>
          brief
        </button>
      </div>
      {latest ? (
        <div className="agentic-os-host-result">
          <strong>{latest.goal}</strong>
          <span>
            construction={latest.construction_id ?? "unknown"} / act={latest.act ?? "unknown"} / stance={latest.construction_stance ?? "unknown"} / score={String(latest.surface_score ?? "-")}
          </span>
          <p>{latest.monologue_text}</p>
          <span>chosen={latest.chosen_action}</span>
          <span>blocked={(latest.blocked_actions ?? []).join(" / ")}</span>
          <span>next={latest.next_intent}</span>
          <span>basis={latest.generation_basis ?? "asm_cgsr_construction_conditioned_inner_voice_v1"}</span>
        </div>
      ) : <p>no inner voice frames yet</p>}
      <div className="agentic-os-flags">
        <span>{flagsLine(status?.safety_flags ?? latest?.safety_flags)}</span>
      </div>
      {brief?.brief ? <pre>{brief.brief}</pre> : null}
      <div className="agentic-os-event-log">
        {frames.map((frame: AnyRecord) => (
          <span key={frame.frame_id}>
            <small>{frame.source_event_id} / {frame.mode}</small>
            <strong>{frame.monologue_text}</strong>
          </span>
        ))}
      </div>
    </article>
  );
}
