"use client";

import { useEffect, useState } from "react";

type AnyRecord = Record<string, any>;

const eventButtons = [
  "user_greeting",
  "novelty_found",
  "repeated_failure",
  "host_action_denied",
  "voice_unavailable",
  "tier4_enabled",
  "resting",
] as const;

function flagLine(flags: AnyRecord | undefined) {
  if (!flags) return "loading";
  return [
    `external_llm=${String(flags.external_llm)}`,
    `real_emotion_claim=${String(flags.real_emotion_claim)}`,
    `local_brain_write=${String(flags.local_brain_write)}`,
    `production_store_mutated=${String(flags.production_store_mutated)}`,
  ].join(" / ");
}

function Gauge({ label, value, min = 0, max = 1 }: { label: string; value: number; min?: number; max?: number }) {
  const normalized = Math.max(0, Math.min(1, (Number(value) - min) / (max - min)));
  return (
    <span className="agentic-os-neural-gauge">
      <small>{label}</small>
      <i><b style={{ width: `${Math.round(normalized * 100)}%` }} /></i>
      <strong>{Number(value).toFixed(3)}</strong>
    </span>
  );
}

export default function NeuralEmotionPanel() {
  const [snapshot, setSnapshot] = useState<AnyRecord | null>(null);
  const [policy, setPolicy] = useState<AnyRecord | null>(null);
  const [lastEvent, setLastEvent] = useState<string>("none");
  const [lastDelta, setLastDelta] = useState<AnyRecord | null>(null);
  const [events, setEvents] = useState<AnyRecord[]>([]);

  async function refresh() {
    const payload = await fetch("/api/neural-emotion/snapshot", { cache: "no-store" })
      .then((response) => response.json())
      .catch((error) => ({ available: false, reason: String(error) }));
    setSnapshot(payload);
    const eventPayload = await fetch("/api/neural-emotion/events", { cache: "no-store" })
      .then((response) => response.json())
      .catch(() => ({ events: [] }));
    setEvents(Array.isArray(eventPayload.events) ? eventPayload.events.slice(-8).reverse() : []);
    const policyPayload = await fetch("/api/neural-emotion/policy/current?workspace=lab", { cache: "no-store" })
      .then((response) => response.json())
      .catch(() => ({ policy: null }));
    setPolicy(policyPayload.policy ?? null);
  }

  async function sendEvent(eventType: string) {
    const payload = await fetch("/api/neural-emotion/events/emit", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        source: "user_action",
        event_type: eventType,
        intensity: 1.0,
        payload_summary: `lab button ${eventType}`,
      }),
    })
      .then((response) => response.json())
      .catch((error) => ({ available: false, reason: String(error) }));
    setSnapshot(payload);
    setLastEvent(eventType);
    const before = payload?.result?.snapshot_before?.vector ?? {};
    const after = payload?.result?.snapshot_after?.vector ?? {};
    setLastDelta({
      valence: Number(after.valence ?? 0) - Number(before.valence ?? 0),
      arousal: Number(after.arousal ?? 0) - Number(before.arousal ?? 0),
      curiosity: Number(after.curiosity ?? 0) - Number(before.curiosity ?? 0),
      caution: Number(after.caution ?? 0) - Number(before.caution ?? 0),
      fatigue: Number(after.fatigue ?? 0) - Number(before.fatigue ?? 0),
    });
    setEvents(Array.isArray(payload.events) ? payload.events.slice(-8).reverse() : []);
    await refresh().catch(() => undefined);
  }

  async function decay() {
    const payload = await fetch("/api/neural-emotion/decay", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ half_life_seconds: 480 }),
    })
      .then((response) => response.json())
      .catch((error) => ({ available: false, reason: String(error) }));
    setSnapshot(payload);
    setLastEvent("decay");
    setLastDelta(null);
    await refresh().catch(() => undefined);
  }

  useEffect(() => {
    refresh().catch(() => undefined);
  }, []);

  const data = snapshot?.snapshot ?? snapshot;
  const vector = data?.vector ?? {};
  return (
    <article className="agentic-os-card agentic-os-neural-emotion-card">
      <div className="agentic-os-permission-header">
        <div>
          <h3>Neural Emotion Engine v0</h3>
          <p>Bounded local state controls for discourse, SPLATRA motion, voice plans, and agentic priority. It is not real emotion or consciousness.</p>
        </div>
        <strong>{data?.label ?? "loading"}</strong>
      </div>
      <div className="agentic-os-neural-grid">
        <Gauge label="valence" value={Number(vector.valence ?? 0)} min={-1} max={1} />
        <Gauge label="arousal" value={Number(vector.arousal ?? 0)} min={-1} max={1} />
        <Gauge label="curiosity" value={Number(vector.curiosity ?? 0)} />
        <Gauge label="caution" value={Number(vector.caution ?? 0)} />
        <Gauge label="fatigue" value={Number(vector.fatigue ?? 0)} />
        <Gauge label="speaking" value={Number(vector.speaking_energy ?? 0)} />
      </div>
      <div className="agentic-os-actions">
        {eventButtons.map((eventType) => (
          <button key={eventType} type="button" className="agentic-os-action" onClick={() => sendEvent(eventType)}>
            {eventType}
          </button>
        ))}
        <button type="button" className="agentic-os-action" onClick={() => decay()}>
          decay
        </button>
        <button type="button" className="agentic-os-action" onClick={() => refresh()}>
          refresh
        </button>
      </div>
      <div className="agentic-os-flags">
        <span>last={lastEvent}</span>
        <span>delta={lastDelta ? JSON.stringify(lastDelta) : "none"}</span>
        <span>{flagLine(snapshot?.safety_flags ?? data?.safety_flags)}</span>
      </div>
      <div className="agentic-os-control-readout">
        <pre>{JSON.stringify({
          surface: data?.surface_bias,
          splatra: data?.splatra_controls,
          voice: data?.voice_controls,
          agentic: data?.agentic_controls,
        }, null, 2)}</pre>
      </div>
      <div className="agentic-os-control-readout">
        <h4>Autonomy Policy v1</h4>
        <p>Suggested only. It cannot change autonomy tier, bypass Permission Gate, write Local Brain, mutate production, promote candidates, or claim real emotion.</p>
        <div className="agentic-os-flags">
          <span>web x{String(policy?.exploration?.web_budget_multiplier ?? "-")}</span>
          <span>pages {String(policy?.exploration?.max_pages_delta ?? "-")}</span>
          <span>review {String(policy?.review?.label ?? "-")}</span>
          <span>skill threshold {String(policy?.review?.skill_draft_threshold ?? "-")}</span>
          <span>throttle {String(policy?.agent_loop?.throttle_multiplier ?? "-")}</span>
          <span>rest={String(policy?.agent_loop?.should_rest ?? false)}</span>
        </div>
        <pre>{JSON.stringify({
          splatra: policy?.splatra,
          asm: {
            brevity: policy?.surface?.asm_brevity_bias,
            caution: policy?.surface?.asm_caution_bias,
          },
          voice: {
            fallback_emphasis: policy?.surface?.voice_fallback_emphasis,
            claims_audio_available: policy?.surface?.voice_claims_audio_available,
          },
          safe: {
            tier_auto_changed: policy?.autonomy_tier_auto_changed,
            permission_gate_bypass: policy?.permission_gate_bypass,
          },
        }, null, 2)}</pre>
      </div>
      <div className="agentic-os-event-log">
        <h4>Event log</h4>
        {events.length === 0 ? <p>no events yet</p> : events.map((event) => (
          <span key={event.event_id}>
            <small>{event.source} / {event.event_type}</small>
            <strong>{event.payload_summary || event.content_hash}</strong>
          </span>
        ))}
      </div>
    </article>
  );
}
