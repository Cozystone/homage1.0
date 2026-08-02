"use client";

import { useEffect, useState } from "react";

type AnyRecord = Record<string, any>;

async function apiJson(path: string, init?: RequestInit): Promise<AnyRecord> {
  const response = await fetch(path, { ...init, cache: "no-store" });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

export default function ConstructionPromotionPanel() {
  const [status, setStatus] = useState<AnyRecord | null>(null);
  const [manifest, setManifest] = useState<AnyRecord | null>(null);
  const [evalResult, setEvalResult] = useState<AnyRecord | null>(null);
  const [rollback, setRollback] = useState<AnyRecord | null>(null);
  const [message, setMessage] = useState("idle");

  async function refresh() {
    setStatus(await apiJson("/api/construction-bank/promotion/status"));
  }

  async function createDraftManifest() {
    const payload = await apiJson("/api/construction-bank/promotion/manifest/draft", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ created_by: "lab_operator" }),
    });
    setManifest(payload.manifest);
    setEvalResult(null);
    setRollback(null);
    setMessage(`manifest=${payload.manifest?.manifest_id ?? "draft"}`);
    await refresh();
  }

  async function runRegression() {
    if (!manifest?.manifest_id) return;
    const payload = await apiJson("/api/construction-bank/promotion/manifest/evaluate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ manifest_id: manifest.manifest_id }),
    });
    setEvalResult(payload);
    setMessage(payload.pass ? "regression pass" : `regression hold=${payload.regressions?.length ?? 0}`);
  }

  async function signPreview() {
    if (!manifest?.manifest_id) return;
    const payload = await apiJson("/api/construction-bank/promotion/manifest/sign-preview", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ manifest_id: manifest.manifest_id, operator_signature: "preview-signature-only" }),
    });
    setManifest(payload.manifest);
    setMessage(`sign preview=${payload.manifest?.status ?? "review_ready"}`);
  }

  async function createRollbackDraft() {
    const ids = manifest?.candidate_ids ?? [];
    const routes = manifest?.route_scopes ?? [];
    const payload = await apiJson("/api/construction-bank/promotion/rollback/draft", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ candidate_ids: ids, route_scopes: routes, reason: "lab rollback rehearsal" }),
    });
    setRollback(payload.rollback);
    setMessage(`rollback=${payload.rollback?.rollback_manifest_id ?? "draft"}`);
  }

  useEffect(() => {
    refresh().catch((error) => setMessage(error instanceof Error ? error.message : "refresh failed"));
  }, []);

  const entries = manifest?.entries ?? [];

  return (
    <article className="agentic-os-card agentic-os-review-card">
      <h3>Construction Promotion Manifest</h3>
      <p>Proof-only promotion gate. It creates review manifests, regression checks, and rollback drafts without product activation.</p>
      <div className="agentic-os-flags">
        <span>eligible_status={String(status?.eligible_status_count ?? 0)}</span>
        <span>activation=OFF</span>
        <span>signed_manifest_required=true</span>
        <span>rollback_required=true</span>
      </div>
      <div className="agentic-os-actions">
        <button type="button" className="agentic-os-action" onClick={() => createDraftManifest()}>create draft manifest</button>
        <button type="button" className="agentic-os-action" onClick={() => runRegression()} disabled={!manifest?.manifest_id}>run regression</button>
        <button type="button" className="agentic-os-action" onClick={() => signPreview()} disabled={!manifest?.manifest_id}>sign preview</button>
        <button type="button" className="agentic-os-action" onClick={() => createRollbackDraft()} disabled={!manifest?.manifest_id}>create rollback draft</button>
      </div>
      <p>{message}</p>
      {manifest ? (
        <div className="agentic-os-review-list">
          <strong>{manifest.manifest_id}</strong>
          <small>status={manifest.status} · candidates={manifest.candidate_ids?.length ?? 0} · product_activation={String(manifest.production_activation)}</small>
          <small>routes={(manifest.route_scopes ?? []).join(", ")}</small>
          {entries.slice(0, 5).map((entry: AnyRecord) => (
            <div className="agentic-os-review-item" key={entry.candidate_id}>
              <small>{entry.route_type} · {entry.review_status}</small>
              <strong>{entry.construction_family}</strong>
              <p>rejected={(entry.rejection_reasons ?? []).join(", ") || "none"}</p>
            </div>
          ))}
        </div>
      ) : null}
      {evalResult ? (
        <pre style={{ whiteSpace: "pre-wrap", maxHeight: 180, overflow: "auto" }}>
          {JSON.stringify({
            pass: evalResult.pass,
            regressions: evalResult.regressions?.length ?? 0,
            recommendation: evalResult.manifest_recommendation,
            production_activation: evalResult.production_activation,
          }, null, 2)}
        </pre>
      ) : null}
      {rollback ? (
        <pre style={{ whiteSpace: "pre-wrap", maxHeight: 140, overflow: "auto" }}>
          {JSON.stringify({
            rollback_manifest_id: rollback.rollback_manifest_id,
            executable: rollback.executable,
            candidate_ids_to_disable: rollback.candidate_ids_to_disable,
          }, null, 2)}
        </pre>
      ) : null}
    </article>
  );
}
