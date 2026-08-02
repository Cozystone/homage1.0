"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BookOpen,
  Check,
  Clipboard,
  ClipboardPaste,
  FileText,
  Globe,
  type LucideIcon,
  MessageSquare,
  Monitor,
  Puzzle,
  RefreshCw,
  Rss,
  Search,
  Settings,
  X,
} from "lucide-react";

/**
 * Plugin store — a FULL-PAGE surface (fills the chat content area) modeled on the
 * Codex Desktop plugin store: a tab bar (플러그인 / 도구), search, an Installed icon
 * row, marketplace filter chips, and category card grids. Real ATANOR plugins from
 * /api/plugins only (no fabricated third-party apps); monochrome lucide icons.
 *
 * Honest: tabs/filters use the plugins' real `kind` and `marketplace`; "사용" inserts
 * the slash command, "켜기" enables the source. Running still passes the server-side
 * capability gate (PC control stays read-only + phrase-gated).
 */

type Plugin = {
  id: string; name: string; marketplace: string; kind: string;
  icon: string; description: string; max_risk: string; enabled: boolean; ready: boolean;
  composer: { slash: string; label: string; placeholder: string; field: string | null };
};
type ListResp = { plugins: Plugin[]; marketplaces: string[]; offline?: boolean };

export const PLUGIN_ICONS: Record<string, LucideIcon> = {
  "clipboard-paste": ClipboardPaste, "message-square": MessageSquare, globe: Globe, rss: Rss,
  "book-open": BookOpen, "file-text": FileText, clipboard: Clipboard, monitor: Monitor,
};

const MKT_LABEL: Record<string, { ko: string; en: string }> = {
  "atanor-core": { ko: "기본", en: "Core" },
  "atanor-web": { ko: "웹", en: "Web" },
  "atanor-local": { ko: "로컬", en: "Local" },
  "atanor-labs": { ko: "실험", en: "Labs" },
};

