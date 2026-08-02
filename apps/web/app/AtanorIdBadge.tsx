"use client";

import { useEffect, useState } from "react";

/**
 * The install's unique AI-model id — minted once by the engine at first launch and shown here so
 * the user can point at *their* ATANOR (device identification / P2P registry / support). Click to
 * copy. Renders nothing if the engine is offline (no id to show yet). Not a secret, not hardware
 * fingerprinting — a did-like proof identifier (see packages/ego_network/device_identity.py).
 */
type Identity = { ai_id?: string; did?: string; model?: string; created_at?: string };

export default function AtanorIdBadge({ ko = true }: { ko?: boolean }) {
  const [ident, setIdent] = useState<Identity | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let alive = true;
    fetch("/api/identity", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (alive && d?.ai_id) setIdent(d); })
      .catch(() => {});
    return () => { alive = false; };
  }, []);

  if (!ident?.ai_id) return null;

  const copy = () => {
    navigator.clipboard?.writeText(ident.ai_id as string).then(
      () => { setCopied(true); window.setTimeout(() => setCopied(false), 1200); },
      () => {},
    );
  };

  const born = ident.created_at ? ident.created_at.slice(0, 10) : "";

  return (
    <button
      type="button"
      className="atanor-id-badge"
      onClick={copy}
      title={`${ko ? "이 기기의 ATANOR 고유 식별번호 — 클릭하면 복사" : "This device's unique ATANOR id — click to copy"}${born ? `\n${ko ? "발급" : "issued"} ${born}` : ""}\n${ident.did ?? ""}`}
    >
      <span className="atanor-id-badge-dot" aria-hidden="true" />
      <span className="atanor-id-badge-body">
        <span className="atanor-id-badge-label">{copied ? (ko ? "복사됨" : "copied") : (ko ? "AI 식별번호" : "AI ID")}</span>
        <span className="atanor-id-badge-code">{ident.ai_id}</span>
      </span>
    </button>
  );
}
