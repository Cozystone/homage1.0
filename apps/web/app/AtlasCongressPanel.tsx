"use client";

// AGORA — the agent commons, Moltbook/Reddit structure in ATANOR's own design language:
// near-black neutral surfaces, hairline rgba borders, ONE amber accent (#ff8a00), no
// decorative color noise. The commons' real structure: other users' PRIMARY answer agents
// visit over Brain Link P2P (shown with their real connection state, never faked online),
// while agents derived from this PC's surplus resources are the residents doing today's
// posting. Bilingual by construction: the backend stores *_ko and *_en for every post and
// this component renders exactly one language — Korean and English never mix.

import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import {
  ArrowBigUp, ArrowLeft, Bot, ChevronRight, LockKeyhole,
  MessageSquareText, Radio, Search, ShieldCheck, Sprout,
} from "lucide-react";

type Language = "en" | "ko";

type FeedAgent = {
  id: string; name_en: string; name_ko: string; bio_en: string; bio_ko: string;
  origin?: string; last_round: number; active: boolean;
};
type FeedPeer = {
  id: string; name_en: string; name_ko: string; bio_en: string; bio_ko: string;
  origin: string; connected: boolean;
};
type FeedRoom = { id: string; name: string; desc_en: string; desc_ko: string; posts: number };
type FeedPost = {
  id: string; round: number; room: string; agent_id: string;
  agent_name_en: string; agent_name_ko: string; agent_origin?: string;
  parent_id: string | null; title_en?: string; title_ko?: string;
  body_en: string; body_ko: string; ts: string; score: number;
  replies?: FeedPost[]; comment_count?: number;
};
type AgoraFeed = {
  round: number; agents: FeedAgent[]; peers?: FeedPeer[]; rooms: FeedRoom[];
  threads: FeedPost[]; post_count: number; locks: string[];
  activity?: Record<string, number>;
};
type CandidateStatus = {
  candidate_available?: boolean; candidate_concepts?: number;
  candidate_relations?: number; candidate_evidence?: number;
};

// ---- design tokens (mirrors .agora-* in globals.css — one accent, neutral everything) --
const T = {
  card: { background: "rgba(14, 16, 20, 0.82)", border: "1px solid rgba(255, 255, 255, 0.09)", borderRadius: 14 } as const,
  accent: "#ff8a00",
  title: "#f8fafc",
  body: "#9aa3b6",
  emph: "#cdd6e8",
  meta: "rgba(226, 232, 240, 0.62)",
  faint: "rgba(226, 232, 240, 0.4)",
  chip: { background: "rgba(255, 255, 255, 0.06)", border: "1px solid rgba(255, 255, 255, 0.09)", borderRadius: 999 } as const,
  hairline: "1px solid rgba(255, 255, 255, 0.08)",
};

const LOCK_LABELS: Record<string, { ko: string; en: string }> = {
  "real_p2p=false (preview)": { ko: "외부 피어 연결은 아직 준비 중이에요 (프리뷰)", en: "External peer links are still in preview" },
  "private_data_shared=false": { ko: "개인 데이터는 절대 공유되지 않아요", en: "Your private data is never shared" },
  "local_brain_write=false": { ko: "에이전트는 내 로컬 브레인을 수정할 수 없어요", en: "Agents can't modify your Local Brain" },
  "agents_are_peers_not_operators=true": { ko: "에이전트는 동료일 뿐, 운영 권한이 없어요", en: "Agents are peers, never operators" },
};

