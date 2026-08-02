"use client";
// Custom Hub — Device & Ato zones. Heavy abilities (face recognition ~1GB, realistic 3D) stay
// OUT of the lean base and are added by capacity. Every card shows the REAL disk cost and the
// LIVE install status measured by the engine (a dependency import, not a guess). The base runs
// on a low-spec laptop; the user downloads only what they have the disk — and the reason — for.
import { useEffect, useState } from "react";
import { Cpu, Sparkles, HardDrive, Check, Download, Cloud } from "lucide-react";

type Plugin = {
  id: string; zone: string; group?: string | null; name: string; name_en: string;
  desc: string; desc_en: string;
  disk_mb: number; install_hint: string | null; provides: string[];
  status: "base" | "installed" | "available"; fits_disk: boolean; weights_ready?: boolean;
};

// Within `device`, perception is grouped by the sense it uses (owner 2026-07-11):
// self = ATANOR reading its own state; camera = the outside world via camera / smart glasses.
const GROUP_ORDER = ["self", "camera", "io"];
const GROUP_META: Record<string, { ko: string; en: string }> = {
  self: { ko: "셀프 인식 · 자기 상태", en: "Self · own state" },
  camera: { ko: "카메라 · 스마트글래스 인식", en: "Camera · smart glasses" },
  io: { ko: "동작 · 음성", en: "Motion · voice" },
};
type Status = { zones: string[]; disk_free_mb: number; plugins: Plugin[] };
type Lang = "ko" | "en";

const ZONE_META: Record<string, { ko: string; en: string; icon: typeof Cpu }> = {
  device: { ko: "디바이스 · 능력", en: "Device · Abilities", icon: Cpu },
  ato: { ko: "아토 · 캐릭터", en: "Ato · Character", icon: Sparkles },
};

function fmtDisk(mb: number): string {
  if (mb === 0) return "0";
  return mb >= 1000 ? `${(mb / 1000).toFixed(mb % 1000 ? 1 : 0)} GB` : `${mb} MB`;
}

export default function CustomHubDevicePanel({ language }: { language: Lang }) {
  const [s, setS] = useState<Status | null>(null);
  useEffect(() => {
    let alive = true;
    fetch("/api/graph-hub/plugins", { cache: "no-store" })
      .then((r) => r.json()).then((j) => { if (alive) setS(j as Status); })
      .catch(() => undefined);
    return () => { alive = false; };
  }, []);

  if (!s) return null;
  const zones = ["device", "ato"];

  const badge = (p: Plugin) => {
    if (p.status === "base")
      return { label: language === "ko" ? "기본 탑재" : "Base", color: "#9aa3b6", Icon: Check };
    if (p.status === "installed")
      return { label: language === "ko" ? "설치됨" : "Installed", color: "#4ade80", Icon: Check };
    return p.disk_mb === 0
      ? { label: language === "ko" ? "연결 필요" : "Connect", color: "#ff8a00", Icon: Cloud }
      : { label: language === "ko" ? "다운로드" : "Download", color: "#ff8a00", Icon: Download };
  };

  const Card = (p: Plugin) => {
    const b = badge(p);
    return (
      <article key={p.id} style={{
        background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.09)",
        borderRadius: 14, padding: "14px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
          <strong style={{ fontSize: 13.5, color: "#f2f4f8", lineHeight: 1.3 }}>
            {language === "ko" ? p.name : p.name_en}
          </strong>
          <em style={{ display: "inline-flex", alignItems: "center", gap: 4, flex: "none",
            fontStyle: "normal", fontSize: 10.5, color: b.color,
            background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.09)",
            borderRadius: 999, padding: "2px 8px" }}>
            <b.Icon size={11} /> {b.label}
          </em>
        </div>
        <p style={{ margin: 0, fontSize: 11.5, lineHeight: 1.55, color: "#9aa3b6" }}>
          {language === "ko" ? p.desc : p.desc_en}
        </p>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 2,
          fontSize: 11, color: "#6b7280" }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
            <HardDrive size={11} /> {p.disk_mb === 0 ? (language === "ko" ? "용량 0" : "no disk") : fmtDisk(p.disk_mb)}
          </span>
          {p.status === "available" && p.disk_mb > 0 && !p.fits_disk && (
            <span style={{ color: "#ff6b6b" }}>{language === "ko" ? "용량 부족" : "not enough space"}</span>
          )}
          {p.weights_ready === false && p.status === "installed" && (
            <span style={{ color: "#ff8a00" }}>{language === "ko" ? "가중치 대기" : "weights pending"}</span>
          )}
        </div>
        {p.status === "available" && p.install_hint && (
          <code style={{ fontSize: 10.5, color: "#9aa3b6", background: "rgba(0,0,0,0.3)",
            borderRadius: 6, padding: "5px 8px", overflowX: "auto", whiteSpace: "nowrap" }}>
            {p.install_hint}
          </code>
        )}
      </article>
    );
  };

  const Grid = ({ items }: { items: Plugin[] }) => (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 12 }}>
      {items.map((p) => Card(p))}
    </div>
  );

  return (
    <div style={{ margin: "0 0 22px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
        <HardDrive size={15} style={{ color: "#9aa3b6" }} />
        <span style={{ color: "#9aa3b6", fontSize: 12.5 }}>
          {language === "ko"
            ? `여유 용량 ${fmtDisk(s.disk_free_mb)} · 무거운 능력은 용량이 있을 때만 받으세요`
            : `${fmtDisk(s.disk_free_mb)} free · add heavy abilities only when you have the disk`}
        </span>
      </div>

      {zones.map((z) => {
        const meta = ZONE_META[z];
        const items = s.plugins.filter((p) => p.zone === z);
        if (!items.length) return null;
        const Icon = meta.icon;
        return (
          <section key={z} style={{ marginTop: 14 }}>
            <h3 style={{ display: "flex", alignItems: "center", gap: 7, margin: "0 0 10px",
              fontSize: 12, letterSpacing: "0.08em", textTransform: "uppercase", color: "#cdd6e8" }}>
              <Icon size={14} style={{ color: "#ff8a00" }} /> {language === "ko" ? meta.ko : meta.en}
            </h3>
            {z === "device" ? (
              GROUP_ORDER.map((g) => {
                const gi = items.filter((p) => (p.group || "io") === g);
                if (!gi.length) return null;
                const gm = GROUP_META[g];
                return (
                  <div key={g} style={{ marginBottom: 12 }}>
                    <div style={{ fontSize: 11, color: "#8a93a6", margin: "0 0 7px 2px", letterSpacing: "0.04em" }}>
                      {language === "ko" ? gm.ko : gm.en}
                    </div>
                    <Grid items={gi} />
                  </div>
                );
              })
            ) : (
              <Grid items={items} />
            )}
          </section>
        );
      })}
    </div>
  );
}