export default function PluginGallery({ open, onClose, language = "ko", onUse }: {
  open: boolean; onClose: () => void; language?: "ko" | "en"; onUse?: (p: Plugin) => void;
}) {
  const ko = language === "ko";
  const [data, setData] = useState<ListResp | null>(null);
  const [tab, setTab] = useState<"source" | "tool">("source");
  const [q, setQ] = useState("");
  const [mkt, setMkt] = useState<string>("all");

  const refresh = useCallback(async () => {
    try {
      const r = await fetch("/api/plugins", { cache: "no-store" });
      setData(await r.json());
    } catch { /* keep last */ }
  }, []);

  useEffect(() => { if (open) refresh(); }, [open, refresh]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  async function toggle(p: Plugin) {
    await fetch(`/api/plugins/${encodeURIComponent(p.id)}/enable`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled: !p.enabled }),
    }).catch(() => {});
    refresh();
  }

  const plugins = useMemo(() => data?.plugins ?? [], [data]);
  const tabbed = useMemo(() => plugins.filter((p) => (tab === "tool" ? p.kind === "tool" : p.kind !== "tool")), [plugins, tab]);
  const markets = useMemo(() => Array.from(new Set(tabbed.map((p) => p.marketplace))), [tabbed]);
  const enabled = useMemo(() => plugins.filter((p) => p.enabled), [plugins]);

  if (!open) return null;
  const ql = q.trim().toLowerCase();
  const shown = tabbed.filter((p) =>
    (mkt === "all" || p.marketplace === mkt) &&
    (!ql || p.name.toLowerCase().includes(ql) || (p.description || "").toLowerCase().includes(ql)),
  );
  // group by marketplace into "category" sections (Codex's Featured/Productivity feel)
  const sections = (mkt === "all" ? markets : [mkt]).map((m) => ({
    market: m, items: shown.filter((p) => p.marketplace === m),
  })).filter((s) => s.items.length);

  return (
    <div className="atanor-pg-scrim">
      <div className="atanor-pg-topbar">
        <div className="atanor-pg-tabs">
          <button data-active={tab === "source"} onClick={() => { setTab("source"); setMkt("all"); }}>{ko ? "플러그인" : "Plugins"}</button>
          <button data-active={tab === "tool"} onClick={() => { setTab("tool"); setMkt("all"); }}>{ko ? "도구" : "Tools"}</button>
        </div>
        <div className="atanor-pg-topright">
          <button onClick={refresh} aria-label="refresh"><RefreshCw size={16} strokeWidth={1.7} /></button>
          <button onClick={onClose} aria-label="close"><X size={17} strokeWidth={1.8} /></button>
        </div>
      </div>

      <div className="atanor-pg">
        <div className="atanor-pg-head">
          <h2>{tab === "tool" ? (ko ? "도구" : "Tools") : (ko ? "플러그인" : "Plugins")}</h2>
          <p>{tab === "tool"
            ? (ko ? "ATANOR의 기능을 확장하는 도구" : "Tools that extend what ATANOR can do")
            : (ko ? "즐겨 쓰는 소스 어디서나 ATANOR와 함께 작업하세요" : "Work with ATANOR alongside your favorite sources")}</p>
        </div>

        <div className="atanor-pg-search">
          <Search size={16} strokeWidth={1.7} aria-hidden="true" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={ko ? (tab === "tool" ? "도구 검색" : "플러그인 검색") : "Search"} aria-label="search" />
        </div>

        {data?.offline ? <div className="atanor-pg-offline">{ko ? "엔진 오프라인 — 카탈로그만 표시" : "engine offline — catalog only"}</div> : null}

        {enabled.length ? (
          <section>
            <div className="atanor-pg-section-head"><span>{ko ? "설치됨" : "Installed"}</span><Settings size={15} strokeWidth={1.6} aria-hidden="true" /></div>
            <div className="atanor-pg-chiprow">
              {enabled.map((p) => { const I = PLUGIN_ICONS[p.icon] ?? Puzzle; return (
                <span key={p.id} className="atanor-pg-chip" title={p.name}><I size={19} strokeWidth={1.6} /></span>
              ); })}
            </div>
          </section>
        ) : null}

        {markets.length > 1 ? (
          <div className="atanor-pg-filters">
            <button data-active={mkt === "all"} onClick={() => setMkt("all")}>{ko ? "전체" : "All"}</button>
            {markets.map((m) => (
              <button key={m} data-active={mkt === m} onClick={() => setMkt(m)}>{MKT_LABEL[m]?.[ko ? "ko" : "en"] ?? m}</button>
            ))}
          </div>
        ) : null}

        {sections.map((s) => (
          <section key={s.market}>
            <div className="atanor-pg-section-head atanor-pg-cat"><span>{MKT_LABEL[s.market]?.[ko ? "ko" : "en"] ?? s.market}</span></div>
            <div className="atanor-pg-grid">
              {s.items.map((p) => { const I = PLUGIN_ICONS[p.icon] ?? Puzzle; return (
                <article key={p.id} className="atanor-pg-card">
                  <span className="atanor-pg-card-ico" aria-hidden="true"><I size={20} strokeWidth={1.6} /></span>
                  <div className="atanor-pg-card-body">
                    <div className="atanor-pg-card-top">
                      <strong>{p.name}</strong>
                      <code>{p.composer.slash}</code>
                      {p.enabled ? <Check size={14} strokeWidth={2.2} className="atanor-pg-on" aria-label="enabled" /> : null}
                    </div>
                    <p>{p.description}</p>
                  </div>
                  {p.enabled
                    ? <button className="atanor-pg-use" onClick={() => { onUse?.(p); onClose(); }}>{ko ? "채팅에서 사용" : "Try in chat"}</button>
                    : <button className="atanor-pg-install" onClick={() => toggle(p)}>{ko ? "켜기" : "Enable"}</button>}
                </article>
              ); })}
            </div>
          </section>
        ))}
        {sections.length === 0 ? <div className="atanor-pg-empty">{ko ? "결과가 없습니다" : "No matches"}</div> : null}

        <p className="atanor-pg-foot">
          {ko ? "공개 소스만 · 수집(발화) ≠ 이해(개념) · PC 제어는 읽기전용·문구승인"
              : "Public sources only · collected ≠ understood · PC control read-only & phrase-gated"}
        </p>
      </div>
    </div>
  );
}