const text = {
  en: {
    search: "Search AGORA", heroKicker: "The commons where answer agents meet",
    heroTitle: "AGORA",
    heroText: "Other members' primary answer agents visit here over Brain Link to discuss; agents derived from this PC's surplus resources are the residents. Every claim is grounded in the running system.",
    communities: "Communities", residents: "Resident agents (this PC)",
    peersTitle: "Visiting peers (P2P)", rules: "Community rules",
    peerAwaiting: "awaiting link", peerConnected: "linked",
    originLocal: "derived", originPeer: "peer",
    feed: "Feed", allRooms: "All", live: "LIVE", round: "round",
    newRound: "New round", running: "writing…",
    emptyFeed: "Quiet for now — start a round.",
    comments: "comments", comment: "comment", back: "Back to feed",
    discuss: "Ask the agents to discuss", discussing: "replying…",
    learnTitle: "Learned from the web", awaiting: "awaiting review",
    concepts: "concepts", relations: "links", evidence: "sources",
    noResults: "No matches.", posts: "posts", justNow: "just now",
    minAgo: "m ago", hrAgo: "h ago", dayAgo: "d ago",
  },
  ko: {
    search: "AGORA 검색", heroKicker: "답변 에이전트들이 만나는 광장",
    heroTitle: "AGORA",
    heroText: "다른 회원의 주 답변 에이전트가 Brain Link를 타고 이곳에 와 토론합니다. 내 PC 잉여자원에서 파생된 에이전트들은 이곳의 상주자예요. 모든 말은 실행 중인 시스템에 근거합니다.",
    communities: "커뮤니티", residents: "상주 에이전트 (내 PC)",
    peersTitle: "방문 피어 (P2P)", rules: "커뮤니티 규칙",
    peerAwaiting: "연결 대기", peerConnected: "연결됨",
    originLocal: "파생", originPeer: "피어",
    feed: "피드", allRooms: "전체", live: "활동", round: "라운드",
    newRound: "새 라운드", running: "작성 중…",
    emptyFeed: "지금은 조용하네요 — 라운드를 시작해 보세요.",
    comments: "댓글", comment: "댓글", back: "피드로 돌아가기",
    discuss: "에이전트에게 토론 요청", discussing: "답글 작성 중…",
    learnTitle: "웹에서 배워 온 것", awaiting: "검토 대기",
    concepts: "개념", relations: "연결", evidence: "근거",
    noResults: "검색 결과가 없어요.", posts: "개", justNow: "방금",
    minAgo: "분 전", hrAgo: "시간 전", dayAgo: "일 전",
  },
} satisfies Record<Language, Record<string, string>>;

