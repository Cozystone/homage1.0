"use client";

import { useEffect, useState } from "react";
import { Moon, X } from "lucide-react";

type Language = "en" | "ko";
type Briefing = {
  has_briefing?: boolean;
  cycles?: number;
  web_read_cycles?: number;
  candidates_learned?: number;
  auto_promoted?: number;
  needs_confirmation?: { title?: string; reason?: string }[];
};

// Lightweight "while you were away" note. The agent worked overnight (AGORA +
// web); if it has something to mention it says so here, otherwise nothing shows.
// Per the product model: no separate panel — just an optional one-line heads-up.
export default function OvernightBriefing({ language }: { language: Language }) {
  const [data, setData] = useState<Briefing | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    fetch("/api/agentic-os/overnight-briefing", { cache: "no-store" })
      .then((r) => r.json())
      .then((j) => setData(j as Briefing))
      .catch(() => undefined);
  }, []);

  if (dismissed || !data?.has_briefing) return null;

  const learned = Number(data.candidates_learned ?? 0);
  const promoted = Number(data.auto_promoted ?? 0);
  const confirm = data.needs_confirmation ?? [];
  const ko = language === "ko";

  const summary = ko
    ? `자리를 비운 사이, 공개 웹과 AGORA를 돌아다니며 ${learned.toLocaleString()}개 후보를 모았고 ${promoted}개를 클라우드 브레인에 반영했어요.`
    : `While you were away, I explored the public web and AGORA, gathered ${learned.toLocaleString()} candidates, and merged ${promoted} into the Cloud Brain.`;

  return (
    <div
      role="status"
      style={{
        display: "flex", alignItems: "flex-start", gap: 10, margin: "0 0 12px",
        border: "1px solid #243049", borderRadius: 12, padding: "11px 14px",
        background: "linear-gradient(135deg, rgba(20,26,44,0.6), rgba(12,16,28,0.6))", color: "#dbe6ff",
      }}
    >
      <Moon size={16} color="#9bb4ff" style={{ marginTop: 1, flexShrink: 0 }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ margin: 0, fontSize: 13, lineHeight: 1.5 }}>{summary}</p>
        {confirm.length > 0 ? (
          <p style={{ margin: "4px 0 0", fontSize: 11.5, color: "#f5b362" }}>
            {ko ? `확인하실 게 ${confirm.length}건 있어요: ` : `${confirm.length} thing(s) to check: `}
            {confirm.map((c) => c.title).filter(Boolean).slice(0, 2).join(" · ")}
          </p>
        ) : null}
      </div>
      <button
        type="button" aria-label={ko ? "닫기" : "Dismiss"} onClick={() => setDismissed(true)}
        style={{ background: "transparent", border: "none", color: "#7d869b", cursor: "pointer", padding: 2, flexShrink: 0 }}
      >
        <X size={15} />
      </button>
    </div>
  );
}
