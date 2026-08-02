"use client";

type Language = "en" | "ko";
type BackendStatus = "idle" | "checking" | "connected" | "failed";
type BrainState = "loading" | "connected_empty" | "connected_with_data" | "disconnected" | "api_mismatch" | "read_only";

type BrainConnectionStatusProps = {
  language: Language;
  activeBrain: "local" | "cloud";
  labMode: boolean;
  localBackendUrl: string;
  localBackendStatus: BackendStatus;
  localBackendMessage: string;
  local: {
    nodes: number;
    relations: number;
    initialized: boolean;
    pending: boolean;
  };
  cloud: {
    concepts: number;
    relations: number;
    evidence: number;
    candidateCaseFrames: number;
    candidateAvailable: boolean;
    pending: boolean;
    source: string;
  };
};

const copy = {
  en: {
    localTitle: "Local Brain connection",
    cloudTitle: "Cloud Brain connection",
    localLoading: "Loading the Local Brain graph.",
    localEmpty: "Connected, but no Local Brain memories have been approved yet.",
    localReady: "Local Brain is connected and has readable memory.",
    localDisconnected: "Local Brain companion is not connected.",
    localMismatch: "Local Brain connection failed. Check the Companion URL.",
    cloudLoading: "Loading Cloud Brain status.",
    cloudEmpty: "Cloud Brain is connected in read-only mode, but the verified store is empty.",
    cloudReady: "Cloud Brain is connected in read-only mode.",
    cloudCandidate: "Candidate knowledge is available for review but is not production knowledge.",
    cloudDisconnected: "Cloud Brain status is not reachable from this Companion.",
    readOnly: "read-only",
    userState: "User-facing state",
    details: "Diagnostics",
    companion: "Local Companion URL",
    endpoints: "Endpoint status",
    noWrite: "No Local Brain write, Cloud write, or candidate promotion is triggered from this view.",
  },
  ko: {
    localTitle: "로컬 브레인 연결",
    cloudTitle: "클라우드 브레인 연결",
    localLoading: "로컬 브레인 그래프를 불러오는 중입니다.",
    localEmpty: "연결은 되었지만 아직 승인된 로컬 브레인 기억이 없습니다.",
    localReady: "로컬 브레인이 연결되어 읽을 수 있는 메모리가 있습니다.",
    localDisconnected: "로컬 브레인 Companion이 연결되지 않았습니다.",
    localMismatch: "로컬 브레인 연결 실패: Companion 주소를 확인하세요.",
    cloudLoading: "클라우드 브레인 상태를 불러오는 중입니다.",
    cloudEmpty: "클라우드 브레인은 읽기 전용으로 연결되었지만 verified store가 비어 있습니다.",
    cloudReady: "클라우드 브레인이 읽기 전용으로 연결되어 있습니다.",
    cloudCandidate: "후보 지식은 검토 가능하지만 production 지식이 아닙니다.",
    cloudDisconnected: "이 Companion에서 Cloud Brain 상태를 읽을 수 없습니다.",
    readOnly: "읽기 전용",
    userState: "사용자 표시 상태",
    details: "진단",
    companion: "Local Companion 주소",
    endpoints: "엔드포인트 상태",
    noWrite: "이 화면에서는 Local Brain 쓰기, Cloud 쓰기, 후보 승격이 실행되지 않습니다.",
  },
} satisfies Record<Language, Record<string, string>>;

function classifyLocal(status: BackendStatus, pending: boolean, nodes: number, initialized: boolean): BrainState {
  if (status === "checking" || pending) return "loading";
  if (status === "failed") return "api_mismatch";
  if (status !== "connected") return "disconnected";
  if (!initialized && nodes === 0) return "connected_empty";
  return "connected_with_data";
}

function classifyCloud(status: BackendStatus, pending: boolean, concepts: number, relations: number, candidateAvailable: boolean): BrainState {
  if (status === "checking" || pending) return "loading";
  if (status === "failed") return "api_mismatch";
  if (status !== "connected") return "disconnected";
  if (concepts === 0 && relations === 0 && !candidateAvailable) return "connected_empty";
  return "read_only";
}

function stateTone(state: BrainState) {
  if (state === "connected_with_data" || state === "read_only") return "green";
  if (state === "loading") return "blue";
  if (state === "connected_empty") return "orange";
  return "red";
}

export default function BrainConnectionStatus(props: BrainConnectionStatusProps) {
  const t = copy[props.language];
  const isCloud = props.activeBrain === "cloud";
  const state = isCloud
    ? classifyCloud(props.localBackendStatus, props.cloud.pending, props.cloud.concepts, props.cloud.relations, props.cloud.candidateAvailable)
    : classifyLocal(props.localBackendStatus, props.local.pending, props.local.nodes, props.local.initialized);
  const title = isCloud ? t.cloudTitle : t.localTitle;
  const userMessage = isCloud
    ? state === "loading" ? t.cloudLoading
      : state === "connected_empty" ? t.cloudEmpty
        : state === "api_mismatch" || state === "disconnected" ? t.cloudDisconnected
          : props.cloud.candidateAvailable ? t.cloudCandidate
            : t.cloudReady
    : state === "loading" ? t.localLoading
      : state === "connected_empty" ? t.localEmpty
        : state === "api_mismatch" ? t.localMismatch
          : state === "disconnected" ? t.localDisconnected
            : t.localReady;

  const rows = isCloud
    ? [
        ["Concepts", props.cloud.concepts.toLocaleString()],
        ["Relations", props.cloud.relations.toLocaleString()],
        ["Evidence", props.cloud.evidence.toLocaleString()],
        ["Candidate case frames", props.cloud.candidateCaseFrames.toLocaleString()],
      ]
    : [
        ["Nodes", props.local.nodes.toLocaleString()],
        ["Relations", props.local.relations.toLocaleString()],
        ["Initialized", String(props.local.initialized)],
        ["Mode", "private local"],
      ];

  return (
    <section className="brain-connection-status" data-state={stateTone(state)} aria-label={title}>
      <header>
        <div>
          <span>{t.userState}</span>
          <h2>{title}</h2>
        </div>
        <strong>{state.replace(/_/g, " ")}</strong>
      </header>
      <p>{userMessage}</p>
      <div className="brain-connection-counts">
        {rows.map(([label, value]) => (
          <span key={label}><small>{label}</small><b>{value}</b></span>
        ))}
      </div>
      <small className="brain-connection-safety">{t.noWrite}</small>
      {props.labMode ? (
        <details className="brain-connection-diagnostics">
          <summary>{t.details}</summary>
          <p><span>{t.companion}</span><code>{props.localBackendUrl}</code></p>
          <p><span>{t.endpoints}</span><code>{props.localBackendStatus}</code></p>
          <p><span>Last message</span><code>{props.localBackendMessage}</code></p>
          <p><span>Cloud source</span><code>{props.cloud.source || "local"}</code></p>
          <p><span>Read-only</span><code>{isCloud ? t.readOnly : "private local"}</code></p>
        </details>
      ) : null}
    </section>
  );
}