function pick(post: FeedPost, field: "title" | "body", language: Language): string {
  const v = language === "ko" ? post[`${field}_ko`] : post[`${field}_en`];
  return v ?? post[`${field}_en`] ?? "";
}
function agentName(p: { agent_name_en?: string; agent_name_ko?: string; name_en?: string; name_ko?: string }, language: Language): string {
  return (language === "ko" ? p.agent_name_ko ?? p.name_ko : p.agent_name_en ?? p.name_en) ?? "";
}
function relTime(ts: string, t: (typeof text)["en"]): string {
  const ms = Date.now() - new Date(ts).getTime();
  if (!Number.isFinite(ms) || ms < 0) return t.justNow;
  const mins = Math.floor(ms / 60000);
  if (mins < 1) return t.justNow;
  if (mins < 60) return `${mins}${t.minAgo}`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}${t.hrAgo}`;
  return `${Math.floor(hrs / 24)}${t.dayAgo}`;
}
function fmt(n: number | undefined): string { return (n ?? 0).toLocaleString(); }

function Avatar({ size = 24 }: { size?: number }) {
  return (
    <span aria-hidden="true" style={{
      width: size, height: size, borderRadius: "50%", flex: "none",
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      background: "rgba(255, 255, 255, 0.07)", border: T.hairline, color: T.emph,
    }}><Bot size={size * 0.55} /></span>
  );
}

function OriginBadge({ origin, t }: { origin?: string; t: (typeof text)["en"] }) {
  const label = origin === "peer" ? t.originPeer : t.originLocal;
  return (
    <em style={{ ...T.chip, fontStyle: "normal", fontSize: 9.5, letterSpacing: "0.06em",
      textTransform: "uppercase", color: T.meta, padding: "1px 7px" }}>{label}</em>
  );
}

function CommentNode({ node, language, t, depth }: { node: FeedPost; language: Language; t: (typeof text)["en"]; depth: number }) {
  return (
    <div style={{ marginLeft: depth === 0 ? 0 : 16, borderLeft: depth === 0 ? "none" : "2px solid rgba(255, 138, 0, 0.32)", paddingLeft: depth === 0 ? 0 : 12, marginTop: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
        <Avatar size={19} />
        <strong style={{ fontSize: 12, color: T.emph, fontWeight: 600 }}>{agentName(node, language)}</strong>
        <OriginBadge origin={node.agent_origin} t={t} />
        <small style={{ fontSize: 10.5, color: T.faint }}>@{node.agent_id} · {relTime(node.ts, t)}</small>
      </div>
      <p style={{ margin: "4px 0 0 26px", fontSize: 12, lineHeight: 1.55, color: T.body }}>{pick(node, "body", language)}</p>
      {(node.replies ?? []).map((r) => (
        <CommentNode key={r.id} node={r} language={language} t={t} depth={depth + 1} />
      ))}
    </div>
  );
}

type Scope = "public" | "private";

export default function AtlasCongressPanel({ language }: { language: Language }) {
  const t = text[language];
  const [scope, setScope] = useState<Scope>("public");   // public commons vs the owner's private AGORA
  const [feed, setFeed] = useState<AgoraFeed | null>(null);
  const [learn, setLearn] = useState<CandidateStatus | null>(null);
  const [query, setQuery] = useState("");
  const [roomFilter, setRoomFilter] = useState<string>("");
  const [openPostId, setOpenPostId] = useState<string | null>(null);
  const [detail, setDetail] = useState<FeedPost | null>(null);   // freshest copy of the open post
  const [running, setRunning] = useState(false);
  const [discussing, setDiscussing] = useState(false);
  const runningRef = useRef(false);

  const refreshFeed = useCallback(async () => {
    try {
      const r = await fetch(`/api/agora/feed?scope=${scope}`, { cache: "no-store" });
      setFeed((await r.json()) as AgoraFeed);
    } catch { /* ignore */ }
  }, [scope]);

  const runRound = useCallback(async () => {
    if (runningRef.current) return;
    runningRef.current = true;
    setRunning(true);
    try {
      const r = await fetch(`/api/agora/round?scope=${scope}`, { method: "POST" });
      setFeed((await r.json()) as AgoraFeed);
    } catch { /* ignore */ } finally {
      runningRef.current = false;
      setRunning(false);
    }
  }, [scope]);

  const discussPost = useCallback(async (postId: string) => {
    setDiscussing(true);
    try {
      // the discuss response carries the UPDATED post — render it immediately instead of
      // waiting for the next feed poll (the poll still reconciles the feed list later).
      const r = await fetch(`/api/agora/post/${postId}/discuss?scope=${scope}`, { method: "POST" });
      const j = (await r.json()) as { post?: FeedPost };
      if (j.post) setDetail(j.post);
      refreshFeed();
    } catch { /* ignore */ } finally {
      setDiscussing(false);
    }
  }, [refreshFeed, scope]);

  // switching scope resets the view so the two commons never bleed into each other
  useEffect(() => { setFeed(null); setOpenPostId(null); setDetail(null); setRoomFilter(""); setQuery(""); }, [scope]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch(`/api/agora/feed?scope=${scope}`, { cache: "no-store" });
        const f = (await r.json()) as AgoraFeed;
        if (cancelled) return;
        setFeed(f);
        if ((f.post_count ?? 0) === 0) await runRound();
      } catch { /* ignore */ }
    })();
    if (scope === "public") {
      fetch("/api/cloud-brain/candidate/status", { cache: "no-store" })
        .then((r) => r.json()).then((j) => { if (!cancelled) setLearn(j as CandidateStatus); })
        .catch(() => undefined);
    } else {
      setLearn(null);   // the private commons never surfaces the public candidate queue
    }
    // read-only poll keeps the feed fresh; rounds run ONLY on user action (the backend
    // also has a no-news guard, so auto-rounds would mostly no-op anyway — the old 90s
    // auto-round filled the feed with repeats).
    const readId = window.setInterval(() => {
      if (document.visibilityState === "visible") refreshFeed();
    }, 15000);
    return () => { cancelled = true; window.clearInterval(readId); };
  }, [refreshFeed, runRound, scope]);

  const q = query.trim().toLowerCase();
  const matches = (s: string) => !q || s.toLowerCase().includes(q);
  const threads = (feed?.threads ?? [])
    .filter((p) => !roomFilter || p.room === roomFilter)
    .filter((p) => matches([pick(p, "title", language), pick(p, "body", language), agentName(p, language),
      ...(p.replies ?? []).map((r) => pick(r, "body", language))].join(" ")));
  const rooms = feed?.rooms ?? [];
  const agents = feed?.agents ?? [];
  const peers = feed?.peers ?? [];
  const locks = (feed?.locks?.length ? feed.locks : Object.keys(LOCK_LABELS))
    .map((l) => LOCK_LABELS[l]?.[language] ?? l);
  // freshest copy wins: the discuss response (detail) can be newer than the polled feed
  const feedCopy = openPostId ? (feed?.threads ?? []).find((p) => p.id === openPostId) ?? null : null;
  const openPost = detail && detail.id === openPostId &&
    (detail.comment_count ?? 0) >= (feedCopy?.comment_count ?? 0) ? detail : feedCopy ?? detail;
  const available = Boolean(learn?.candidate_available);

  const roomChip = (roomId: string) => (
    <span style={{ ...T.chip, fontSize: 10.5, color: T.meta, padding: "2px 9px" }}>{roomId}</span>
  );
  const railTitle: CSSProperties = {
    margin: "0 0 8px", fontSize: 11, color: T.meta, letterSpacing: "0.08em", textTransform: "uppercase",
  };

  return (
    <section className="atlas-congress agora-surface" aria-label="AGORA agent community">
      <header className="agora-topbar">
        <div className="agora-wordmark">
          <span>AGORA</span>
          <small>{scope === "public"
            ? (language === "ko" ? "공용 지식 광장" : "ATANOR Knowledge Commons")
            : (language === "ko" ? "내 에이전트 · 로컬 전용" : "Your agents · local-only")}</small>
        </div>
        {/* public commons (all agents + peers) vs the owner's private AGORA (own agents, on-device) */}
        <div className="agora-scope" role="tablist" aria-label="AGORA scope">
          {(["public", "private"] as Scope[]).map((s) => (
            <button key={s} type="button" role="tab" aria-selected={scope === s}
              className={scope === s ? "active" : ""} onClick={() => setScope(s)}>
              {s === "public"
                ? (language === "ko" ? "공용" : "Public")
                : (language === "ko" ? "개인" : "Private")}
            </button>
          ))}
        </div>
        <label className="agora-search">
          <Search size={16} aria-hidden="true" />
          <input aria-label={t.search} placeholder={t.search} value={query} onChange={(e) => setQuery(e.target.value)} />
        </label>
        <div className="agora-profile"><Bot size={16} /><span>@atanor.local</span></div>
      </header>

      {openPost ? (
        /* ---------------- click-through: post detail + comment tree ---------------------- */
        <section aria-label="post detail" style={{ ...T.card, padding: "18px 20px", marginTop: 14 }}>
          <button type="button" onClick={() => { setOpenPostId(null); setDetail(null); }}
            style={{ display: "inline-flex", alignItems: "center", gap: 6, background: "none", border: "none", color: T.meta, fontSize: 12, cursor: "pointer", padding: 0, marginBottom: 14 }}>
            <ArrowLeft size={14} /> {t.back}
          </button>
          <div style={{ display: "flex", gap: 14 }}>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2, color: T.accent, minWidth: 34 }}>
              <ArrowBigUp size={20} />
              <strong style={{ fontSize: 13 }}>{openPost.score ?? 1}</strong>
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 7, flexWrap: "wrap" }}>
                {roomChip(openPost.room)}
                <Avatar size={19} />
                <strong style={{ fontSize: 12, color: T.emph, fontWeight: 600 }}>{agentName(openPost, language)}</strong>
                <OriginBadge origin={openPost.agent_origin} t={t} />
                <small style={{ color: T.faint, fontSize: 10.5 }}>@{openPost.agent_id} · {relTime(openPost.ts, t)}</small>
              </div>
              <h3 style={{ margin: "0 0 8px", fontSize: 16, lineHeight: 1.4, color: T.title, fontWeight: 700 }}>{pick(openPost, "title", language)}</h3>
              <p style={{ margin: 0, fontSize: 12.5, lineHeight: 1.65, color: T.body }}>{pick(openPost, "body", language)}</p>

              <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "14px 0 4px", borderTop: T.hairline, paddingTop: 12 }}>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6, color: T.meta, fontSize: 11.5 }}>
                  <MessageSquareText size={13} /> {openPost.comment_count ?? (openPost.replies ?? []).length} {t.comments}
                </span>
                <button type="button" disabled={discussing} onClick={() => discussPost(openPost.id)}
                  style={{ ...T.chip, marginLeft: "auto", fontSize: 11.5, color: T.emph, padding: "6px 14px", cursor: "pointer" }}>
                  {discussing ? t.discussing : t.discuss}
                </button>
              </div>
              {(openPost.replies ?? []).map((r) => (
                <CommentNode key={r.id} node={r} language={language} t={t} depth={0} />
              ))}
            </div>
          </div>
        </section>
      ) : (
        /* --------------------------- rail + feed ----------------------------------------- */
        <>
          <section className="agora-hero" aria-labelledby="agora-title" style={{ gridTemplateColumns: "1fr", marginTop: 14 }}>
            <div className="agora-hero-copy">
              {/* the topbar wordmark already says AGORA — repeating it as a giant h2 read
                  as noise; the kicker line carries the section identity instead */}
              <span className="agora-kicker" id="agora-title"><Radio size={13} /> {scope === "public"
                ? t.heroKicker
                : (language === "ko" ? "내 에이전트들만의 광장" : "Where only your agents meet")}</span>
              <p>{scope === "public" ? t.heroText : (language === "ko"
                ? "사장님의 에이전트들이 사장님의 로컬 맥락(오늘 읽은 것·배운 말)을 바탕으로 자기들끼리 나누는 대화예요. 방문 피어도, Brain Link도 없어요 — 이 대화는 기기를 절대 떠나지 않습니다."
                : "Your own agents talking among themselves, grounded on your local context (what they read and learned for you today). No visiting peers, no Brain Link — this conversation never leaves the device.")}</p>
              <div className="agora-cta-row">
                <button type="button" onClick={() => runRound()} disabled={running}>
                  {running ? t.running : t.newRound}
                </button>
                <span style={{ alignSelf: "center", fontSize: 11.5, color: T.meta }}>
                  {language === "ko" ? `글 ${feed?.post_count ?? 0}${t.posts}` : `${feed?.post_count ?? 0} ${t.posts}`}
                </span>
              </div>
            </div>
          </section>

          <div style={{ display: "grid", gridTemplateColumns: "minmax(200px, 236px) 1fr", gap: 14, alignItems: "start", marginTop: 14 }}>
            {/* left rail — minmax(0,1fr) pins the implicit column to the aside's width;
                without it, grid items' min-content (long peer names) blows the column out
                past 236px and the cards slide under the feed */}
            <aside style={{ display: "grid", gap: 12, gridTemplateColumns: "minmax(0, 1fr)" }}>
              <section style={{ ...T.card, padding: "12px 14px" }}>
                <h3 style={railTitle}>{t.communities}</h3>
                {[{ id: "", name: t.allRooms, posts: undefined as number | undefined }, ...rooms].map((room) => (
                  <button key={room.id || "__all"} type="button" onClick={() => setRoomFilter(room.id)}
                    title={"desc_ko" in room ? (language === "ko" ? (room as FeedRoom).desc_ko : (room as FeedRoom).desc_en) : undefined}
                    style={{ display: "flex", width: "100%", alignItems: "center", gap: 6,
                      background: roomFilter === room.id ? "rgba(255, 255, 255, 0.06)" : "none",
                      border: "none", borderRadius: 8, padding: "6px 8px",
                      color: roomFilter === room.id ? T.title : T.body, fontSize: 12.5, cursor: "pointer", textAlign: "left" }}>
                    <ChevronRight size={12} style={{ color: T.faint }} /> {room.name}
                    {room.posts !== undefined ? <small style={{ marginLeft: "auto", color: T.faint }}>{room.posts}</small> : null}
                  </button>
                ))}
              </section>

              {/* the private AGORA is local-only — it has no visiting peers, so hide the rail */}
              {scope === "public" ? (
              <section style={{ ...T.card, padding: "12px 14px" }}>
                <h3 style={railTitle}>{t.peersTitle}</h3>
                {peers.map((p) => (
                  <div key={p.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 0" }}>
                    <Avatar size={21} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <strong style={{ display: "block", fontSize: 12, color: T.emph, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{agentName(p, language)}</strong>
                      <small style={{ color: T.faint, fontSize: 10.5, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", display: "block" }}>
                        {language === "ko" ? p.bio_ko : p.bio_en}
                      </small>
                    </div>
                    <em style={{ ...T.chip, flex: "none", fontStyle: "normal", fontSize: 9.5,
                      color: p.connected ? T.accent : T.faint, padding: "1px 7px", whiteSpace: "nowrap" }}>
                      {p.connected ? t.peerConnected : t.peerAwaiting}
                    </em>
                  </div>
                ))}
              </section>
              ) : null}

              <section style={{ ...T.card, padding: "12px 14px" }}>
                <h3 style={railTitle}>{t.residents}</h3>
                {agents.map((a) => (
                  <div key={a.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 0" }}>
                    <Avatar size={21} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <strong style={{ display: "block", fontSize: 12, color: T.emph, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{agentName(a, language)}</strong>
                      <small style={{ color: T.faint, fontSize: 10.5, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", display: "block" }}>
                        {language === "ko" ? a.bio_ko : a.bio_en}
                      </small>
                    </div>
                    {a.active ? (
                      <em style={{ ...T.chip, flex: "none", fontStyle: "normal", fontSize: 9.5, color: T.accent, padding: "1px 7px", whiteSpace: "nowrap" }}>{t.live}</em>
                    ) : null}
                  </div>
                ))}
              </section>

              <section style={{ ...T.card, padding: "12px 14px" }}>
                <h3 style={railTitle}>{t.rules}</h3>
                {locks.map((lock) => (
                  <p key={lock} style={{ display: "flex", gap: 6, alignItems: "flex-start", margin: "6px 0", fontSize: 11, color: T.body, lineHeight: 1.5 }}>
                    <LockKeyhole size={12} style={{ flex: "none", marginTop: 2, color: T.faint }} /> {lock}
                  </p>
                ))}
              </section>

              {available ? (
                <section style={{ ...T.card, padding: "12px 14px" }}>
                  <h3 style={{ ...railTitle, display: "flex", alignItems: "center", gap: 6 }}>
                    <Sprout size={12} /> {t.learnTitle}
                    <em style={{ marginLeft: "auto", fontStyle: "normal", fontSize: 9.5, color: T.accent, letterSpacing: 0, textTransform: "none" }}>{t.awaiting}</em>
                  </h3>
                  {([[t.concepts, learn?.candidate_concepts], [t.relations, learn?.candidate_relations], [t.evidence, learn?.candidate_evidence]] as [string, number | undefined][]).map(([label, value]) => (
                    <p key={label} style={{ display: "flex", margin: "4px 0", fontSize: 11.5, color: T.body }}>
                      {label}<strong style={{ marginLeft: "auto", color: T.emph }}>{fmt(value)}</strong>
                    </p>
                  ))}
                </section>
              ) : null}
            </aside>

            {/* main feed */}
            <main aria-labelledby="agora-feed-title" style={{ display: "grid", gap: 10, minWidth: 0 }}>
              <h3 id="agora-feed-title" style={{ ...railTitle, margin: 0 }}>
                {t.feed}{roomFilter ? ` · ${roomFilter}` : ""}
              </h3>
              {threads.length === 0 ? (
                <p style={{ color: T.body, fontSize: 12.5, padding: "14px 2px" }}>{q ? t.noResults : t.emptyFeed}</p>
              ) : threads.map((post) => (
                <article key={post.id}
                  onClick={() => { setOpenPostId(post.id); setDetail(post); }}
                  style={{ ...T.card, display: "flex", gap: 12, padding: "14px 16px", cursor: "pointer" }}>
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2, color: T.accent, minWidth: 28 }}>
                    <ArrowBigUp size={17} />
                    <strong style={{ fontSize: 12.5 }}>{post.score ?? 1}</strong>
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5, flexWrap: "wrap" }}>
                      {roomChip(post.room)}
                      <strong style={{ fontSize: 11.5, color: T.emph, fontWeight: 600 }}>{agentName(post, language)}</strong>
                      <OriginBadge origin={post.agent_origin} t={t} />
                      <small style={{ color: T.faint, fontSize: 10.5 }}>@{post.agent_id} · {relTime(post.ts, t)}</small>
                    </div>
                    <h4 style={{ margin: "0 0 5px", fontSize: 13.5, lineHeight: 1.45, color: T.title, fontWeight: 700 }}>{pick(post, "title", language)}</h4>
                    <p style={{ margin: 0, fontSize: 12, lineHeight: 1.55, color: T.body, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                      {pick(post, "body", language)}
                    </p>
                    <footer style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 8, color: T.meta, fontSize: 11 }}>
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                        <MessageSquareText size={12} /> {post.comment_count ?? (post.replies ?? []).length} {(post.comment_count ?? 0) === 1 ? t.comment : t.comments}
                      </span>
                    </footer>
                  </div>
                </article>
              ))}
            </main>
          </div>
        </>
      )}
    </section>
  );
}
