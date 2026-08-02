"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent, WheelEvent as ReactWheelEvent } from "react";
import dynamic from "next/dynamic";
import { Bell, Brain, Cloud, Globe2, Home, MessageCircle, Mic, Moon, Network, Package, RefreshCw, Settings, Share2, Sun, SunMoon, UserCircle, UsersRound } from "lucide-react";
import AtanorUserStatusCard from "./AtanorUserStatusCard";
import DemoChat from "./DemoChat";
import { isDemo } from "./lib/profile";
import AgenticMicroOSPanel from "./AgenticMicroOSPanel";
import SeismographChart from "./SeismographChart";
import AutonomousAgentPanel from "./AutonomousAgentPanel";
const AtlasGlobe3D = dynamic(() => import("./AtlasGlobe3D"), { ssr: false, loading: () => null });
import AtlasCongressPanel from "./AtlasCongressPanel";
import CustomHubDevicePanel from "./CustomHubDevicePanel";
import DashboardImaginationLayer from "./DashboardImaginationLayer";
import BrainConnectionStatus from "./BrainConnectionStatus";
import type { CloudBrainSphereStats } from "./CloudBrainSphereScene";
const CloudBrainSphereScene = dynamic(() => import("./CloudBrainSphereScene"), { ssr: false, loading: () => null });
import LiveLearningPanel from "./LiveLearningPanel";
import { useCloudLearningMetrics } from "./useCloudLearningMetrics";
import LiveSelfhoodSchedulerPanel from "./LiveSelfhoodSchedulerPanel";
import MemoryApprovalPanel from "./MemoryApprovalPanel";
import type { Rag3DControl, Rag3DEdge, Rag3DGraph, Rag3DNode, Rag3DVisualState } from "./Rag3DScene";
const Rag3DScene = dynamic(() => import("./Rag3DScene"), { ssr: false, loading: () => null });
import SelfhoodRuntimePanel from "./SelfhoodRuntimePanel";
import { TauriUpdatePrompt } from "./TauriUpdatePrompt";

type StageState = "idle" | "running" | "warning" | "complete";
type LayoutMode = "graph" | "split" | "workbench";
type WorkspaceMode = "daemon" | "lab";
type LearningVolume = "lite" | "standard" | "deep" | "max" | "infinite";
type RightMode = "process" | "chat";
type LabStageKey = "collect" | "learn" | "output";
type AnyRecord = Record<string, any>;
type Language = "en" | "ko";
type MainSectionId = "home" | "graph" | "local" | "cloud" | "atlas" | "congress" | "agent-os" | "autonomous" | "selfhood" | "live-scheduler" | "memory-approval" | "graphhub" | "contribute" | "chat" | "settings";
type SurfaceClass = "product" | "advanced" | "lab";
type GraphPresentationMode = "home_unified_overview" | "local_private_memory" | "cloud_world_knowledge" | "unified_projection";

const mainNavIcon = {
  home: Home,
  graph: Network,
  local: Brain,
  cloud: Cloud,
  atlas: Globe2,
  congress: UsersRound,
  "agent-os": Package,
  autonomous: Brain,
  selfhood: UserCircle,
  "live-scheduler": RefreshCw,
  "memory-approval": Bell,
  graphhub: Package,
  contribute: Share2,
  chat: MessageCircle,
  settings: Settings,
} satisfies Record<MainSectionId, typeof Home>;

const mainSectionSurface = {
  home: "product",
  graph: "product",
  local: "product",
  cloud: "product",
  atlas: "product",
  contribute: "product",
  chat: "product",
  settings: "product",
  congress: "product",
  "agent-os": "lab",
  autonomous: "lab",
  "memory-approval": "advanced",
  selfhood: "lab",
  "live-scheduler": "lab",
  graphhub: "product",
} satisfies Record<MainSectionId, SurfaceClass>;

const internalMainSections = new Set<MainSectionId>(["agent-os", "autonomous", "selfhood", "live-scheduler", "memory-approval"]);

const MAIN_COPY: Record<Language, {
  nav: Array<{ id: MainSectionId; key: string; label: string }>;
  shellTitle: string;
  shellSubtitle: string;
  graphTitle: string;
  graphSubtitle: string;
  nodes: string;
  relations: string;
  sparsity: string;
  communities: string;
  systemStatus: string;
  activeTask: string;
  quickActions: string;
  recentActivity: string;
  chatTitle: string;
  chatSubtitle: string;
  send: string;
  generating: string;
  placeholder: string;
  sync: string;
  localBrain: string;
  cloudBrain: string;
  learningEngine: string;
  generationEngine: string;
  fragmentSync: string;
  running: string;
  connected: string;
  listening: string;
  ready: string;
  synced: string;
  graphSettled: string;
  localNode: string;
  cloudNode: string;
  fragmentNode: string;
  graphHint: string;
  strongRelation: string;
  weakRelation: string;
  actions: { newChat: string; graphExplore: string; memorySearch: string; learningTrigger: string; checkpoint: string };
  activity: { graphUpdate: string; patchSync: string; runtime: string; selected: string };
}> = {
  en: {
    nav: [
      { id: "home", key: "D", label: "Dashboard" },
      { id: "local", key: "L", label: "Local Brain" },
      { id: "cloud", key: "B", label: "Cloud Brain" },
      { id: "atlas", key: "A", label: "Atlas" },
      { id: "congress", key: "C", label: "AGORA" },
      { id: "agent-os", key: "O", label: "Agentic OS" },
      { id: "autonomous", key: "U", label: "Autonomous Agent" },
      { id: "selfhood", key: "F", label: "Selfhood Lab" },
      { id: "live-scheduler", key: "Y", label: "Live Scheduler" },
      { id: "memory-approval", key: "M", label: "Memory Approval" },
      { id: "graphhub", key: "H", label: "Custom Hub" },
      { id: "contribute", key: "P", label: "Brain Link" },
      { id: "settings", key: "S", label: "Settings" },
    ],
    shellTitle: "ATANOR",
    shellSubtitle: "LOCAL-FIRST HYBRID AI ENGINE",
    graphTitle: "Unified Knowledge Graph",
    graphSubtitle: "A visual projection of Local, Seed, and Cloud layers. It does not indicate a live bridge.",
    nodes: "Nodes",
    relations: "Relations",
    sparsity: "Sparsity",
    communities: "Communities",
    systemStatus: "System Status",
    activeTask: "Active Task",
    quickActions: "Quick Actions",
    recentActivity: "Recent Activity",
    chatTitle: "ATANOR",
    chatSubtitle: "Ask the Local Brain's knowledge graph — grounded answers, honest when unsure.",
    send: "Send",
    generating: "Generating",
    placeholder: "Ask ATANOR about the current memory graph...",
    sync: "Sync",
    localBrain: "Local Brain",
    cloudBrain: "Cloud Brain",
    learningEngine: "Learning Engine",
    generationEngine: "Generation Engine",
    fragmentSync: "Fragment Sync",
    running: "Running",
    connected: "Connected",
    listening: "Listening",
    ready: "Ready",
    synced: "Synced",
    graphSettled: "Graph settled",
    localNode: "Local Brain Node",
    cloudNode: "Cloud Brain Node",
    fragmentNode: "Cloud Fragment",
    graphHint: "Drag to rotate / Scroll to zoom / Click node to inspect",
    strongRelation: "Relation Strong",
    weakRelation: "Relation Weak",
    actions: {
      newChat: "New Conversation",
      graphExplore: "Graph Exploration",
      memorySearch: "Memory Search",
      learningTrigger: "Learning Trigger",
      checkpoint: "Checkpoint",
    },
    activity: {
      graphUpdate: "Graph Update",
      patchSync: "Patch Sync",
      runtime: "Runtime",
      selected: "Selected",
    },
  },
  ko: {
    nav: [
      { id: "home", key: "D", label: "대시보드" },
      { id: "local", key: "L", label: "로컬 브레인" },
      { id: "cloud", key: "B", label: "클라우드 브레인" },
      { id: "atlas", key: "A", label: "아틀라스" },
      { id: "congress", key: "C", label: "AGORA" },
      { id: "agent-os", key: "O", label: "Agentic OS" },
      { id: "autonomous", key: "U", label: "Autonomous Agent" },
      { id: "selfhood", key: "F", label: "Selfhood Lab" },
      { id: "live-scheduler", key: "Y", label: "Live Scheduler" },
      { id: "memory-approval", key: "M", label: "Memory Approval" },
      { id: "graphhub", key: "H", label: "Custom Hub" },
      { id: "contribute", key: "P", label: "브레인 링크" },
      { id: "settings", key: "S", label: "설정" },
    ],
    shellTitle: "ATANOR",
    shellSubtitle: "로컬 우선 하이브리드 AI 엔진",
    graphTitle: "통합 지식 그래프",
    graphSubtitle: "로컬, 시드, 클라우드 레이어를 하나의 시각 투영으로 봅니다. 실제 연결 상태를 뜻하지 않습니다.",
    nodes: "노드",
    relations: "관계",
    sparsity: "희소도",
    communities: "커뮤니티",
    systemStatus: "시스템 상태",
    activeTask: "활성 작업",
    quickActions: "빠른 실행",
    recentActivity: "최근 활동",
    chatTitle: "ATANOR",
    chatSubtitle: "로컬 브레인 지식 그래프에 질문하세요 — 근거를 갖춘 답, 모르면 정직하게 보류.",
    send: "보내기",
    generating: "생성 중",
    placeholder: "현재 로컬 브레인에 대해 질문하세요...",
    sync: "동기화",
    localBrain: "로컬 브레인",
    cloudBrain: "클라우드 브레인",
    learningEngine: "학습 엔진",
    generationEngine: "생성 엔진",
    fragmentSync: "프래그먼트 동기화",
    running: "실행 중",
    connected: "연결됨",
    listening: "수신 중",
    ready: "준비됨",
    synced: "동기화됨",
    graphSettled: "그래프 안정화",
    localNode: "로컬 브레인 노드",
    cloudNode: "클라우드 브레인 노드",
    fragmentNode: "클라우드 프래그먼트",
    graphHint: "드래그 회전 / 스크롤 확대 / 노드 선택",
    strongRelation: "강한 관계",
    weakRelation: "약한 관계",
    actions: {
      newChat: "새 대화",
      graphExplore: "그래프 탐색",
      memorySearch: "메모리 검색",
      learningTrigger: "학습 시작",
      checkpoint: "체크포인트",
    },
    activity: {
      graphUpdate: "그래프 업데이트",
      patchSync: "패치 동기화",
      runtime: "누적 시간",
      selected: "선택 노드",
    },
  },
};

const INITIAL_CHAT_PROMPT: Record<Language, string> = {
  en: "How does GraphRAG verify answers with evidence documents?",
  ko: "GraphRAG가 근거 문서를 어떻게 사용해서 답변을 검증하나요?",
};

const INITIAL_ASSISTANT_MESSAGE: Record<Language, string> = {
  en: "Ask ATANOR anything. It answers from the Local Brain's knowledge graph — grounded in what it knows, and honest when it isn't sure.",
  ko: "무엇이든 물어보세요. 로컬 브레인의 지식 그래프에서 근거를 갖춰 답하고, 확실하지 않으면 정직하게 보류합니다.",
};

const EFFECTIVE_MAIN_COPY: typeof MAIN_COPY = MAIN_COPY;
const EFFECTIVE_INITIAL_CHAT_PROMPT: Record<Language, string> = INITIAL_CHAT_PROMPT;
const EFFECTIVE_INITIAL_ASSISTANT_MESSAGE: Record<Language, string> = INITIAL_ASSISTANT_MESSAGE;

const labStageOrder: LabStageKey[] = ["collect", "learn", "output"];

type PipelineStage = {
  id: string;
  name: string;
  state: StageState;
  progress: number;
  summary: string;
  metric_label: string;
  metric_value: string;
};

type PipelineStatus = {
  generated_at: string;
  system_state: string;
  stages: PipelineStage[];
};

const defaultEdgeBrokerStatus: AnyRecord = {
  state: "viewer_only",
  architecture: "edge_compute_broker",
  cloud_required: false,
  capacity: {
    peer_id: "deployment-viewer",
    tier: "viewer",
    idle: false,
    endpoint: null,
    task_types: ["status_view"],
    max_batch_nodes: 0,
    max_batch_edges: 0,
  },
};

type ChatMessage = {
  role: "user" | "assistant";
  text: string;
  evidence?: AnyRecord[];
  diagnostics?: AnyRecord;
};

type MemoryNode = {
  id: string;
  label: string;
  type: string;
  confidence: number;
  x: number;
  y: number;
  color: string;
};

type MemoryEdge = {
  id: string;
  source: string;
  target: string;
  relation: string;
  confidence: number;
};

type GraphView = {
  scale: number;
  x: number;
  y: number;
};

type DragState = {
  pointerId: number;
  startX: number;
  startY: number;
  view: GraphView;
};

type AtlasDragState = {
  pointerId: number;
  startX: number;
  startRotationDeg: number;
};

type BuildRun = {
  run_id: string;
  generated_at: string;
  mode: string;
  harvest_docs: AnyRecord[];
  graph_3d: Rag3DGraph;
  graph_frames: AnyRecord[];
  learning_profile?: AnyRecord;
  training_gate: AnyRecord;
  training_units?: AnyRecord[];
  learning_trace: AnyRecord[];
  web_search?: AnyRecord;
  notes: string[];
};

const liveGrowthTemplates = [
  { label: "시냅스 가소성", type: "ontology", source: "mutable-kg", relation: "reinforces_memory" },
  { label: "작업기억 루프", type: "retrieval", source: "anchor", relation: "routes_context" },
  { label: "Few-shot 원형", type: "training", source: "oven", relation: "forms_prototype" },
  { label: "SNN 이벤트", type: "source", source: "harvest", relation: "fires_event" },
  { label: "지식 증류", type: "training", source: "guard", relation: "distills_signal" },
  { label: "Guard 기억", type: "guardrail", source: "guard", relation: "protects_claim" },
  { label: "전문가 모듈", type: "ontology", source: "dedupe", relation: "specializes" },
  { label: "수면 압축", type: "visualization", source: "3d", relation: "consolidates" },
  { label: "추출한다", type: "verb", source: "harvest", relation: "acts_on" },
  { label: "근거 문장", type: "phrase", source: "anchor", relation: "forms_phrase" },
  { label: "공출현 측정", type: "relation", source: "mutable-kg", relation: "co_occurs" },
];

const maxTargetNodes = 500_000;
const liveGrowthBatchSize = 12;
const minLiveGrowthPulses = 8;

function stableUnit(value: string, salt: number) {
  let hash = 2166136261 ^ salt;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return ((hash >>> 0) / 4294967295) * 2 - 1;
}

function stableDirection(value: string) {
  const y = stableUnit(value, 17);
  const theta = (stableUnit(value, 41) + 1) * Math.PI;
  const radial = Math.sqrt(Math.max(0.0001, 1 - y * y));
  return {
    x: Math.cos(theta) * radial,
    y,
    z: Math.sin(theta) * radial,
  };
}

const learningVolumePresets: Record<LearningVolume, { label: string; textBudget: string; chunkBudget: number; visualNodes: number; targetNodes: number | null; edgeRatio: number; durationHours: number; detail: string }> = {
  lite: { label: "가볍게", textBudget: "12k chars", chunkBudget: 32, visualNodes: 12, targetNodes: 3_000, edgeRatio: 3, durationHours: 12, detail: "응답 확인용" },
  standard: { label: "표준", textBudget: "48k chars", chunkBudget: 128, visualNodes: 24, targetNodes: 10_000, edgeRatio: 4, durationHours: 72, detail: "기본 학습" },
  deep: { label: "깊게", textBudget: "160k chars", chunkBudget: 384, visualNodes: 36, targetNodes: 25_000, edgeRatio: 4, durationHours: 168, detail: "대량 텍스트" },
  max: { label: "최대", textBudget: "4.5m chars", chunkBudget: 4096, visualNodes: 2000, targetNodes: 500_000, edgeRatio: 4.8, durationHours: 168, detail: "압축 메모리" },
  infinite: { label: "∞", textBudget: "continuous", chunkBudget: 4096, visualNodes: 2000, targetNodes: null, edgeRatio: 6, durationHours: 720, detail: "중지 전까지 지속" },
};

function defaultTargetNodesForVolume(volume: LearningVolume) {
  return volume === "max" || volume === "infinite" ? maxTargetNodes : learningVolumePresets[volume].targetNodes ?? 10_000;
}

function VoiceMicButton({ onText, disabled, language }: { onText: (t: string) => void; disabled?: boolean; language: string }) {
  // Voice input v0 — mic → LOCAL Whisper (/api/voice/transcribe). The browser's own
  // SpeechRecognition is deliberately not used: Chrome routes it through Google's
  // cloud, and the contract here is that audio never leaves the device.
  const [micState, setMicState] = useState<"idle" | "rec" | "busy" | "off">("idle");
  const recRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const toggle = async () => {
    if (micState === "rec") { recRef.current?.stop(); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream, { mimeType: "audio/webm" });
      chunksRef.current = [];
      rec.ondataavailable = (e) => { if (e.data.size) chunksRef.current.push(e.data); };
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setMicState("busy");
        try {
          const fd = new FormData();
          fd.append("file", new Blob(chunksRef.current, { type: "audio/webm" }), "mic.webm");
          const res = await fetch("/api/voice/transcribe", { method: "POST", body: fd });
          const body = await res.json().catch(() => ({}));
          if (res.ok && body.text) onText(String(body.text));
          setMicState(res.ok ? "idle" : "off");
        } catch { setMicState("off"); }
      };
      recRef.current = rec;
      rec.start();
      setMicState("rec");
    } catch { setMicState("off"); }
  };
  const title = micState === "off"
    ? (language === "ko" ? "로컬 음성 엔진 사용 불가" : "Local STT unavailable")
    : micState === "rec"
      ? (language === "ko" ? "녹음 중지 후 전사" : "Stop & transcribe")
      : (language === "ko" ? "음성 입력 — 로컬 Whisper, 기기 밖으로 나가지 않음" : "Voice input — local Whisper, never leaves this device");
  return (
    <button type="button" onClick={toggle} disabled={disabled || micState === "busy"} title={title}
      aria-label={title} data-mic-state={micState}
      style={{ minWidth: 40, borderRadius: 10, border: "1px solid rgba(255,255,255,.18)",
               background: micState === "rec" ? "rgba(255,80,60,.18)" : "transparent",
               color: micState === "off" ? "rgba(255,255,255,.3)" : "inherit", cursor: "pointer" }}>
      {micState === "rec" ? "■" : micState === "busy" ? "…" : "🎙"}
    </button>
  );
}

function buildLiveGrowth(base: Rag3DGraph, pulseCount: number, maxTotalNodes = Number.POSITIVE_INFINITY): Rag3DGraph {
  const liveNodes: Rag3DNode[] = [];
  const liveEdges: Rag3DEdge[] = [];
  const baseIds = new Set(base.nodes.map((node) => node.id));
  const baseNodeMap = new Map(base.nodes.map((node) => [node.id, node]));
  const baseCenter = base.nodes.reduce(
    (center, node) => ({
      x: center.x + (node.x ?? 0),
      y: center.y + (node.y ?? 0),
      z: center.z + (node.z ?? 0),
    }),
    { x: 0, y: 0, z: 0 },
  );
  if (base.nodes.length) {
    baseCenter.x /= base.nodes.length;
    baseCenter.y /= base.nodes.length;
    baseCenter.z /= base.nodes.length;
  }
  const baseRadius = Math.max(
    3.4,
    ...base.nodes.map((node) => {
      const dx = (node.x ?? 0) - baseCenter.x;
      const dy = (node.y ?? 0) - baseCenter.y;
      const dz = (node.z ?? 0) - baseCenter.z;
      return Math.sqrt(dx * dx + dy * dy + dz * dz);
    }),
  );
  const totalLiveNodeCount = Math.max(0, Math.floor(pulseCount)) * liveGrowthBatchSize;
  const maxRenderedNodes = Number.isFinite(maxTotalNodes) ? Math.max(base.nodes.length, Math.floor(maxTotalNodes)) : Number.POSITIVE_INFINITY;
  const renderSlots = Math.max(0, Math.floor(maxRenderedNodes - base.nodes.length));
  const startIndex = 0;
  const endIndex = Math.min(totalLiveNodeCount, renderSlots);
  for (let index = startIndex; index < endIndex; index += 1) {
    const template = liveGrowthTemplates[index % liveGrowthTemplates.length];
    const id = `live-synapse-${index + 1}`;
    const previous = index > startIndex ? `live-synapse-${index}` : null;
    const batchStart = Math.floor(index / liveGrowthBatchSize) * liveGrowthBatchSize;
    const batchIndex = Math.floor(index / liveGrowthBatchSize);
    const batchAnchor = base.nodes[(batchIndex * 3 + index) % Math.max(1, base.nodes.length)]?.id;
    const source = index === batchStart
      ? baseIds.has(template.source) ? template.source : batchAnchor
      : previous ?? batchAnchor;
    const sourceAnchor = baseIds.has(template.source) ? template.source : batchAnchor;
    const anchorNode = baseNodeMap.get(sourceAnchor ?? "") ?? base.nodes[batchIndex % Math.max(1, base.nodes.length)];
    const batchOffset = index - batchStart;
    const direction = stableDirection(id);
    const shell = baseRadius + 0.8 + Math.cbrt(index + 1) * 0.86 + Math.floor(index / liveGrowthBatchSize) * 0.055;
    const anchorBlend = Math.max(0.18, 0.42 - Math.min(0.22, batchIndex * 0.01));
    const shellPoint = {
      x: baseCenter.x + direction.x * shell,
      y: baseCenter.y + direction.y * shell * 0.9,
      z: baseCenter.z + direction.z * shell,
    };
    liveNodes.push({
      id,
      label: `${template.label} ${index + 1}`,
      type: template.type,
      x: shellPoint.x * (1 - anchorBlend) + (anchorNode?.x ?? baseCenter.x) * anchorBlend,
      y: shellPoint.y * (1 - anchorBlend) + (anchorNode?.y ?? baseCenter.y) * anchorBlend,
      z: shellPoint.z * (1 - anchorBlend) + (anchorNode?.z ?? baseCenter.z) * anchorBlend,
      confidence: 0.62 + ((index % 9) * 0.026),
    });
    if (source) {
      liveEdges.push({ source, target: id, relation: template.relation, weight: 0.58 + ((index % 6) * 0.045) });
    }
    if (previous && index !== batchStart) {
      liveEdges.push({ source: previous, target: id, relation: "parallel_association", weight: 0.62 });
    }
    if (index - liveGrowthBatchSize >= startIndex) {
      liveEdges.push({ source: `live-synapse-${index + 1 - liveGrowthBatchSize}`, target: id, relation: "consolidates_with", weight: 0.55 });
    }
  }
  return {
    nodes: [...base.nodes, ...liveNodes],
    edges: [...base.edges, ...liveEdges],
    traversal_path: [...(base.traversal_path ?? []), ...liveNodes.slice(-8).map((node) => node.id)],
  };
}

type CloudArrival = { id: string; label: string; born: number; anchorSeed: number; seq: number };

/**
 * Inject newly-learned "arrival" nodes onto the OUTER shell of the (otherwise
 * fixed) cloud graph. The count comes from the REAL continuous-learning metrics
 * delta — N concepts/relations learned → N arrivals spawn outside, each wired to
 * an existing node by an edge. Rag3DScene then flashes them (born-at) and grows
 * the orange tendril out to them; the poller drops them after a few seconds so
 * they fade back into the field instead of accumulating.
 */
function appendCloudArrivals(base: Rag3DGraph, arrivals: CloudArrival[]): Rag3DGraph {
  if (!arrivals.length || !base.nodes.length) return base;
  let cx = 0, cy = 0, cz = 0;
  base.nodes.forEach((node) => { cx += node.x; cy += node.y; cz += node.z; });
  const count = base.nodes.length;
  cx /= count; cy /= count; cz /= count;
  // Robust radius = 90th-percentile distance (NOT max), so a stray base outlier
  // can't inflate it and fling arrivals far out.
  const dists = base.nodes.map((node) => Math.hypot(node.x - cx, node.y - cy, node.z - cz)).sort((a, b) => a - b);
  const radius = Math.max(2, dists[Math.floor(dists.length * 0.9)] ?? dists[dists.length - 1] ?? 2);
  const extraNodes: Rag3DNode[] = [];
  const extraEdges: Rag3DEdge[] = [];
  arrivals.forEach((arrival) => {
    // Even spread over the WHOLE sphere via a low-discrepancy (golden-ratio)
    // sequence keyed by a monotonic seq — so consecutive arrivals are maximally
    // separated and no side of the ball gets a denser cluster.
    const seq = arrival.seq;
    const zLat = 1 - 2 * (((seq + 0.5) * 0.6180339887498949) % 1);
    const zRad = Math.sqrt(Math.max(0.0001, 1 - zLat * zLat));
    const theta = seq * 2.399963229728653;
    const dir = { x: Math.cos(theta) * zRad, y: zLat, z: Math.sin(theta) * zRad };
    // Sit ON the shell (embedded), not protruding, so arrivals don't dangle out.
    const reach = radius * (0.97 + ((stableUnit(arrival.id, 17) + 1) / 2) * 0.04);
    const ax = cx + dir.x * reach;
    const ay = cy + dir.y * reach;
    const az = cz + dir.z * reach;
    extraNodes.push({
      id: arrival.id,
      label: arrival.label,
      type: "cloud_arrival",
      x: ax,
      y: ay,
      z: az,
      confidence: 0.72,
      source_type: "cloud_fragment",
    });
    // The new node reaches out WIDELY — to nodes anywhere on the sphere, including
    // the far side — so the orange tendrils are long and far-reaching, not timid
    // local stubs (related content can live anywhere in the graph). Deterministic
    // per id so the edges stay put.
    const linkCount = 4 + (arrival.anchorSeed % 4); // 4..7
    const picks = new Set<number>();
    for (let k = 0; picks.size < linkCount && k < linkCount * 4; k += 1) {
      const idx = Math.floor(((stableUnit(arrival.id, 100 + k) + 1) / 2) * base.nodes.length) % base.nodes.length;
      picks.add(idx);
    }
    picks.forEach((idx) => {
      const node = base.nodes[idx];
      if (!node) return;
      // source = arrival (new node) — the tendril originates AT the new node and
      // grows out to the related existing node, wherever it is.
      extraEdges.push({ source: arrival.id, target: node.id, relation: "newly_learned", weight: 0.72, source_type: "cloud_fragment" });
    });
  });
  // Clamp ANY node (base or arrival) that sits beyond the ball into the shell, so
  // there are no extreme dangling outliers.
  const maxR = radius * 1.15;
  const clamp = (node: Rag3DNode): Rag3DNode => {
    const dx = node.x - cx, dy = node.y - cy, dz = node.z - cz;
    const d = Math.hypot(dx, dy, dz);
    if (d > maxR && d > 0.0001) {
      const s = maxR / d;
      return { ...node, x: cx + dx * s, y: cy + dy * s, z: cz + dz * s };
    }
    return node;
  };
  return {
    nodes: [...base.nodes, ...extraNodes].map(clamp),
    edges: [...base.edges, ...extraEdges],
    traversal_path: base.traversal_path,
  };
}

function buildStudioTopologyGraph(graph: Rag3DGraph): Rag3DGraph {
  if (!graph.nodes.length) return graph;
  const degree = new Map<string, number>();
  graph.nodes.forEach((node) => degree.set(node.id, 0));
  graph.edges.forEach((edge) => {
    degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1);
    degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1);
  });
  const sortedIds = [...graph.nodes]
    .sort((left, right) => (degree.get(right.id) ?? 0) - (degree.get(left.id) ?? 0))
    .map((node) => node.id);
  const anchorCount = Math.max(5, Math.min(18, Math.round(Math.sqrt(graph.nodes.length) / 2.1)));
  const anchors = sortedIds.slice(0, anchorCount);
  const anchorSet = new Set(anchors);
  const anchorIndex = new Map(anchors.map((id, index) => [id, index]));
  const neighborAnchors = new Map<string, string>();
  graph.edges.forEach((edge) => {
    if (anchorSet.has(edge.source) && !neighborAnchors.has(edge.target)) neighborAnchors.set(edge.target, edge.source);
    if (anchorSet.has(edge.target) && !neighborAnchors.has(edge.source)) neighborAnchors.set(edge.source, edge.target);
  });
  const anchorPosition = (id: string, index: number) => {
    if (index === 0) return { x: 0, y: 0, z: 0 };
    const side = index % 2 === 0 ? 1 : -1;
    const lane = Math.ceil(index / 2);
    const laneRatio = lane / Math.max(1, Math.ceil(anchorCount / 2));
    const arc = -0.9 + laneRatio * 1.8;
    return {
      x: side * (1.9 + laneRatio * 5.85),
      y: Math.sin(arc) * 5.35 + stableUnit(id, 501) * 0.42,
      z: Math.cos(arc) * 2.45 + stableUnit(id, 503) * 0.72,
    };
  };
  const anchorPositions = new Map<string, { x: number; y: number; z: number }>();
  anchors.forEach((id, index) => anchorPositions.set(id, anchorPosition(id, index)));
  const nodes = graph.nodes.map((node, index) => {
    const directAnchor = anchorSet.has(node.id)
      ? node.id
      : neighborAnchors.get(node.id) ?? anchors[Math.floor(((stableUnit(node.id, 601) + 1) / 2) * anchors.length) % anchors.length];
    const anchor = anchorPositions.get(directAnchor) ?? { x: 0, y: 0, z: 0 };
    const rank = anchorIndex.get(node.id);
    if (typeof rank === "number") {
      const type = anchor.x > 1.2 ? "cloud_brain" : anchor.x < -1.2 ? "local_memory" : "representative_sample";
      return {
        ...node,
        x: anchor.x,
        y: anchor.y,
        z: anchor.z,
        source_type: rank % 6 === 0 ? "cloud_fragment" : type,
      };
    }
    const degreeBoost = Math.min(1.7, 0.38 + Math.log1p(degree.get(node.id) ?? 0) * 0.2);
    const radius = degreeBoost + ((stableUnit(node.id, 607) + 1) / 2) * 1.84;
    const theta = (stableUnit(node.id, 613) + 1) * Math.PI;
    const x = anchor.x + Math.cos(theta) * radius * 0.92;
    const y = anchor.y + Math.sin(theta) * radius * 1.14 + stableUnit(`${node.id}:${index}`, 619) * 0.42;
    const z = anchor.z + stableUnit(node.id, 617) * 2.18;
    const sourceType = x > 1.7
      ? (index % 7 === 0 ? "cloud_fragment" : "cloud_brain")
      : x < -1.7
        ? "local_memory"
        : "representative_sample";
    return {
      ...node,
      x,
      y,
      z,
      source_type: sourceType,
    };
  });
  const targetVisualEdges = Math.min(graph.edges.length, Math.max(420, Math.round(Math.sqrt(graph.nodes.length) * 20)));
  const stride = Math.max(1, Math.ceil(graph.edges.length / targetVisualEdges));
  const visualEdges = graph.edges.filter((edge, index) => {
    if (anchorSet.has(edge.source) || anchorSet.has(edge.target)) return true;
    if ((degree.get(edge.source) ?? 0) > 8 && (degree.get(edge.target) ?? 0) > 8 && index % Math.max(1, Math.floor(stride / 2)) === 0) return true;
    return index % stride === 0;
  }).slice(0, targetVisualEdges);
  return { ...graph, nodes, edges: visualEdges };
}

function graphPresentationModeForSection(section: MainSectionId): GraphPresentationMode {
  if (section === "local" || section === "chat") return "local_private_memory";
  if (section === "cloud") return "cloud_world_knowledge";
  if (section === "graph") return "unified_projection";
  return "home_unified_overview";
}

function projectAtlasPoint(lat: number, lng: number) {
  const safeLat = clamp(Number.isFinite(lat) ? lat : 0, -72, 72);
  const normalizedLng = ((((Number.isFinite(lng) ? lng : 0) + 180) % 360) + 360) % 360 - 180;
  const safeLng = clamp(normalizedLng, -180, 180);
  const x = 50 + (safeLng / 180) * 38;
  const y = 50 - (safeLat / 90) * 32;
  return { x: clamp(x, 11, 89), y: clamp(y, 12, 88) };
}

function buildSphericalTopologyGraph(graph: Rag3DGraph, mode: GraphPresentationMode): Rag3DGraph {
  if (!graph.nodes.length) return graph;
  const degree = new Map<string, number>();
  graph.nodes.forEach((node) => degree.set(node.id, 0));
  graph.edges.forEach((edge) => {
    degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1);
    degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1);
  });
  const rankedIds = new Map(
    [...graph.nodes]
      .sort((left, right) => (degree.get(right.id) ?? 0) - (degree.get(left.id) ?? 0))
      .map((node, index) => [node.id, index]),
  );
  // Balanced placement order: a stable HASH of the id (not degree-rank), so
  // high-degree hubs are scattered evenly over the sphere instead of clustering
  // at one pole — this keeps the EDGE density uniform (no top-heavy clump). It
  // re-derives every time the graph changes, so it self-balances on growth.
  const balancedSeq = new Map(
    graph.nodes
      .map((node) => ({ id: node.id, h: stableUnit(node.id, 953) }))
      .sort((left, right) => left.h - right.h)
      .map((entry, index) => [entry.id, index]),
  );
  const nodeCount = graph.nodes.length;
  const localClusters = ["user_knowledge", "project_memory", "saved_conversations", "documents", "payload_vault", "ghost_shell", "local_evidence"];
  const cloudClusters = ["world_knowledge", "public_ontology", "source_cluster", "live_fragment", "trust_provenance", "freshness"];
  const nodes = graph.nodes.map((node, index) => {
    const rank = rankedIds.get(node.id) ?? index;
    const theta = index * 2.399963229728653 + stableUnit(node.id, 811) * 0.32;
    const scatter = 0.45 + ((stableUnit(node.id, 809) + 1) / 2);
    let x = 0;
    let y = 0;
    let z = 0;
    let sourceType = "local_memory";
    let clusterId = "local_memory";

    if (mode === "local_private_memory") {
      const cluster = localClusters[Math.abs(Math.floor((rank * 3 + index) % localClusters.length))];
      const clusterIndex = localClusters.indexOf(cluster);
      const clusterAngle = (clusterIndex / localClusters.length) * Math.PI * 2 - Math.PI / 2;
      const clusterRadius = cluster === "payload_vault" || cluster === "ghost_shell" ? 2.7 : 2.0;
      const centerX = Math.cos(clusterAngle) * clusterRadius * 0.75;
      const centerY = Math.sin(clusterAngle) * clusterRadius * 0.52;
      const centerZ = (clusterIndex - localClusters.length / 2) * 0.18;
      const nodeRadius = (rank < 28 ? 0.42 : 0.76 + scatter * 0.62) * (cluster === "payload_vault" ? 0.72 : 1);
      x = centerX + Math.cos(theta) * nodeRadius;
      y = centerY + Math.sin(theta) * nodeRadius * 0.86;
      z = centerZ + stableUnit(node.id, 821) * 1.2;
      sourceType = rank % 53 === 0 ? "cloud_fragment_disabled" : rank % 9 === 0 ? "representative_sample" : "local_memory";
      clusterId = `local:${cluster}`;
    } else if (mode === "cloud_world_knowledge") {
      if (nodeCount <= 24) {
        if (rank === 0) {
          x = 0;
          y = 0;
          z = 0.15;
        } else {
          const smallAngle = ((rank - 1) / Math.max(1, nodeCount - 1)) * Math.PI * 2 - Math.PI / 2;
          const smallRadius = 1.55 + (rank % 3) * 0.28;
          x = Math.cos(smallAngle) * smallRadius * 1.18;
          y = Math.sin(smallAngle) * smallRadius * 0.82;
          z = stableUnit(node.id, 824) * 0.88;
        }
        sourceType = rank === 0 ? "cloud_fragment" : "cloud_brain";
        clusterId = "cloud:proof_store";
        return {
          ...node,
          x,
          y,
          z,
          source_type: sourceType,
          cluster_id: clusterId,
        };
      }
      const cluster = cloudClusters[Math.abs(Math.floor((rank * 5 + index) % cloudClusters.length))];
      const clusterIndex = cloudClusters.indexOf(cluster);
      // Spherical envelope by the BALANCED hash sequence (latitude + golden-angle
      // longitude) — even node + edge density, no degree-driven top clump.
      const seq = balancedSeq.get(node.id) ?? index;
      const lat = 1 - ((seq + 0.5) / Math.max(1, nodeCount)) * 2;
      const latRadial = Math.sqrt(Math.max(0.02, 1 - lat * lat));
      const lon = seq * 2.399963229728653 + stableUnit(node.id, 811) * 0.22;
      const sphereRadius = 5.7 + scatter * 0.9;
      x = Math.cos(lon) * latRadial * sphereRadius;
      y = lat * sphereRadius;
      z = Math.sin(lon) * latRadial * sphereRadius;
      sourceType = rank % 41 === 0 ? "representative_sample_edge_consumer" : rank % 5 === 0 ? "cloud_fragment" : "cloud_brain";
      clusterId = `cloud:${cluster}`;
    } else {
      const band = rank % 10;
      const isWorking = band >= 8;
      const isCloud = band >= 4 && band < 8;
      const side = isWorking ? 0 : isCloud ? 1 : -1;
      const lobeCenterX = side * 4.7;
      const lobeCenterY = isWorking ? 0 : stableUnit(`${node.id}:lobe`, 827) * 1.1;
      const lobeRadius = isWorking ? 1.25 + scatter * 0.45 : 1.55 + scatter * 0.85;
      x = lobeCenterX + Math.cos(theta) * lobeRadius * (isWorking ? 0.82 : 1.1);
      y = lobeCenterY + Math.sin(theta) * lobeRadius * 0.86;
      z = stableUnit(node.id, 831) * (isWorking ? 1.4 : 2.3);
      sourceType = isWorking ? "cloud_fragment_working_memory" : isCloud ? (rank % 6 === 0 ? "cloud_fragment" : "cloud_brain") : "local_memory";
      clusterId = isWorking ? "unified:working_memory" : isCloud ? "unified:cloud_brain" : "unified:local_brain";
    }

    return {
      ...node,
      x,
      y,
      z,
      source_type: sourceType,
      cluster_id: clusterId,
    };
  });
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const targetVisualEdges = mode === "local_private_memory"
    ? Math.min(graph.edges.length, Math.max(260, Math.round(nodeCount * 0.78)))
    : mode === "cloud_world_knowledge"
      ? Math.min(graph.edges.length, Math.max(520, Math.round(nodeCount * 1.28)))
      : Math.min(graph.edges.length, Math.max(420, Math.round(nodeCount * 0.92)));
  const stride = Math.max(1, Math.ceil(graph.edges.length / targetVisualEdges));
  const visualEdges = graph.edges.filter((edge, index) => {
    const sourceRank = rankedIds.get(edge.source) ?? Number.MAX_SAFE_INTEGER;
    const targetRank = rankedIds.get(edge.target) ?? Number.MAX_SAFE_INTEGER;
    const sourceNode = nodeById.get(edge.source);
    const targetNode = nodeById.get(edge.target);
    const sourceCluster = String(sourceNode?.cluster_id ?? "");
    const targetCluster = String(targetNode?.cluster_id ?? "");
    if (mode === "unified_projection") {
      if (sourceCluster !== targetCluster && index % Math.max(1, Math.floor(stride / 3)) === 0) return true;
      if (sourceRank < 16 || targetRank < 16) return true;
      return index % Math.max(stride * 2, 1) === 0;
    }
    if (mode === "local_private_memory") {
      if (/disabled|cloud/i.test(String(sourceNode?.source_type ?? "")) || /disabled|cloud/i.test(String(targetNode?.source_type ?? ""))) return false;
      if (sourceRank < 14 || targetRank < 14) return true;
      if (sourceCluster !== targetCluster && index % Math.max(1, stride) === 0) return true;
      return index % Math.max(1, stride * 2) === 0;
    }
    if (sourceRank < 18 || targetRank < 18) return true;
    if (sourceCluster !== targetCluster && index % Math.max(1, Math.floor(stride / 2)) === 0) return true;
    if (sourceRank < 80 && targetRank < 80 && index % Math.max(1, Math.floor(stride / 2)) === 0) return true;
    return index % stride === 0;
  }).slice(0, targetVisualEdges);
  return { ...graph, nodes, edges: visualEdges };
}

function brainGraphLayerSourceType(node: AnyRecord) {
  const layer = String(node.layer ?? node.kind ?? "").toLowerCase();
  if (layer.includes("semantic_cloud")) return "cloud_brain";
  if (layer.includes("graph_cartridge")) return "cloud_fragment";
  if (layer.includes("cloud_attached") || layer.includes("working_memory_cloud")) return "working_memory";
  if (layer.includes("surface")) return "representative_sample";
  if (layer.includes("seed")) return "seed_schema";
  if (layer.includes("base")) return "evidence_source";
  return String(node.source_scope ?? "").toLowerCase() === "cloud" ? "cloud_brain" : "local_memory";
}

function buildBrainLayerGraph3D(rawGraph: AnyRecord | null | undefined): Rag3DGraph {
  const rawNodes = Array.isArray(rawGraph?.nodes) ? rawGraph.nodes as AnyRecord[] : [];
  const rawEdges = Array.isArray(rawGraph?.edges) ? rawGraph.edges as AnyRecord[] : [];
  if (!rawNodes.length) return { nodes: [], edges: [], traversal_path: [] };

  const idByLayerAndRawId = new Map<string, string>();
  const ids = new Set<string>();
  const nodes: Rag3DNode[] = rawNodes.map((node, index) => {
    const layer = String(node.layer ?? "graph");
    const rawId = String(node.id ?? `${layer}:${index}`);
    const id = `${layer}:${rawId}`;
    idByLayerAndRawId.set(`${layer}:${rawId}`, id);
    ids.add(id);
    const fallbackTheta = index * 2.399963229728653;
    const fallbackRadius = 1.8 + ((stableUnit(rawId, 271) + 1) / 2) * 1.4;
    const hasSourcePosition = Number.isFinite(Number(node.x)) && Number.isFinite(Number(node.y)) && Number.isFinite(Number(node.z));
    return {
      id,
      label: String(node.label ?? rawId),
      type: String(node.kind ?? node.type ?? layer),
      x: hasSourcePosition ? Number(node.x) * 2.8 : Math.cos(fallbackTheta) * fallbackRadius,
      y: hasSourcePosition ? Number(node.y) * 2.8 : Math.sin(fallbackTheta) * fallbackRadius * 0.72,
      z: hasSourcePosition ? Number(node.z) * 2.8 : stableUnit(rawId, 277) * 2.2,
      confidence: Number(node.weight ?? node.confidence ?? 0.78),
      source_type: brainGraphLayerSourceType(node),
      cluster_id: layer,
    };
  });

  const edges: Rag3DEdge[] = rawEdges.flatMap((edge) => {
    const layer = String(edge.layer ?? "graph");
    const source = idByLayerAndRawId.get(`${layer}:${String(edge.source ?? "")}`)
      ?? idByLayerAndRawId.get(`semantic_cloud:${String(edge.source ?? "")}`)
      ?? idByLayerAndRawId.get(`cloud_attached:${String(edge.source ?? "")}`)
      ?? String(edge.source ?? "");
    const target = idByLayerAndRawId.get(`${layer}:${String(edge.target ?? "")}`)
      ?? idByLayerAndRawId.get(`semantic_cloud:${String(edge.target ?? "")}`)
      ?? idByLayerAndRawId.get(`cloud_attached:${String(edge.target ?? "")}`)
      ?? String(edge.target ?? "");
    if (!ids.has(source) || !ids.has(target)) return [];
    return [{
      source,
      target,
      relation: String(edge.relation ?? "relates_to"),
      weight: Number(edge.weight ?? edge.confidence ?? 0.7),
      source_type: layer,
    }];
  });

  return {
    nodes,
    edges,
    traversal_path: nodes.slice(0, 32).map((node) => node.id),
  };
}

function graphPayloadNodeCount(rawGraph: AnyRecord | null | undefined) {
  return Array.isArray(rawGraph?.nodes) ? rawGraph.nodes.length : 0;
}

function keepNonEmptyGraph(current: AnyRecord | null, next: AnyRecord | null) {
  if (!next) return current;
  if (graphPayloadNodeCount(next) === 0 && graphPayloadNodeCount(current) > 0) return current;
  return next;
}

const stateLabels: Record<string, string> = {
  idle: "대기",
  running: "진행 중",
  completed: "완료",
  complete: "완료",
  failed: "실패",
  warning: "경고",
  ready: "준비",
  waiting: "대기",
  resume_needed: "재개 필요",
};

const fallbackMemoryColors = ["#ff6b35", "#006a9f", "#8c3fa7", "#22936f", "#c5283d", "#e89d2a", "#4a8fdb"];

const traceStepLabels: Record<string, string> = {
  Harvest: "자료 수집",
  DataGate: "DataGate 정제",
  "Ontology Forge": "온톨로지 생성",
  GraphRAG: "GraphRAG 경로",
  "ATANOR Oven": "학습 게이트",
};

const sourceTypeLabels: Record<string, string> = {
  discussion: "토론 자료",
  repository_or_docs: "저장소/문서",
};

const sourceStatusLabels: Record<string, string> = {
  fetched: "수집 완료",
  fallback: "대체 요약",
};

const licenseStatusLabels: Record<string, string> = {
  reference_only: "참조 전용",
};

const memoryTypeLabels: Record<string, string> = {
  concept: "개념",
  source: "자료",
  critique: "비평",
  ontology: "온톨로지",
  retrieval: "검색",
  visualization: "시각화",
  guardrail: "가드레일",
  training: "학습",
  quality: "품질",
  memory: "메모리",
  verification: "검증",
  learning: "학습",
  efficiency: "효율",
  keyword: "키워드",
  heading: "제목",
  verb: "행위",
  phrase: "구",
  relation: "관계",
};

const memoryTypeColors: Record<string, string> = {
  source: "#ff6b35",
  critique: "#c5283d",
  ontology: "#1a936f",
  retrieval: "#006a9f",
  visualization: "#8c3fa7",
  guardrail: "#e89d2a",
  training: "#111715",
  concept: "#22936f",
  keyword: "#4a8fdb",
  heading: "#7b8794",
  verb: "#f97316",
  phrase: "#7c3aed",
  relation: "#0f766e",
  quality: "#3f6f5f",
  memory: "#1a936f",
  verification: "#e89d2a",
  learning: "#111715",
  efficiency: "#006a9f",
  // Graph Hub cartridges + cloud overlay — visually distinct from base/local nodes.
  graph_cartridge_node: "#e0338a",
  graph_cartridge: "#e0338a",
  cloud_attached: "#00b4d8",
  // Brain Link P2P compute-share topology.
  brain_link_self: "#0ea5a4",
  brain_link_peer: "#6366f1",
};

const memoryTypeDescriptions: Record<string, string> = {
  source: "웹과 문서에서 수집한 원문 자료와 근거 청크입니다.",
  critique: "품질 문제, 반례, 경계 조건처럼 학습을 조절하는 신호입니다.",
  ontology: "개념 사이의 관계를 묶는 온톨로지 메모리입니다.",
  retrieval: "질문을 근거 문서와 그래프 경로로 연결하는 검색 노드입니다.",
  visualization: "현재 학습 상태를 화면에 표시하는 시각화 노드입니다.",
  guardrail: "답변의 과장, 생략, 근거 부족을 검증하는 안전 노드입니다.",
  training: "ATANOR Oven으로 이어지는 학습 및 압축 신호입니다.",
  concept: "문서에서 추출한 핵심 개념 노드입니다.",
  keyword: "검색과 관계 확장에 쓰이는 키워드 기억입니다.",
  heading: "문서 구조와 섹션 제목에서 온 문맥 앵커입니다.",
  verb: "문장에서 추출한 행위 또는 동작 신호입니다.",
  phrase: "인접 단어가 함께 만든 짧은 문장 요소입니다.",
  relation: "공출현, 행위, 대상 사이에서 측정한 관계 신호입니다.",
  quality: "DataGate가 판단한 품질 게이트 신호입니다.",
  memory: "장기 온톨로지 메모리의 저장 영역입니다.",
  verification: "근거 확인과 검증에 쓰이는 노드입니다.",
  learning: "실시간 학습 과정과 연결되는 노드입니다.",
  efficiency: "저전력 및 저사양 실행을 위한 효율 노드입니다.",
  graph_cartridge_node: "Graph Hub에서 꽂은 전문·페르소나 그래프 카트리지 노드입니다.",
  graph_cartridge: "Graph Hub에서 꽂은 전문·페르소나 그래프 카트리지 노드입니다.",
  cloud_attached: "클라우드에서 임시로 부착된 작업기억 오버레이 노드입니다.",
  brain_link_self: "Brain Link에서 내 노드(유휴 연산을 공유하는 이 기기)입니다.",
  brain_link_peer: "Brain Link P2P 풀의 상대 피어입니다 (신뢰·사생활 게이트로 연산 공유 여부 결정).",
};

// Without a timeout a slow/wedged backend leaves the browser fetch pending forever, and
// since browsers cap concurrent connections per host (~6 over HTTP/1.1) a handful of stuck
// polls permanently starve the pool — every later click (e.g. opening Graph Hub) then hangs
// and its panel renders empty. A bounded timeout aborts the stuck request, frees the socket,
// and lets the caller's catch/retry recover. Generous default so real slow answers aren't cut.
const DEFAULT_FETCH_TIMEOUT_MS = 15000;

async function fetchWithTimeout(input: string, init?: RequestInit, timeoutMs = DEFAULT_FETCH_TIMEOUT_MS): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new DOMException("timeout", "AbortError")), timeoutMs);
  const outerSignal = init?.signal;
  if (outerSignal) {
    if (outerSignal.aborted) controller.abort(outerSignal.reason);
    else outerSignal.addEventListener("abort", () => controller.abort(outerSignal.reason), { once: true });
  }
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function fetchJson<T>(path: string, init?: RequestInit, timeoutMs?: number): Promise<T> {
  const response = await fetchWithTimeout(path, {
    ...init,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  }, timeoutMs);
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.detail ?? body.error ?? `API returned ${response.status}`);
  }
  return body;
}

function normalizeLocalBackendUrl(value: string) {
  const trimmed = value.trim().replace(/\/+$/, "");
  return trimmed || "http://127.0.0.1:8502";
}

function edgeStatusApiPath(baseUrl: string) {
  return `/api/network/edge/status?backend=${encodeURIComponent(normalizeLocalBackendUrl(baseUrl))}`;
}

function edgeAdvertiseApiPath(baseUrl: string) {
  return `/api/network/edge/advertise?backend=${encodeURIComponent(normalizeLocalBackendUrl(baseUrl))}`;
}

const EMPTY_STRING_ARRAY: string[] = [];

function brainGraphApiPath(
  view: "local" | "cloud",
  layers?: string[],
  profile: "fast" | "full" = "fast",
  options?: { focusNodeId?: string | null; lod?: number | null },
) {
  const layerParam = layers && layers.length > 0 ? `&layers=${layers.join(",")}` : "";
  const limits = view === "cloud"
    ? (profile === "full" ? { nodes: 1200, edges: 30000 } : { nodes: 1200, edges: 30000 })
    : (profile === "full" ? { nodes: 5000, edges: 10000 } : { nodes: 1200, edges: 2400 });
  const focusParam = options?.focusNodeId ? `&focus_node_id=${encodeURIComponent(options.focusNodeId)}` : "";
  const lodParam = options?.lod ? `&lod=${encodeURIComponent(String(options.lod))}` : "";
  return `/api/brain/graph?view=${view}${layerParam}&max_nodes=${limits.nodes}&max_edges=${limits.edges}${focusParam}${lodParam}`;
}

function graphStreamApiPath(baseUrl: string, limit = 1200) {
  return `/api/graph/stream?backend=${encodeURIComponent(normalizeLocalBackendUrl(baseUrl))}&limit=${encodeURIComponent(String(limit))}&include_cloud_attached=true`;
}

function readBrowserStorage(key: string) {
  try {
    if (typeof window === "undefined" || !window.localStorage) return null;
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeBrowserStorage(key: string, value: string) {
  try {
    if (typeof window !== "undefined" && window.localStorage) {
      window.localStorage.setItem(key, value);
    }
  } catch {
    // Storage can be unavailable in embedded browser sandboxes.
  }
}

function removeBrowserStorage(key: string) {
  try {
    if (typeof window !== "undefined" && window.localStorage) {
      window.localStorage.removeItem(key);
    }
  } catch {
    // Storage can be unavailable in embedded browser sandboxes.
  }
}

function localBackendErrorMessage(baseUrl: string, caught: unknown) {
  const message = caught instanceof Error ? caught.message : "로컬 FastAPI 응답 실패";
  if (typeof window !== "undefined" && window.location.protocol === "https:" && normalizeLocalBackendUrl(baseUrl).startsWith("http://")) {
    return "HTTPS 배포본에서는 브라우저가 HTTP 로컬 FastAPI를 차단할 수 있습니다. 로컬 웹과 FastAPI를 함께 실행하거나 HTTPS 로컬 companion을 사용하세요.";
  }
  return message;
}

function localBackendDisplayMessage(message: string, status: "idle" | "checking" | "connected" | "failed", language: Language) {
  if (language === "ko") return message;
  if (status === "checking") return "Syncing Local Brain";
  if (status === "connected") return "Local Brain connected";
  if (status === "idle") return "Using bundled fallback";
  if (message.includes("HTTPS") || message.includes("HTTP")) {
    return "This browser may block an HTTP Local FastAPI companion from an HTTPS deployment. Run the local web app and FastAPI together, or use an HTTPS local companion.";
  }
  return "Local FastAPI did not respond";
}

async function directBackendJson<T>(baseUrl: string, path: string, init?: RequestInit, timeoutMs?: number): Promise<T> {
  const headers = new Headers(init?.headers ?? undefined);
  const method = init?.method?.toUpperCase() ?? "GET";
  if ((init?.body || method !== "GET") && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetchWithTimeout(`${normalizeLocalBackendUrl(baseUrl)}${path}`, {
    ...init,
    cache: "no-store",
    headers,
  }, timeoutMs);
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.detail ?? body.error ?? `Local FastAPI returned ${response.status}`);
  }
  return body;
}

function ghHash(value: string): number {
  let h = 2166136261;
  for (let i = 0; i < value.length; i += 1) {
    h ^= value.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

// Theme-matched palette. Node color encodes its REAL semantic domain / cluster (consistent
// per domain), so a multi-domain fragment reads as a colorful but meaningful constellation
// rather than a monochrome blob. ATANOR orange leads; sky-blue/violet/teal/rose fill it out.
const GH_PALETTE = ["#ff9f1c", "#4da3ff", "#b07bff", "#3dd6a0", "#ff6b9d", "#ffd166", "#22d3ee", "#f97316", "#7c9bff"];

function ghNodeColorHex(node: AnyRecord, index: number): string {
  const key = String(node.planetary_domain ?? node.cluster_id ?? node.onion_layer ?? node.id ?? node.label ?? index);
  return GH_PALETTE[ghHash(key) % GH_PALETTE.length];
}

// Renders a cartridge's REAL graph fragment (nodes from /sandbox-preview) as a small
// constellation: nodes at their stored x/y when present (else a deterministic per-id layout),
// linked where they share a planetary domain / cluster (real structure), else to the nearest
// node so the shape reads as a graph rather than scattered dots.
function GraphHubFragmentThumb({ nodes }: { nodes: AnyRecord[] }) {
  const W = 100;
  const H = 100;
  const pad = 14;
  const picked = nodes.slice(0, 16);
  const raw = picked.map((n, i) => {
    const hasXY = typeof n.x === "number" && typeof n.y === "number";
    let px: number;
    let py: number;
    if (hasXY) {
      px = Number(n.x);
      py = Number(n.y);
    } else {
      const h = ghHash(String(n.id ?? n.label ?? i));
      const ang = (h % 360) * (Math.PI / 180);
      const rad = 0.35 + (((h >> 4) % 100) / 100) * 0.6;
      px = Math.cos(ang) * rad;
      py = Math.sin(ang) * rad;
    }
    return {
      px,
      py,
      domain: String(n.planetary_domain ?? n.cluster_id ?? ""),
      layer: String(n.onion_layer ?? ""),
      trust: Number(n.trust ?? n.confidence ?? 0.6),
    };
  });
  const xs = raw.map((p) => p.px);
  const ys = raw.map((p) => p.py);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const nx = (v: number) => pad + (maxX > minX ? (v - minX) / (maxX - minX) : 0.5) * (W - 2 * pad);
  const ny = (v: number) => pad + (maxY > minY ? (v - minY) / (maxY - minY) : 0.5) * (H - 2 * pad);
  const laid = raw.map((p) => ({ ...p, cx: nx(p.px), cy: ny(p.py) }));
  const edges: Array<[number, number]> = [];
  for (let i = 0; i < laid.length; i += 1) {
    let linked = false;
    for (let j = i + 1; j < laid.length; j += 1) {
      if (laid[i].domain && laid[i].domain === laid[j].domain) {
        edges.push([i, j]);
        linked = true;
      }
    }
    if (!linked && laid.length > 1) {
      let best = -1;
      let bd = Infinity;
      for (let j = 0; j < laid.length; j += 1) {
        if (j === i) continue;
        const d = (laid[i].cx - laid[j].cx) ** 2 + (laid[i].cy - laid[j].cy) ** 2;
        if (d < bd) {
          bd = d;
          best = j;
        }
      }
      if (best >= 0) edges.push([i, best]);
    }
  }
  const cappedEdges = edges.slice(0, 26);
  return (
    <svg className="atanor-graph-hub-fragment" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet" aria-hidden="true">
      <g stroke="rgba(255,255,255,0.34)" strokeWidth={0.7}>
        {cappedEdges.map(([a, b], k) => (
          <line key={k} x1={laid[a].cx} y1={laid[a].cy} x2={laid[b].cx} y2={laid[b].cy} />
        ))}
      </g>
      {laid.map((p, i) => (
        <circle
          key={i}
          cx={p.cx}
          cy={p.cy}
          r={2.1 + Math.min(1.8, p.trust * 2)}
          fill={GH_PALETTE[ghHash(p.domain || p.layer || String(i)) % GH_PALETTE.length]}
          opacity={0.55 + Math.min(0.4, p.trust * 0.5)}
        />
      ))}
    </svg>
  );
}

// Shared offscreen Three.js renderer. Each cartridge's REAL node cloud is rendered once (in
// the same additive glowing-points-on-black style as the live Local/Cloud Brain scenes) and
// captured as a PNG — one reused WebGL context instead of many live canvases.
let _ghThree: any = null;
let _ghRenderer: any = null;
let _ghDotTex: any = null;

// Soft round glow sprite so points read as luminous nodes (not square dots), matching the
// additive look of the brain scenes.
function ghDotTexture(THREE: any): any {
  if (_ghDotTex) return _ghDotTex;
  const c = document.createElement("canvas");
  c.width = 64;
  c.height = 64;
  const ctx = c.getContext("2d")!;
  const g = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
  g.addColorStop(0, "rgba(255,255,255,1)");
  g.addColorStop(0.25, "rgba(255,255,255,0.9)");
  g.addColorStop(0.55, "rgba(255,255,255,0.32)");
  g.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 64, 64);
  _ghDotTex = new THREE.CanvasTexture(c);
  return _ghDotTex;
}

// Fibonacci-sphere point (same distribution the Cloud Brain shell uses).
function ghShellPoint(THREE: any, index: number, total: number, radius: number): any {
  const golden = Math.PI * (3 - Math.sqrt(5));
  const y = 1 - (index / Math.max(1, total - 1)) * 2;
  const r = Math.sqrt(Math.max(0, 1 - y * y));
  const theta = golden * index;
  return new THREE.Vector3(Math.cos(theta) * r * radius, y * radius, Math.sin(theta) * r * radius);
}

async function graphHubSnapshot(nodes: AnyRecord[]): Promise<string | null> {
  if (typeof window === "undefined" || !nodes.length) return null;
  try {
    if (!_ghThree) _ghThree = await import("three");
    const THREE = _ghThree;
    const SIZE = 420;
    if (!_ghRenderer) {
      _ghRenderer = new THREE.WebGLRenderer({ alpha: false, antialias: true, preserveDrawingBuffer: true });
      _ghRenderer.setSize(SIZE, SIZE);
      _ghRenderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    }
    const renderer = _ghRenderer;
    renderer.setClearColor(0x04060d, 1); // black backdrop for the additive glow
    const dot = ghDotTexture(THREE);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 200);
    const list = nodes.slice(0, 48);
    const pts = list.map((n: AnyRecord, i: number) => {
      if (typeof n.x === "number" && typeof n.y === "number") {
        return new THREE.Vector3(Number(n.x), Number(n.y), Number(n.z ?? 0));
      }
      const h = ghHash(String(n.id ?? n.label ?? i));
      const theta = (h % 360) * (Math.PI / 180);
      const phi = (((h >> 4) % 180) + 10) * (Math.PI / 180);
      const r = 2 + (((h >> 8) % 100) / 100) * 2.4;
      return new THREE.Vector3(r * Math.sin(phi) * Math.cos(theta), r * Math.cos(phi), r * Math.sin(phi) * Math.sin(theta));
    });
    const box = new THREE.Box3().setFromPoints(pts);
    const center = box.getCenter(new THREE.Vector3());
    pts.forEach((p: any) => p.sub(center));
    const radius = Math.max(1.3, box.getSize(new THREE.Vector3()).length() / 2);
    const disposables: any[] = [];

    // Dense spherical shell of ambient points → the "brain cluster" backdrop. We fill both a
    // surface shell and a thinner inner scatter so even a small cartridge reads as a populated
    // cluster (like the real Cloud Brain sphere), with its real nodes highlighted on top.
    const shellR = radius * 1.25 + 0.85;
    const shellCount = Math.min(1600, 900 + list.length * 40);
    const shellPos = new Float32Array(shellCount * 3);
    for (let i = 0; i < shellCount; i += 1) {
      const h = ghHash(String(i * 2 + 1));
      // ~70% on the surface shell, ~30% scattered inside for volume.
      const rr = (h % 100) < 70 ? shellR * (0.9 + ((h >> 3) % 100) / 100 * 0.14) : shellR * (0.3 + ((h >> 5) % 100) / 100 * 0.55);
      const p = ghShellPoint(THREE, i, shellCount, rr);
      shellPos[i * 3] = p.x;
      shellPos[i * 3 + 1] = p.y;
      shellPos[i * 3 + 2] = p.z;
    }
    const shellGeo = new THREE.BufferGeometry();
    shellGeo.setAttribute("position", new THREE.BufferAttribute(shellPos, 3));
    const shellMat = new THREE.PointsMaterial({
      color: new THREE.Color("#4c83b8"),
      map: dot,
      size: radius * 0.1,
      opacity: 0.62,
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      sizeAttenuation: true,
    });
    disposables.push(shellGeo, shellMat);
    scene.add(new THREE.Points(shellGeo, shellMat));

    // Edges between same-domain nodes → additive near-white filaments.
    const linePos: number[] = [];
    for (let i = 0; i < pts.length; i += 1) {
      for (let j = i + 1; j < pts.length; j += 1) {
        const di = String(list[i].planetary_domain ?? list[i].cluster_id ?? "");
        const dj = String(list[j].planetary_domain ?? list[j].cluster_id ?? "");
        if (di && di === dj) linePos.push(pts[i].x, pts[i].y, pts[i].z, pts[j].x, pts[j].y, pts[j].z);
      }
    }
    // Fallback for cartridges whose preview carries no domain/cluster (e.g. operator-authored
    // cartridges): connect each node to its nearest neighbour so it still reads as a graph
    // rather than scattered dots.
    if (!linePos.length && pts.length > 1) {
      for (let i = 0; i < pts.length; i += 1) {
        let best = -1;
        let bd = Infinity;
        for (let j = 0; j < pts.length; j += 1) {
          if (j === i) continue;
          const d = pts[i].distanceToSquared(pts[j]);
          if (d < bd) {
            bd = d;
            best = j;
          }
        }
        if (best > i) linePos.push(pts[i].x, pts[i].y, pts[i].z, pts[best].x, pts[best].y, pts[best].z);
      }
    }
    if (linePos.length) {
      const lg = new THREE.BufferGeometry();
      lg.setAttribute("position", new THREE.Float32BufferAttribute(linePos, 3));
      const lm = new THREE.LineBasicMaterial({ color: 0xdce8ff, transparent: true, opacity: 0.32, blending: THREE.AdditiveBlending });
      disposables.push(lg, lm);
      scene.add(new THREE.LineSegments(lg, lm));
    }

    // A soft halo pass under the real nodes for bloom-like depth.
    const nodePos = new Float32Array(list.length * 3);
    const nodeCol = new Float32Array(list.length * 3);
    list.forEach((n: AnyRecord, i: number) => {
      nodePos[i * 3] = pts[i].x;
      nodePos[i * 3 + 1] = pts[i].y;
      nodePos[i * 3 + 2] = pts[i].z;
      const c = new THREE.Color(ghNodeColorHex(n, i));
      nodeCol[i * 3] = c.r;
      nodeCol[i * 3 + 1] = c.g;
      nodeCol[i * 3 + 2] = c.b;
    });
    const nodeGeo = new THREE.BufferGeometry();
    nodeGeo.setAttribute("position", new THREE.BufferAttribute(nodePos, 3));
    nodeGeo.setAttribute("color", new THREE.BufferAttribute(nodeCol, 3));
    const haloMat = new THREE.PointsMaterial({
      vertexColors: true,
      map: dot,
      size: radius * 0.66,
      opacity: 0.5,
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      sizeAttenuation: true,
    });
    const coreMat = new THREE.PointsMaterial({
      vertexColors: true,
      map: dot,
      size: radius * 0.3,
      opacity: 1,
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      sizeAttenuation: true,
    });
    disposables.push(nodeGeo, haloMat, coreMat);
    scene.add(new THREE.Points(nodeGeo, haloMat));
    scene.add(new THREE.Points(nodeGeo, coreMat));

    const dist = radius * 3.3 + shellR * 0.35;
    camera.position.set(dist * 0.42, dist * 0.3, dist);
    camera.lookAt(0, 0, 0);
    renderer.render(scene, camera);
    const url = renderer.domElement.toDataURL("image/png");
    disposables.forEach((d) => d.dispose && d.dispose());
    return url;
  } catch {
    return null;
  }
}

function percent(part: number, total: number) {
  return total > 0 ? Math.round((part / total) * 100) : 0;
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function asPercent(value?: number | null) {
  return Math.round((value ?? 0) * 100);
}

function stabilityPayloadForVolume(volume: LearningVolume, targetNodeCount?: number, hardwareProfile?: AnyRecord | null) {
  const preset = learningVolumePresets[volume];
  const targetNodes = clamp(Math.round(targetNodeCount ?? defaultTargetNodesForVolume(volume)), 100, maxTargetNodes);
  return {
    ...(hardwareProfile ? { hardware_profile: hardwareProfile } : {}),
    target_nodes: targetNodes,
    target_edges: Math.max(targetNodes + 1, Math.round(targetNodes * preset.edgeRatio)),
    duration_hours: preset.durationHours,
  };
}

function isRealTelemetrySource(system?: AnyRecord | null, benchmark?: AnyRecord | null) {
  const source = String(system?.source ?? "");
  return Boolean(benchmark?.can_read_local_hardware) || source === "local-fastapi" || source === "local-next";
}

function telemetrySourceText(system?: AnyRecord | null, benchmark?: AnyRecord | null) {
  if (benchmark?.can_read_local_hardware || system?.source === "local-fastapi") return "실제 PC 측정";
  if (system?.source === "local-next") return "로컬 Next 측정";
  if (system?.source === "deployment-sandbox") return "배포 샌드박스";
  return "측정 대기";
}

function numeric(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

// HARD resource limits only — these PAUSE compute sharing (and auto-resume: the
// reason is re-derived on every telemetry refresh, so it clears by itself). Soft
// pressure must NOT block sharing — that made Brain Link read as "용량 부족이라 공유
// 불가" whenever the PC was merely busy. Copy is user-facing: what's happening and
// that it resumes on its own — no watermark jargon.
function resourcePressureReason(system?: AnyRecord | null, gpu?: AnyRecord | null, stability?: AnyRecord | null, benchmark?: AnyRecord | null) {
  if (!isRealTelemetrySource(system, benchmark)) return null;
  const ramHard = numeric(stability?.runtime_envelope?.ram_hard_gb);
  const ramUsed = numeric(system?.ram_used_gb);
  if (ramHard !== null && ramUsed !== null && ramUsed >= ramHard) {
    return `메모리가 거의 가득 차서(${ramUsed.toFixed(1)}GB 사용 중) 연산 공유를 잠시 쉬고 있어요.`;
  }
  const vramHard = numeric(stability?.runtime_envelope?.vram_hard_gb);
  const vramUsedMb = numeric(gpu?.vram_used);
  const vramUsed = vramUsedMb === null ? null : vramUsedMb / 1024;
  if (gpu?.available && vramHard !== null && vramUsed !== null && vramUsed >= vramHard) {
    return `그래픽 메모리가 가득 차서(${vramUsed.toFixed(1)}GB 사용 중) 연산 공유를 잠시 쉬고 있어요.`;
  }
  // Disk: warn only on a REAL positive reading below the SOFT minimum (30–50GB).
  // The 20% "desired growth reserve" is aspirational — the API itself says normal
  // operation is safe below it — and a 0/null reading means telemetry is absent,
  // not an empty disk, so neither may raise the red banner.
  const diskFree = numeric(system?.disk_free_gb);
  const softMinFree = numeric(stability?.runtime_envelope?.disk_budget?.soft_min_free_gb);
  if (diskFree !== null && diskFree > 0 && softMinFree !== null && diskFree <= softMinFree) {
    return `저장 공간 여유가 ${diskFree.toFixed(1)}GB뿐이라 연산 공유를 잠시 쉬고 있어요.`;
  }
  return null;
}

// SOFT pressure — informational only: sharing keeps running, the machine is just
// busy, so the UI says contribution may slow down instead of blocking it.
function resourceSoftNotice(system?: AnyRecord | null, gpu?: AnyRecord | null, stability?: AnyRecord | null, benchmark?: AnyRecord | null) {
  if (!isRealTelemetrySource(system, benchmark)) return null;
  const ramSoft = numeric(stability?.runtime_envelope?.ram_soft_gb);
  const ramUsed = numeric(system?.ram_used_gb);
  const ramPercent = numeric(system?.ram_used_percent);
  if (ramSoft !== null && ramUsed !== null && ramUsed >= ramSoft && ramPercent !== null && ramPercent >= 88) {
    return "지금 PC가 바빠서 연산 공유가 느려질 수 있어요. 공유는 계속 켜져 있습니다.";
  }
  const vramSoft = numeric(stability?.runtime_envelope?.vram_soft_gb);
  const vramUsedMb = numeric(gpu?.vram_used);
  const vramUsed = vramUsedMb === null ? null : vramUsedMb / 1024;
  if (gpu?.available && vramSoft !== null && vramUsed !== null && vramUsed >= vramSoft && Number(gpu?.utilization ?? 0) >= 92) {
    return "그래픽카드가 바빠서 연산 공유가 느려질 수 있어요. 공유는 계속 켜져 있습니다.";
  }
  return null;
}

function statusText(state?: string) {
  return stateLabels[state ?? "idle"] ?? state ?? "대기";
}

function traceStepText(step?: string) {
  return traceStepLabels[step ?? ""] ?? step ?? "단계";
}

function sourceTypeText(type?: string) {
  return sourceTypeLabels[type ?? ""] ?? type ?? "출처";
}

function sourceStatusText(status?: string) {
  return sourceStatusLabels[status ?? ""] ?? status ?? "상태 미확인";
}

function licenseStatusText(status?: string) {
  return licenseStatusLabels[status ?? ""] ?? status ?? "라이선스 미확인";
}

function memoryTypeText(type?: string) {
  return memoryTypeLabels[type ?? ""] ?? type ?? "기억";
}

function memoryTypeColor(type?: string, fallbackIndex = 0) {
  return memoryTypeColors[type ?? ""] ?? fallbackMemoryColors[fallbackIndex % fallbackMemoryColors.length];
}

function memoryTypeDescription(type?: string) {
  return memoryTypeDescriptions[type ?? ""] ?? "현재 그래프에서 관찰된 사용자 정의 기억 노드입니다.";
}

function evidenceSignalText(doc: AnyRecord) {
  const signals = doc.retrieval_signals;
  if (!signals) return "";
  if (signals.web_search) return ` / 웹 ${signals.provider ?? "search"}`;
  const lexical = signals.lexical ?? "-";
  const graphBoost = signals.graph_boost ?? "-";
  return ` / 어휘 ${lexical} / 그래프 ${graphBoost}`;
}

function buildFrameMessageText(message?: string | null) {
  if (!message) return "수집 그래프를 구성하고 있습니다.";
  if (/output gate/i.test(message)) return "수집 대상 그래프 구성 완료";
  if (/harvest/i.test(message)) return "자료 수집 그래프 구성 중";
  return message;
}

function isNodeInventoryQuestion(query: string) {
  const normalized = query.trim().toLowerCase();
  return /(노드|node|nodes)/i.test(normalized) && /(전체|모두|목록|리스트|말해|알려|보여|보유|있는|list|all|show|inventory|available)/i.test(normalized);
}

function isLegendQuestion(query: string) {
  const normalized = query.trim().toLowerCase();
  const asksColor = /(색깔|색상|컬러|범례|legend|color)/i.test(normalized);
  const asksMeaning = /(의미|뜻|설명|구분|차이|meaning|mean|label)/i.test(normalized);
  const graphContext = /(노드|그래프|rag|온톨로지|메모리|신호|이론|node|graph)/i.test(normalized);
  return asksColor && (asksMeaning || graphContext);
}

function isConversationalQuestion(query: string) {
  const normalized = query.trim().toLowerCase();
  return /^(안녕|안녕하세요|하이|헬로|반가워|고마워|감사|감사합니다|hi|hello|hey|yo|thanks|thank you)[\s!.?]*$/i.test(normalized);
}

function graphInventoryStatus(query: string, graph: Rag3DGraph) {
  const nodes = graph.nodes ?? [];
  const edges = graph.edges ?? [];
  const nodeLines = nodes.map((node, index) => {
    const confidence = node.confidence === undefined ? "" : `, 신뢰도 ${asPercent(node.confidence)}%`;
    return `${index + 1}. ${node.label} (${memoryTypeText(node.type)}, id: ${node.id}${confidence})`;
  });
  const answer = nodes.length
    ? `현재 화면의 온톨로지 메모리에는 ${nodes.length}개 노드와 ${edges.length}개 관계가 있습니다.\n${nodeLines.join("\n")}`
    : "현재 화면에 표시할 온톨로지 메모리 노드가 없습니다. 빌드 시작 또는 메모리 생성을 먼저 실행해 주세요.";

  return {
    state: "completed",
    started_at: new Date().toISOString(),
    finished_at: new Date().toISOString(),
    error: null,
    last_query: query,
    confidence: nodes.length ? 0.99 : 0.2,
    result: {
      query,
      method: "atanor-graph-inspection-v1",
      answer,
      matched_nodes: nodes,
      matched_edges: edges,
      evidence_docs: [],
      citations: [],
      graph_paths: edges.slice(0, 12).map((edge) => [edge.source, edge.relation, edge.target]),
      follow_up_questions: ["관계선을 모두 보여줄까요?", "특정 노드의 이웃만 펼쳐볼까요?"],
      retrieval_trace: {
        strategy: "graph inventory intent; retrieval skipped",
        query_terms: query.toLowerCase().split(/\s+/).filter(Boolean),
        expanded_terms: [],
        ranked_chunk_ids: [],
        matched_node_ids: nodes.map((node) => node.id),
      },
      answer_kind: "inspection",
      answer_engine: {
        name: "BakeBoard Inspection Router",
        mode: "graph-inspection-control-alpha",
        external_llm: false,
        surface_generation: "disabled",
      },
      confidence: nodes.length ? 0.99 : 0.2,
    },
  };
}

function graphLegendStatus(query: string, graph: Rag3DGraph) {
  const nodes = graph.nodes ?? [];
  const edges = graph.edges ?? [];
  const typeOrder: string[] = [];
  const typeCounts = new Map<string, number>();
  const representativeNodes: Rag3DNode[] = [];
  const seenRepresentatives = new Set<string>();

  nodes.forEach((node) => {
    const type = node.type || "concept";
    typeCounts.set(type, (typeCounts.get(type) ?? 0) + 1);
    if (!typeOrder.includes(type)) typeOrder.push(type);
    if (!seenRepresentatives.has(type)) {
      representativeNodes.push(node);
      seenRepresentatives.add(type);
    }
  });

  const lines = typeOrder.slice(0, 10).map((type) => {
    const count = typeCounts.get(type) ?? 0;
    return `- ${memoryTypeColor(type)} ${memoryTypeText(type)}: ${memoryTypeDescription(type)} 현재 ${count}개`;
  });
  const answer = lines.length
    ? `색깔은 노드의 역할을 나타냅니다. 현재 3D RAG 그래프에서는 다음처럼 읽으면 됩니다.\n${lines.join("\n")}\n\n질문 중 주황색으로 밝게 켜지는 노드는 실제로 활성화된 신호입니다. 기본 색은 역할과 메모리 상태를 구분하기 위한 시각적 표식입니다.`
    : "아직 표시된 노드가 없어 색상 범례를 만들 수 없습니다. 빌드 시작을 누르면 수집 자료가 온톨로지 노드로 바뀌고 타입별 색상이 적용됩니다.";
  const representativeIds = new Set(representativeNodes.map((node) => node.id));
  const matchedEdges = edges.filter((edge) => representativeIds.has(edge.source) || representativeIds.has(edge.target)).slice(0, 12);

  return {
    state: "completed",
    started_at: new Date().toISOString(),
    finished_at: new Date().toISOString(),
    error: null,
    last_query: query,
    confidence: nodes.length ? 0.98 : 0.25,
    result: {
      query,
      method: "atanor-graph-legend-v1",
      answer,
      matched_nodes: representativeNodes,
      matched_edges: matchedEdges,
      evidence_docs: [],
      citations: [],
      graph_paths: matchedEdges.map((edge) => [edge.source, edge.relation, edge.target]),
      follow_up_questions: ["주황색 신호가 어떤 노드를 읽는지 보여줄까요?", "현재 노드 목록을 같이 펼쳐볼까요?"],
      retrieval_trace: {
        strategy: "graph legend intent; retrieval skipped",
        query_terms: query.toLowerCase().split(/\s+/).filter(Boolean),
        expanded_terms: typeOrder,
        ranked_chunk_ids: [],
        matched_node_ids: representativeNodes.map((node) => node.id),
      },
      answer_kind: "inspection",
      answer_engine: {
        name: "BakeBoard Inspection Router",
        mode: "graph-legend-control-alpha",
        external_llm: false,
        surface_generation: "disabled",
      },
      confidence: nodes.length ? 0.98 : 0.25,
    },
  };
}

function shouldUseWebSearchForQuestion(question: string, webSearchEnabled: boolean) {
  if (!webSearchEnabled) return false;
  const normalized = question.trim().toLowerCase();
  if (!normalized) return false;
  const compact = normalized.replace(/[\s!.?,]+/g, "");
  if (["hi", "hello", "hey", "yo", "thanks", "thankyou", "안녕", "안녕하세요", "하이", "고마워", "감사", "감사합니다"].includes(compact)) {
    return false;
  }
  const tokens = normalized.match(/[a-z0-9가-힣-]+/g) ?? [];
  if (tokens.length <= 2 && tokens.some((token) => ["hi", "hello", "hey", "안녕", "안녕하세요", "하이"].includes(token))) {
    return false;
  }
  return true;
}

// A real, non-trivial question that deserves the transcript view (and the orb
// stepping aside) rather than a one-line greeting. Used to auto-open the
// conversation log on the home/orb screen so answers are always visible.
function isSubstantiveQuestion(question: string) {
  const t = question.trim();
  if (t.length < 7) return false;
  if (["hi", "hello", "hey", "yo", "안녕", "안녕하세요", "하이", "고마워", "감사", "감사합니다", "thanks"].includes(t.toLowerCase())) return false;
  return true;
}

function signalTraceForQueryLegacy(query: string, graph: Rag3DGraph, result?: AnyRecord | null) {
  const memoryActiveNodes = (result?.memory_activation?.active_nodes ?? []) as AnyRecord[];
  const memoryActiveEdges = (result?.memory_activation?.active_edges ?? []) as AnyRecord[];
  const memoryNodeIds = new Set(memoryActiveNodes.map((node) => String(node.id ?? "")).filter(Boolean));
  const memoryLabels = memoryActiveNodes
    .map((node) => String(node.label ?? node.id ?? "").toLowerCase())
    .filter(Boolean);
  const resultNodeIds = new Set((result?.matched_nodes ?? []).map((node: AnyRecord) => String(node.id ?? "")));
  const graphPathIds = new Set(
    (result?.graph_paths ?? [])
      .flatMap((path: AnyRecord) => Array.isArray(path) ? [path[0], path[2]] : [])
      .filter(Boolean)
      .map(String),
  );
  const terms = query
    .toLowerCase()
    .split(/[^a-z0-9가-힣-]+/i)
    .filter((term) => term.length > 1);
  const activationTerms = [
    ...terms,
    ...memoryLabels.flatMap((label) => label.split(/[^a-z0-9가-힣]+/i)),
  ].filter((term) => term.length > 1);
  const visibleNodeIds = new Set(graph.nodes.map((node) => node.id));
  const visibleMemoryIds = [...memoryNodeIds].filter((id) => visibleNodeIds.has(id));
  const scored = graph.nodes
    .map((node) => {
      const haystack = `${node.id} ${node.label} ${node.type}`.toLowerCase();
      const termScore = activationTerms.reduce((score, term) => score + (haystack.includes(term) ? 1 : 0), 0);
      const memoryScore = memoryNodeIds.has(node.id) ? 10 : 0;
      const labelScore = memoryLabels.some((label) => label && haystack.includes(label)) ? 7 : 0;
      const resultScore = resultNodeIds.has(node.id) ? 6 : 0;
      const pathScore = graphPathIds.has(node.id) ? 3 : 0;
      return { node, score: termScore + memoryScore + labelScore + resultScore + pathScore };
    })
    .filter((item) => item.score > 0)
    .sort((left, right) => right.score - left.score);
  let activeNodeIds = [...visibleMemoryIds, ...scored.map((item) => item.node.id)]
    .filter((id, index, all) => visibleNodeIds.has(id) && all.indexOf(id) === index)
    .slice(0, 8);
  let retargeted = Boolean(memoryNodeIds.size && !visibleMemoryIds.length && activeNodeIds.length);
  if (!activeNodeIds.length) {
    const recentLiveIds = graph.nodes
      .filter((node) => node.id.startsWith("live-synapse"))
      .slice(-6)
      .map((node) => node.id);
    const traversalIds = (graph.traversal_path ?? [])
      .filter((id) => visibleNodeIds.has(id))
      .slice(-6);
    activeNodeIds = Array.from(new Set([...recentLiveIds, ...traversalIds])).slice(0, 8);
    retargeted = Boolean(memoryNodeIds.size && activeNodeIds.length);
  }
  const activeNodeSet = new Set(activeNodeIds);
  const memoryEdgeKeys = memoryActiveEdges
    .map((edge) => `${edge.source}:${edge.target}`)
    .filter((key) => {
      const [source, target] = key.split(":");
      return activeNodeSet.has(source) && activeNodeSet.has(target);
    });
  const activeEdgeKeys = [
    ...memoryEdgeKeys,
    ...graph.edges
      .filter((edge) => activeNodeSet.has(edge.source) && activeNodeSet.has(edge.target))
      .slice(0, 10)
      .map((edge) => `${edge.source}:${edge.target}`),
  ].filter((key, index, all) => all.indexOf(key) === index).slice(0, 12);
  const labels = activeNodeIds
    .map((id) => graph.nodes.find((node) => node.id === id)?.label ?? id)
    .slice(0, 6);
  const signalText = labels.length
    ? `${retargeted ? "활성 신호(대체 노드)" : "활성 노드"}: ${labels.join(", ")}`
    : "활성 신호 대기";
  return {
    edgeKeys: activeEdgeKeys,
    nodeIds: activeNodeIds,
    text: signalText,
  };
}

function edgeKeyFromParts(source: unknown, target: unknown) {
  if (!source || !target) return "";
  return `${String(source)}:${String(target)}`;
}

function signalTraceForQuery(query: string, graph: Rag3DGraph, result?: AnyRecord | null) {
  const visibleNodeIds = new Set(graph.nodes.map((node) => node.id));
  const visibleEdges = graph.edges;
  const memoryActiveNodes = (result?.memory_activation?.active_nodes ?? []) as AnyRecord[];
  const memoryActiveEdges = (result?.memory_activation?.active_edges ?? []) as AnyRecord[];
  const resultNodeIds = new Set<string>((result?.matched_nodes ?? []).map((node: AnyRecord) => String(node.id ?? "")).filter(Boolean));
  const graphPathIds = new Set<string>(
    (result?.graph_paths ?? [])
      .flatMap((path: AnyRecord) => Array.isArray(path) ? path : [])
      .filter(Boolean)
      .map(String),
  );
  const queryTerms = query
    .toLowerCase()
    .split(/[^a-z0-9가-힣-]+/i)
    .filter((term) => term.length > 1);
  const activeCandidates = new Set<string>();

  for (const node of memoryActiveNodes) {
    const id = String(node.id ?? "");
    if (visibleNodeIds.has(id)) activeCandidates.add(id);
  }
  for (const id of resultNodeIds) {
    if (visibleNodeIds.has(id)) activeCandidates.add(id);
  }
  for (const id of graphPathIds) {
    if (visibleNodeIds.has(id)) activeCandidates.add(id);
  }

  const semanticCloudAttached = Number(result?.compact_trace?.semantic_cloud_graph?.attached_nodes ?? 0);
  if (semanticCloudAttached > 0 && activeCandidates.size < 3) {
    graph.nodes
      .filter((node) => {
        const type = String(node.type ?? "").toLowerCase();
        const id = String(node.id ?? "").toLowerCase();
        return type.includes("cloud") || type.includes("semantic") || id.includes("cloud") || id.includes("semantic");
      })
      .slice(0, Math.max(3, Math.min(semanticCloudAttached, 10)))
      .forEach((node) => activeCandidates.add(node.id));
  }

  if (activeCandidates.size < 3 && queryTerms.length) {
    graph.nodes
      .map((node) => {
        const haystack = `${node.id} ${node.label} ${node.type}`.toLowerCase();
        const score = queryTerms.reduce((total, term) => total + (haystack.includes(term) ? 1 : 0), 0);
        return { id: node.id, score };
      })
      .filter((item) => item.score > 0)
      .sort((left, right) => right.score - left.score)
      .slice(0, 8)
      .forEach((item) => activeCandidates.add(item.id));
  }

  if (!activeCandidates.size) {
    for (const id of (graph.traversal_path ?? []).slice(-8)) {
      if (visibleNodeIds.has(id)) activeCandidates.add(id);
    }
  }

  const activeNodeIds = Array.from(activeCandidates).slice(0, 12);
  const activeNodeSet = new Set(activeNodeIds);
  const explicitMemoryEdgeKeys = memoryActiveEdges
    .map((edge) => edgeKeyFromParts(edge.source, edge.target))
    .filter((key) => {
      const [source, target] = key.split(":");
      return visibleNodeIds.has(source) && visibleNodeIds.has(target);
    });
  const visibleSignalEdges = visibleEdges
    .filter((edge) => activeNodeSet.has(edge.source) || activeNodeSet.has(edge.target))
    .slice(0, 24)
    .map((edge) => `${edge.source}:${edge.target}`);
  const activeEdgeKeys = [...explicitMemoryEdgeKeys, ...visibleSignalEdges]
    .filter((key, index, all) => key && all.indexOf(key) === index)
    .slice(0, 24);
  const labels = activeNodeIds
    .map((id) => graph.nodes.find((node) => node.id === id)?.label ?? id)
    .slice(0, 6);

  return {
    edgeKeys: activeEdgeKeys,
    nodeIds: activeNodeIds,
    text: labels.length ? `활성 노드: ${labels.join(", ")}` : "활성 신호 대기",
  };
}

function fmtClock(date = new Date()) {
  return date.toLocaleTimeString("ko-KR", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function formatDuration(ms: number) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return `${hours}시간 ${String(minutes).padStart(2, "0")}분 ${String(seconds).padStart(2, "0")}초`;
  return `${minutes}분 ${String(seconds).padStart(2, "0")}초`;
}

function LossChart({ losses }: { losses: Array<{ step: number; loss: number }> }) {
  if (!losses?.length) {
    return <div className="chart-empty">학습 dry-run 기록 없음</div>;
  }
  const maxLoss = Math.max(...losses.map((loss) => loss.loss));
  const minLoss = Math.min(...losses.map((loss) => loss.loss));
  const points = losses
    .map((loss, index) => {
      const x = losses.length === 1 ? 0 : (index / (losses.length - 1)) * 100;
      const y = 92 - ((loss.loss - minLoss) / Math.max(0.001, maxLoss - minLoss)) * 76;
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <svg className="loss-chart" viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="학습 손실 곡선">
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="3" vectorEffect="non-scaling-stroke" />
      {losses.map((loss, index) => {
        const x = losses.length === 1 ? 0 : (index / (losses.length - 1)) * 100;
        const y = 92 - ((loss.loss - minLoss) / Math.max(0.001, maxLoss - minLoss)) * 76;
        return <circle key={loss.step} cx={x} cy={y} r="2.3" />;
      })}
    </svg>
  );
}

function StatusDot({ state }: { state?: string }) {
  return (
    <span className="status-indicator" data-state={state ?? "idle"}>
      <span className="status-dot" />
      {statusText(state)}
    </span>
  );
}

function makeMemoryNodes(graph: AnyRecord | null): MemoryNode[] {
  const rawNodes = graph?.nodes?.length
    ? graph.nodes
    : [
        { id: "datagate", label: "DataGate", type: "quality" },
        { id: "ontology", label: "Ontology", type: "memory" },
        { id: "rag", label: "RAG", type: "retrieval" },
        { id: "guardrail", label: "Guardrail", type: "verification" },
        { id: "oven", label: "Oven", type: "learning" },
        { id: "neuro", label: "Neuro-Efficiency", type: "efficiency" },
      ];
  const positions = [
    [52, 18],
    [78, 30],
    [82, 58],
    [60, 78],
    [32, 76],
    [16, 50],
    [25, 24],
    [48, 48],
    [70, 70],
    [36, 38],
    [18, 72],
    [86, 20],
  ];
  return rawNodes.slice(0, 5000).map((node: AnyRecord, index: number) => ({
    id: node.id ?? node.label ?? `node-${index}`,
    label: node.label ?? node.name ?? node.id ?? `Node ${index + 1}`,
    type: node.type ?? node.labels?.[0] ?? "concept",
    confidence: node.confidence ?? 0.72,
    x: positions[index % positions.length][0],
    y: positions[index % positions.length][1],
    color: memoryTypeColor(node.type ?? node.labels?.[0], index),
  }));
}

function makeMemoryEdges(graph: AnyRecord | null, nodes: MemoryNode[]): MemoryEdge[] {
  const nodeIds = new Set(nodes.map((node) => node.id));
  const rawEdges = graph?.edges?.length
    ? graph.edges
    : [
        { source: "datagate", target: "ontology", relation: "cleans_for" },
        { source: "ontology", target: "rag", relation: "grounds" },
        { source: "rag", target: "guardrail", relation: "evidence_for" },
        { source: "oven", target: "neuro", relation: "optimizes" },
        { source: "neuro", target: "rag", relation: "routes" },
      ];
  return rawEdges
    .filter((edge: AnyRecord) => nodeIds.has(edge.source) && nodeIds.has(edge.target))
    .slice(0, 20000)
    .map((edge: AnyRecord, index: number) => ({
      id: `${edge.source}-${edge.target}-${index}`,
      source: edge.source,
      target: edge.target,
      relation: edge.relation ?? edge.name ?? "relates",
      confidence: edge.confidence ?? 0.7,
    }));
}

export default function Page() {
  // Demo and full share the SAME ATANOR frame (sidebar / branding / panels). The
  // demo only swaps the central home: a GPT-style chat instead of the orb. New
  // ATANOR (orb / 3D) ships when complete.
  return <FullApp />;
}

function FullApp() {
  const [layoutMode, setLayoutMode] = useState<LayoutMode>("split");
  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>("lab");
  const [rightMode, setRightMode] = useState<RightMode>("process");
  const [autoChatOpened, setAutoChatOpened] = useState(false);
  const [pipeline, setPipeline] = useState<PipelineStatus | null>(null);
  const [datagate, setDatagate] = useState<AnyRecord | null>(null);
  const [ontology, setOntology] = useState<AnyRecord | null>(null);
  const [graph, setGraph] = useState<AnyRecord | null>(null);
  const [graphrag, setGraphRag] = useState<AnyRecord | null>(null);
  const [guard, setGuard] = useState<AnyRecord | null>(null);
  const [gpu, setGpu] = useState<AnyRecord | null>(null);
  const [system, setSystem] = useState<AnyRecord | null>(null);
  const [oven, setOven] = useState<AnyRecord | null>(null);
  const [neuro, setNeuro] = useState<AnyRecord | null>(null);
  const [stability, setStability] = useState<AnyRecord | null>(null);
  const [memoryStatus, setMemoryStatus] = useState<AnyRecord | null>(null);
  const [memoryDrift, setMemoryDrift] = useState<AnyRecord | null>(null);
  const [learningDaemon, setLearningDaemon] = useState<AnyRecord | null>(null);
  const [edgeStatus, setEdgeStatus] = useState<AnyRecord | null>(defaultEdgeBrokerStatus);
  const [cloudBrainStatus, setCloudBrainStatus] = useState<AnyRecord | null>(null);
  const [cloudBrainSourceInspector, setCloudBrainSourceInspector] = useState<AnyRecord | null>(null);
  const [semanticCloudStatus, setSemanticCloudStatus] = useState<AnyRecord | null>(null);
  const [cloudCandidateStatus, setCloudCandidateStatus] = useState<AnyRecord | null>(null);
  const [semanticGrowthRun, setSemanticGrowthRun] = useState<AnyRecord | null>(null);
  const [semanticAttachResult, setSemanticAttachResult] = useState<AnyRecord | null>(null);
  const [semanticGrowthRunning, setSemanticGrowthRunning] = useState(false);
  const [semanticGrowthError, setSemanticGrowthError] = useState<string | null>(null);
  const [graphHubStatus, setGraphHubStatus] = useState<AnyRecord | null>(null);
  const [graphHubCatalog, setGraphHubCatalog] = useState<AnyRecord[]>([]);
  const [graphHubInstalled, setGraphHubInstalled] = useState<AnyRecord[]>([]);
  const [graphHubAttachments, setGraphHubAttachments] = useState<AnyRecord[]>([]);
  const [graphHubAudit, setGraphHubAudit] = useState<AnyRecord[]>([]);
  const [graphHubExport, setGraphHubExport] = useState<AnyRecord | null>(null);
  const [graphHubProof, setGraphHubProof] = useState<AnyRecord | null>(null);
  // Real graph fragment previews (nodes from /sandbox-preview) rendered as each card's cover.
  const [graphHubPreviews, setGraphHubPreviews] = useState<Record<string, AnyRecord[] | "loading" | "error">>({});
  // PNG snapshots of each cartridge's fragment rendered in real 3D (see graphHubSnapshot).
  const [graphHubSnapshots, setGraphHubSnapshots] = useState<Record<string, string>>({});
  const [graphHubProfiles, setGraphHubProfiles] = useState<Record<string, AnyRecord>>({});
  const [graphHubSynergy, setGraphHubSynergy] = useState<Record<string, AnyRecord>>({});
  const [graphHubTrials, setGraphHubTrials] = useState<Record<string, AnyRecord>>({});
  const [graphHubTrialInputs, setGraphHubTrialInputs] = useState<Record<string, string>>({});
  const [graphHubPricingFilter, setGraphHubPricingFilter] = useState<string>("all");
  const [graphHubCategoryFilter, setGraphHubCategoryFilter] = useState<string>("all");
  const [graphHubTab, setGraphHubTab] = useState<"catalog" | "installed" | "attachments" | "export" | "audit">("catalog");
  const [graphHubSearch, setGraphHubSearch] = useState("");
  const [graphHubRunning, setGraphHubRunning] = useState<string | null>(null);
  const [graphHubError, setGraphHubError] = useState<string | null>(null);
  const [graphHubLoading, setGraphHubLoading] = useState(false);
  const [remoteCloudProof, setRemoteCloudProof] = useState<AnyRecord | null>(null);
  const [remoteCloudProofRunning, setRemoteCloudProofRunning] = useState(false);
  const [remoteCloudProofError, setRemoteCloudProofError] = useState<string | null>(null);
  const [cloudAttachmentStatus, setCloudAttachmentStatus] = useState<AnyRecord | null>(null);
  const [cloudAttachmentRunning, setCloudAttachmentRunning] = useState(false);
  const [cloudAttachmentError, setCloudAttachmentError] = useState<string | null>(null);
  const [brainGraphLocal, setBrainGraphLocal] = useState<AnyRecord | null>(null);
  const [brainGraphCloud, setBrainGraphCloud] = useState<AnyRecord | null>(null);
  const [cloudArrivals, setCloudArrivals] = useState<CloudArrival[]>([]);
  const cloudArrivalPrevRef = useRef<number | null>(null);
  // Shared cloud-brain learning metrics (one app-wide SSE/poll subscription — 난제
  // P4). Drives the cloud arrival flashes + surface arrivals + synapse rate below
  // instead of this page keeping its own duplicate 2.2s poll of the same endpoint.
  const cloudLearnMetrics = useCloudLearningMetrics();
  const [cloudGraphView, setCloudGraphView] = useState<"concept" | "surface">("concept");
  // Render gate for the live activity overlay (new-node orange branches, blue
  // verification flashes, pulses, bloom). OFF = calmer + power-efficient; the
  // engine keeps learning/verifying regardless.
  const [showActivity, setShowActivity] = useState(true);
  const [surfaceGraphData, setSurfaceGraphData] = useState<AnyRecord | null>(null);
  const [surfaceArrivals, setSurfaceArrivals] = useState<CloudArrival[]>([]);
  const surfaceArrivalPrevRef = useRef<number | null>(null);
  const [synapseRate, setSynapseRate] = useState(0);
  const arrivalSeqRef = useRef(0);
  const [brainGraphOverlayStatus, setBrainGraphOverlayStatus] = useState<AnyRecord | null>(null);
  const [brainGraphStatus, setBrainGraphStatus] = useState<AnyRecord | null>(null);
  const [localBrainGraphLayers, setLocalBrainGraphLayers] = useState<string[]>(["local_user", "working_memory_local", "local_base", "seed"]);
  const [cloudBrainGraphLayers, setCloudBrainGraphLayers] = useState<string[]>(["cloud_attached", "working_memory_cloud", "semantic_cloud"]);
  const [cloudDiagnosticsOpen, setCloudDiagnosticsOpen] = useState(false);
  const [controlledGrowthProof, setControlledGrowthProof] = useState<AnyRecord | null>(null);
  const [controlledGrowthRunning, setControlledGrowthRunning] = useState(false);
  const [controlledGrowthError, setControlledGrowthError] = useState<string | null>(null);
  const [cloudSphereStats, setCloudSphereStats] = useState<CloudBrainSphereStats | null>(null);
  const [cortexStatus, setCortexStatus] = useState<AnyRecord | null>(null);
  const [qCortexStatus, setQCortexStatus] = useState<AnyRecord | null>(null);
  const [baseBrainStatus, setBaseBrainStatus] = useState<AnyRecord | null>(null);
  const [baseBrainAnswer, setBaseBrainAnswer] = useState<AnyRecord | null>(null);
  const [baseBrainBenchmark, setBaseBrainBenchmark] = useState<AnyRecord | null>(null);
  const [baseBrainRunning, setBaseBrainRunning] = useState(false);
  const [baseBrainError, setBaseBrainError] = useState<string | null>(null);
  const [baseBrainQuery, setBaseBrainQuery] = useState("쿠버네티스가 뭐야?");
  const [answerQualityStatus, setAnswerQualityStatus] = useState<AnyRecord | null>(null);
  const [answerQualityRun, setAnswerQualityRun] = useState<AnyRecord | null>(null);
  const [answerQualityRunning, setAnswerQualityRunning] = useState(false);
  const [answerQualityError, setAnswerQualityError] = useState<string | null>(null);
  const [answerRepairComparison, setAnswerRepairComparison] = useState<AnyRecord | null>(null);
  const [answerRepairRunning, setAnswerRepairRunning] = useState(false);
  const [answerRepairError, setAnswerRepairError] = useState<string | null>(null);
  const [repairCandidates, setRepairCandidates] = useState<AnyRecord[]>([]);
  const [productionRepairRules, setProductionRepairRules] = useState<AnyRecord[]>([]);
  const [repairAuditEvents, setRepairAuditEvents] = useState<AnyRecord[]>([]);
  const [repairReviewRunning, setRepairReviewRunning] = useState(false);
  const [repairReviewError, setRepairReviewError] = useState<string | null>(null);
  const [brainSyncStatus, setBrainSyncStatus] = useState<AnyRecord | null>(null);
  const [cloudBudgetStatus, setCloudBudgetStatus] = useState<AnyRecord | null>(null);
  const [atlasStatus, setAtlasStatus] = useState<AnyRecord | null>(null);
  const [graphSourceMode, setGraphSourceMode] = useState<"build" | "memory">("memory");
  // Slider re-scaled so its MIDDLE (50%) lands on opacity 0.076 — the dimmer line
  // brightness the old bar gave at ~15%. Range 0.03..0.122.
  const [graphEdgeOpacity, setGraphEdgeOpacity] = useState(0.076);
  const [workbenchInfoOpen, setWorkbenchInfoOpen] = useState(false);
  const [chatInfoOpen, setChatInfoOpen] = useState(false);
  const [webSearchEnabled, setWebSearchEnabled] = useState(true);
  const [benchmark, setBenchmark] = useState<AnyRecord | null>(null);
  const [localBackendUrl, setLocalBackendUrl] = useState("http://127.0.0.1:8502");
  const [localBackendStatus, setLocalBackendStatus] = useState<"idle" | "checking" | "connected" | "failed">("idle");
  const [localBackendMessage, setLocalBackendMessage] = useState("배포 fallback 사용 중");
  const [language, setLanguage] = useState<Language>("en");
  // Demo home (GPT-style chat in place of the orb) = build profile OR ?profile=demo.
  // Persisted to localStorage so a refresh stays in demo even after the app rewrites
  // the URL and drops ?profile.
  const [demoView, setDemoView] = useState<boolean>(isDemo);
  useEffect(() => {
    // The BUILD flag is authoritative: a full local build is full, a demo build (Vercel) is demo.
    // Only an explicit ?profile= toggles it for that load. We deliberately do NOT let a stale
    // localStorage pin the profile — an earlier demo build used to write "demo" here, which kept
    // the full build stuck on the demo home. ?profile still lets you preview the other face.
    let demo = isDemo;
    try {
      const p = new URLSearchParams(window.location.search).get("profile");
      if (p === "demo") demo = true;
      else if (p === "full") demo = false;
      window.localStorage.setItem("atanor.profile", demo ? "demo" : "full");
    } catch {
      /* storage unavailable */
    }
    setDemoView(demo);
  }, []);
  const [mainSection, setMainSection] = useState<MainSectionId>("home");
  // Tracks whether the one-time baseline dashboard refresh has run (see section-gated poll).
  const didInitialAggregateRef = useRef(false);
  const [labSurfaceVisible, setLabSurfaceVisible] = useState(false);
  const [contributionEnabled, setContributionEnabled] = useState(() => readBrowserStorage("atanor.contribution.enabled") === "true");
  const [contributionPaused, setContributionPaused] = useState(false);
  const [contributionSafeMode, setContributionSafeMode] = useState(() => readBrowserStorage("atanor.contribution.safeMode") !== "false");
  const [contributionCpuLimit, setContributionCpuLimit] = useState(() => Number(readBrowserStorage("atanor.contribution.cpuLimit") ?? 20));
  const [contributionGpuLimit, setContributionGpuLimit] = useState(() => Number(readBrowserStorage("atanor.contribution.gpuLimit") ?? 0));
  const [contributionAllowPublic, setContributionAllowPublic] = useState(() => readBrowserStorage("atanor.contribution.publicFragments") !== "false");
  const [contributionChartTick, setContributionChartTick] = useState(0);
  const [contributionStatus, setContributionStatus] = useState<AnyRecord | null>(null);
  const [persistedLearningSeconds, setPersistedLearningSeconds] = useState(0);
  const [learningVolume, setLearningVolume] = useState<LearningVolume>("standard");
  const [targetNodeCount, setTargetNodeCount] = useState<number>(defaultTargetNodesForVolume("standard"));
  const [selectedMemory, setSelectedMemory] = useState<AnyRecord | null>(null);
  const [activeSignalEdgeKeys, setActiveSignalEdgeKeys] = useState<string[]>([]);
  const [activeSignalNodeIds, setActiveSignalNodeIds] = useState<string[]>([]);
  const [signalTraceText, setSignalTraceText] = useState("활성 신호 대기");
  const [isGeneratingAnswer, setIsGeneratingAnswer] = useState(false);
  const [buildRun, setBuildRun] = useState<BuildRun | null>(null);
  const [buildTick, setBuildTick] = useState(0);
  const [isBuilding, setIsBuilding] = useState(false);
  const [continuousLearningActive, setContinuousLearningActive] = useState(false);
  const [learningStartedAt, setLearningStartedAt] = useState<number | null>(null);
  const [learningElapsedMs, setLearningElapsedMs] = useState(0);
  const [clockNow, setClockNow] = useState<Date | null>(null);
  const [activeAction, setActiveAction] = useState<string | null>(null);
  const [labStageProgress, setLabStageProgress] = useState<Record<LabStageKey, number>>({ collect: 0, learn: 0, output: 0 });
  const [activeLabStage, setActiveLabStage] = useState<LabStageKey>("collect");
  const [graphMode] = useState<"2d" | "3d">("3d");
  const [rag3dControl, setRag3dControl] = useState<Rag3DControl>({ serial: 0, action: "reset" });
  const graphRef = useRef<SVGSVGElement | null>(null);
  const chatScrollRef = useRef<HTMLDivElement | null>(null);
  const signalTimerRef = useRef<number | null>(null);
  const progressTimerRef = useRef<number | null>(null);
  const buildFrameTimerRef = useRef<number | null>(null);
  const benchmarkAppliedRef = useRef(false);
  const benchmarkProbeAtRef = useRef(0);
  const [graphView, setGraphView] = useState<GraphView>({ scale: 1, x: 0, y: 0 });
  const [dragState, setDragState] = useState<DragState | null>(null);
  const [atlasRotationDeg, setAtlasRotationDeg] = useState(0);
  const [atlasDragState, setAtlasDragState] = useState<AtlasDragState | null>(null);
  const [memoryQuery, setMemoryQuery] = useState("");
  const [chatInput, setChatInput] = useState(EFFECTIVE_INITIAL_CHAT_PROMPT.en);
  const [draft, setDraft] = useState("GraphRAG는 근거 문서와 지식 그래프 경로를 함께 읽어 답변 근거를 확인합니다.");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      text: EFFECTIVE_INITIAL_ASSISTANT_MESSAGE.en,
    },
  ]);
  const [error, setError] = useState<string | null>(null);
  // Engine reachability: SSE-first (난제 P4 — one push stream instead of polling),
  // falling back to the 20s poll only when the stream cannot be established.
  const [engineDown, setEngineDown] = useState(false);
  const [enginePingNonce, setEnginePingNonce] = useState(0);
  // Engine liveness by HEARTBEAT + GRACE (owner: "항상 로딩되어 있어야 한다" — stop the flapping).
  // The old code flipped the "not connected" banner on the FIRST EventSource error — but SSE errors
  // fire on every transient hiccup (a learner GIL stall, a normal reconnect cycle), so the banner
  // flashed constantly and, during an engine restart, the poll fallback only began after 30s. Now:
  //  * a backup poll starts IMMEDIATELY and every 5s, refreshing a lastAlive heartbeat;
  //  * SSE gives instant liveness, but its errors are IGNORED (it auto-reconnects — the poll covers it);
  //  * "down" is shown ONLY after BOTH signals go silent for GRACE_MS — a single blip never flaps it;
  //  * optimistic start (lastAlive = now) so the UI reads connected instead of a slow "connecting".
  useEffect(() => {
    let stopped = false;
    let lastAlive = Date.now();
    const GRACE_MS = 12000;                 // outlast GIL storms + SSE reconnects before crying "down"
    let es: EventSource | null = null;
    const markAlive = () => { lastAlive = Date.now(); if (!stopped) setEngineDown(false); };

    async function pollOnce() {
      try {
        const r = await fetch("/api/base-brain/status", { cache: "no-store" });
        if (r.ok) markAlive();
      } catch { /* transient — grace + the next poll recover it; a single miss never flaps the banner */ }
    }
    pollOnce();
    const pollTimer = setInterval(pollOnce, 5000);

    try {
      es = new EventSource("http://127.0.0.1:8502/api/status/stream");
      es.onmessage = markAlive;
      es.onopen = markAlive;
      es.onerror = () => { /* reconnecting — do NOT flip the banner; poll + grace carry liveness */ };
    } catch { /* SSE unavailable → the poll is the heartbeat */ }

    const graceTimer = setInterval(() => {
      if (!stopped) setEngineDown(Date.now() - lastAlive > GRACE_MS);
    }, 2000);

    return () => {
      stopped = true;
      clearInterval(pollTimer);
      clearInterval(graceTimer);
      es?.close();
    };
  }, [enginePingNonce]);
  // Conversation-log drawer: collapsed to a button by default; slides open
  // left→right over the render area (ChatGPT-style).
  const [transcriptOpen, setTranscriptOpen] = useState(false);
  const localBackendConnected = localBackendStatus === "connected";
  const localBackendDisplay = localBackendDisplayMessage(localBackendMessage, localBackendStatus, language);

  // WHITE=online / BLACK=local theme (owner 2026-07-12: "색이 곧 상태 — 자연스럽게 전환"). Auto: the
  // dashboard stays light while the cloud engine is reachable and eases to dark (CSS 520ms) when it
  // drops to local/offline, so the color itself tells you where your data lives right now. A settings
  // toggle overrides the auto behavior (cycles auto → light → dark).
  const [themePref, setThemePref] = useState<"auto" | "light" | "dark">("auto");
  useEffect(() => {
    const stored = readBrowserStorage("atanor.theme");
    if (stored === "light" || stored === "dark" || stored === "auto") setThemePref(stored);
  }, []);
  useEffect(() => {
    const resolved = themePref === "auto" ? (engineDown ? "dark" : "light") : themePref;
    if (typeof document !== "undefined") document.documentElement.dataset.theme = resolved;
    writeBrowserStorage("atanor.theme", themePref);
  }, [themePref, engineDown]);

  useEffect(() => {
    writeBrowserStorage("atanor.contribution.enabled", contributionEnabled ? "true" : "false");
    writeBrowserStorage("atanor.contribution.safeMode", contributionSafeMode ? "true" : "false");
    writeBrowserStorage("atanor.contribution.cpuLimit", String(contributionCpuLimit));
    writeBrowserStorage("atanor.contribution.gpuLimit", String(contributionGpuLimit));
    writeBrowserStorage("atanor.contribution.publicFragments", contributionAllowPublic ? "true" : "false");
  }, [contributionAllowPublic, contributionCpuLimit, contributionEnabled, contributionGpuLimit, contributionSafeMode]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.has("api") || params.has("backend")) return;
    const savedUrl = readBrowserStorage("atanor.localFastApiUrl");
    const targetUrl = savedUrl || "http://127.0.0.1:8502";
    const requestedSection = params.get("section");
    const shouldWarmBrainGraph = requestedSection === "home" || requestedSection === "local" || requestedSection === "cloud";
    if (savedUrl) setLocalBackendUrl(savedUrl);
    if (shouldWarmBrainGraph) {
      refreshCloudProofFast().catch(() => undefined);
      refreshBrainGraphPanels().catch(() => undefined);
    }
    const timer = window.setTimeout(() => {
      connectLocalBackend(targetUrl).catch(() => undefined);
    }, shouldWarmBrainGraph ? 500 : 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    const warmupTimers: number[] = [];
    const params = new URLSearchParams(window.location.search);
    const requestedLanguage = params.get("lang") ?? params.get("language");
    const requestedWorkspace = params.get("workspace") ?? params.get("view");
    const requestedSurface = params.get("surface") ?? params.get("mode");
    const labSurfaceRequested = ["lab", "dev", "developer"].includes(requestedWorkspace ?? "") || ["lab", "dev", "developer"].includes(requestedSurface ?? "");
    setLabSurfaceVisible(labSurfaceRequested);
    const initialLanguage = requestedLanguage === "ko" || requestedLanguage === "en"
      ? requestedLanguage
      : "en";
    setLanguage(initialLanguage);
    const requestedSection = params.get("section");
    const requestedTrace = params.get("trace");
    if (requestedTrace) {
      setRequestedTraceLabels(requestedTrace.split(",").map((part) => part.trim()).filter(Boolean).slice(0, 8));
    }
    const sectionIds: MainSectionId[] = ["home", "graph", "local", "cloud", "atlas", "congress", "agent-os", "autonomous", "selfhood", "live-scheduler", "memory-approval", "graphhub", "contribute", "chat", "settings"];
    if (requestedSection && sectionIds.includes(requestedSection as MainSectionId)) {
      const nextSection = requestedSection as MainSectionId;
      if (internalMainSections.has(nextSection) && !labSurfaceRequested) {
        setMainSection("home");
        return;
      }
      setMainSection(nextSection);
      if (nextSection === "atlas") setWorkspaceMode("daemon");
      if (nextSection === "chat") setRightMode("chat");
      if (nextSection === "graph") setLayoutMode("graph");
      if (nextSection === "home" || nextSection === "local" || nextSection === "cloud") {
        refreshCloudProofFast().catch(() => undefined);
        refreshBrainGraphPanels().catch(() => undefined);
        for (let index = 1; index <= 3; index += 1) {
          warmupTimers.push(window.setTimeout(() => {
            refreshCloudProofFast().catch(() => undefined);
            refreshBrainGraphPanels().catch(() => undefined);
          }, index * 1100));
        }
      }
    }
    const savedSeconds = Number(readBrowserStorage("atanor.cumulativeLearningSeconds") ?? "0");
    if (Number.isFinite(savedSeconds) && savedSeconds > 0) {
      setPersistedLearningSeconds(Math.floor(savedSeconds));
    }
    return () => {
      warmupTimers.forEach((timer) => window.clearTimeout(timer));
    };
  }, []);

  useEffect(() => {
    writeBrowserStorage("atanor.uiLanguage", language);
  }, [language]);

  useEffect(() => {
    setChatInput((current) => {
      if (current === EFFECTIVE_INITIAL_CHAT_PROMPT.en || current === EFFECTIVE_INITIAL_CHAT_PROMPT.ko || current === INITIAL_CHAT_PROMPT.en || current === INITIAL_CHAT_PROMPT.ko) {
        return EFFECTIVE_INITIAL_CHAT_PROMPT[language];
      }
      return current;
    });
    setChatMessages((messages) => {
      if (
        messages.length === 1
        && messages[0].role === "assistant"
        && (
          messages[0].text === EFFECTIVE_INITIAL_ASSISTANT_MESSAGE.en
          || messages[0].text === EFFECTIVE_INITIAL_ASSISTANT_MESSAGE.ko
          || messages[0].text === INITIAL_ASSISTANT_MESSAGE.en
          || messages[0].text === INITIAL_ASSISTANT_MESSAGE.ko
          || messages[0].text.includes("dry-run")
          || messages[0].text.includes("RAG 梨꾪똿 肄섏넄") // legacy mojibake sessions
          || messages[0].text.includes("RAG 채팅 콘솔")
        )
      ) {
        return [{ role: "assistant", text: EFFECTIVE_INITIAL_ASSISTANT_MESSAGE[language] }];
      }
      return messages;
    });
  }, [language]);

  useEffect(() => {
    const daemonSeconds = Number(
      learningDaemon?.cumulative_learning_seconds
        ?? learningDaemon?.total_runtime_seconds
        ?? 0,
    );
    const liveSeconds = Math.floor(learningElapsedMs / 1000);
    const nextSeconds = Math.max(
      Number.isFinite(daemonSeconds) ? daemonSeconds : 0,
      Number.isFinite(liveSeconds) ? liveSeconds : 0,
    );
    if (nextSeconds <= 0) return;
    setPersistedLearningSeconds((current) => Math.max(current, Math.floor(nextSeconds)));
  }, [learningDaemon?.cumulative_learning_seconds, learningDaemon?.total_runtime_seconds, learningElapsedMs]);

  useEffect(() => {
    if (persistedLearningSeconds > 0) {
      writeBrowserStorage("atanor.cumulativeLearningSeconds", String(Math.floor(persistedLearningSeconds)));
    }
  }, [persistedLearningSeconds]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const requestedWorkspace = params.get("workspace") ?? params.get("view");
    const requestedSurface = params.get("surface") ?? params.get("mode");
    const requestedApi = params.get("api") ?? params.get("backend");
    if (["lab", "dev", "developer"].includes(requestedWorkspace ?? "") || ["lab", "dev", "developer"].includes(requestedSurface ?? "")) {
      setLabSurfaceVisible(true);
    }
    if (["daemon", "cumulative", "cloud", "cloud-brain", "cloudbrain"].includes(requestedWorkspace ?? "")) {
      setWorkspaceMode("daemon");
    } else if (requestedWorkspace === "lab") {
      setWorkspaceMode("lab");
    }
    if (requestedApi) {
      setLocalBackendUrl(requestedApi);
      connectLocalBackend(requestedApi).catch(() => undefined);
    }
  }, []);

  async function apiJson<T>(path: string, init?: RequestInit, options: { localOnly?: boolean; preferLocal?: boolean } = {}): Promise<T> {
    const shouldUseLocal = options.localOnly || options.preferLocal || localBackendConnected;
    if (shouldUseLocal) {
      try {
        return await directBackendJson<T>(localBackendUrl, path, init);
      } catch (caught) {
        if (options.localOnly) throw caught;
        try {
          const fallback = await fetchJson<T>(path, init);
          if (localBackendConnected) {
            setLocalBackendStatus("connected");
            setLocalBackendMessage("로컬 브레인 프록시 연결됨");
          }
          return fallback;
        } catch {
          // Continue to the existing health check so the user gets a precise status.
        }
        if (localBackendConnected) {
          const message = localBackendErrorMessage(localBackendUrl, caught);
          try {
            await directBackendJson<AnyRecord>(localBackendUrl, "/health");
            setLocalBackendStatus("connected");
            setLocalBackendMessage(`로컬 FastAPI 연결됨 / 일부 API fallback: ${message}`);
          } catch {
            setLocalBackendStatus("failed");
            setLocalBackendMessage(message);
          }
        }
      }
    }
    return fetchJson<T>(path, init);
  }

  useEffect(() => {
    let cancelled = false;
    async function refreshCandidateCloudStatus() {
      const candidateStatus = await fetchJson<AnyRecord>("/api/cloud-brain/candidate/status").catch(() => null);
      if (!cancelled && candidateStatus) {
        setCloudCandidateStatus(candidateStatus);
      }
    }
    refreshCandidateCloudStatus();
    const timer = window.setInterval(refreshCandidateCloudStatus, 12000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  async function syncLocalBackendState(url: string, benchmarkForStability?: AnyRecord | null) {
    const [
      memoryStatusResult,
      memoryGraphResult,
      memoryDriftResult,
      learningDaemonStatus,
      edgeBrokerStatus,
      brainSyncStatusResult,
      cloudBrainStatusResult,
      cloudBrainSourceInspectorResult,
      semanticCloudStatusResult,
      controlledGrowthProofResult,
      cloudBudgetStatusResult,
      atlasStatusResult,
      cortexStatusResult,
      qCortexStatusResult,
      baseBrainStatusResult,
      answerQualityStatusResult,
      brainGraphLocalResult,
      brainGraphCloudResult,
      brainGraphOverlayResult,
      brainGraphStatusResult,
      graphragStatus,
      guardStatus,
      ovenStatus,
      neuroStatus,
    ] = await Promise.all([
      directBackendJson<AnyRecord>(url, "/api/memory/status").catch(() => null),
      directBackendJson<AnyRecord>(url, "/api/memory/graph?limit=600&include_cloud_attached=true").catch(() => null),
      directBackendJson<AnyRecord>(url, "/api/memory/drift-check").catch(() => null),
      directBackendJson<AnyRecord>(url, "/api/learning/daemon/status").catch(() => null),
      fetchJson<AnyRecord>(edgeStatusApiPath(url)).catch(() => null),
      directBackendJson<AnyRecord>(url, "/api/brain-sync/status").catch(() => null),
      directBackendJson<AnyRecord>(url, "/api/cloud-brain/status").catch(() => null),
      directBackendJson<AnyRecord>(url, "/api/cloud-brain/source-inspector").catch(() => null),
      directBackendJson<AnyRecord>(url, "/api/cloud-brain/semantic/status").catch(() => null),
      directBackendJson<AnyRecord>(url, "/api/cloud-brain/controlled-self-growth-proof").catch(() => null),
      directBackendJson<AnyRecord>(url, "/api/neuro/cloud-budget", {
        method: "POST",
        body: JSON.stringify({
          plan: "plus",
          contribution_active: true,
          contribution_score: 0.6,
          local_strength: 0.55,
          cloud_coverage: 0.72,
          seed_stability: 0.64,
          working_memory_capacity: 0.58,
          epistemic_confidence: 0.7,
          provider_healthy: true,
          remaining_budget_ratio: 1,
        }),
      }).catch(() => null),
      directBackendJson<AnyRecord>(url, "/api/neuro/atlas").catch(() => null),
      directBackendJson<AnyRecord>(url, "/api/cortex/status").catch(() => null),
      directBackendJson<AnyRecord>(url, "/api/q-cortex/status").catch(() => null),
      directBackendJson<AnyRecord>(url, "/api/base-brain/status").catch(() => null),
      directBackendJson<AnyRecord>(url, "/api/answer-quality/status").catch(() => null),
      directBackendJson<AnyRecord>(url, brainGraphApiPath("local", localBrainGraphLayers)).catch(() => null),
      directBackendJson<AnyRecord>(url, brainGraphApiPath("cloud", cloudBrainGraphLayers)).catch(() => null),
      directBackendJson<AnyRecord>(url, "/api/brain/overlay-status").catch(() => null),
      directBackendJson<AnyRecord>(url, "/api/brain/graph/status").catch(() => null),
      directBackendJson<AnyRecord>(url, "/api/graphrag/status").catch(() => null),
      directBackendJson<AnyRecord>(url, "/api/guard/status").catch(() => null),
      directBackendJson<AnyRecord>(url, "/api/oven/status").catch(() => null),
      directBackendJson<AnyRecord>(url, "/api/neuro/plan").catch(() => null),
    ]);
    if (memoryStatusResult) setMemoryStatus(memoryStatusResult);
    if (memoryGraphResult && ("nodes" in memoryGraphResult || "working_memory_overlay" in memoryGraphResult)) setGraph(memoryGraphResult);
    if (memoryDriftResult) setMemoryDrift(memoryDriftResult);
    if (learningDaemonStatus) setLearningDaemon(learningDaemonStatus);
    if (edgeBrokerStatus) setEdgeStatus(edgeBrokerStatus);
    if (brainSyncStatusResult) setBrainSyncStatus(brainSyncStatusResult);
    if (cloudBrainStatusResult) setCloudBrainStatus(cloudBrainStatusResult);
    if (cloudBrainSourceInspectorResult) setCloudBrainSourceInspector(cloudBrainSourceInspectorResult);
    if (semanticCloudStatusResult) setSemanticCloudStatus(semanticCloudStatusResult);
    if (controlledGrowthProofResult) setControlledGrowthProof(controlledGrowthProofResult);
    if (cloudBudgetStatusResult) setCloudBudgetStatus(cloudBudgetStatusResult);
    if (atlasStatusResult) setAtlasStatus(atlasStatusResult);
    if (cortexStatusResult) {
      setCortexStatus((current) => ({
        ...cortexStatusResult,
        last_cycle: cortexStatusResult.last_cycle ?? current?.last_cycle,
      }));
    }
    if (qCortexStatusResult) setQCortexStatus(qCortexStatusResult);
    if (baseBrainStatusResult) setBaseBrainStatus(baseBrainStatusResult);
    if (answerQualityStatusResult) setAnswerQualityStatus(answerQualityStatusResult);
    if (brainGraphLocalResult) setBrainGraphLocal((current) => keepNonEmptyGraph(current, brainGraphLocalResult));
    if (brainGraphCloudResult) setBrainGraphCloud((current) => keepNonEmptyGraph(current, brainGraphCloudResult));
    if (brainGraphOverlayResult) setBrainGraphOverlayStatus(brainGraphOverlayResult);
    if (brainGraphStatusResult) setBrainGraphStatus(brainGraphStatusResult);
    if (graphragStatus) setGraphRag(graphragStatus);
    if (guardStatus) setGuard(guardStatus);
    if (ovenStatus) setOven(ovenStatus);
    if (neuroStatus) setNeuro(neuroStatus);
    if (benchmarkForStability?.can_read_local_hardware) {
      const stabilityStatus = await directBackendJson<AnyRecord>(url, "/api/neuro/stability", {
        method: "POST",
        body: JSON.stringify(stabilityPayloadForVolume(
          learningVolume,
          targetNodeCount,
          benchmarkForStability.hardware_profile,
        )),
      }).catch(() => null);
      if (stabilityStatus) setStability(stabilityStatus);
    }
  }

  async function connectLocalBackend(candidateUrl = localBackendUrl) {
    const url = normalizeLocalBackendUrl(candidateUrl);
    setLocalBackendUrl(url);
    setLocalBackendStatus("checking");
    setLocalBackendMessage("로컬 브레인 동기화 중");
    try {
      try {
        await directBackendJson<AnyRecord>(url, "/health");
      } catch {
        const proxiedMemoryStatus = await fetchJson<AnyRecord>("/api/memory/status");
        setMemoryStatus(proxiedMemoryStatus);
      }
      setLocalBackendStatus("connected");
      setLocalBackendMessage("로컬 브레인 연결됨");
      writeBrowserStorage("atanor.localFastApiUrl", url);
      fetchJson<AnyRecord>(edgeStatusApiPath(url))
        .then((edgeBrokerStatus) => setEdgeStatus(edgeBrokerStatus))
        .catch(() => setEdgeStatus(defaultEdgeBrokerStatus));
      benchmarkProbeAtRef.current = Date.now();
      const [systemStatus, gpuStatus, benchmarkStatus] = await Promise.all([
        directBackendJson<AnyRecord>(url, "/api/telemetry/system").catch(() => null),
        directBackendJson<AnyRecord>(url, "/api/telemetry/gpu").catch(() => null),
        directBackendJson<AnyRecord>(url, "/api/neuro/benchmark", {
          method: "POST",
          body: JSON.stringify({ run_probes: true }),
        }).catch(() => null),
      ]);
      if (systemStatus) setSystem(systemStatus);
      if (gpuStatus) setGpu(gpuStatus);
      if (benchmarkStatus) setBenchmark(benchmarkStatus);
      const requestedSection = new URLSearchParams(window.location.search).get("section");
      const deferHeavyLocalSync = requestedSection === "home" || requestedSection === "local" || requestedSection === "cloud";
      if (deferHeavyLocalSync) {
        window.setTimeout(() => {
          syncLocalBackendState(url, benchmarkStatus).catch(() => undefined);
        }, 1800);
      } else {
        await syncLocalBackendState(url, benchmarkStatus);
      }
      const recommended = benchmarkStatus?.recommended_learning_volume as LearningVolume | undefined;
      let nextVolume = learningVolume;
      let nextTargetNodeCount = targetNodeCount;
      if (benchmarkStatus?.can_read_local_hardware && recommended && learningVolumePresets[recommended]) {
        nextVolume = recommended;
        nextTargetNodeCount = defaultTargetNodesForVolume(recommended);
        setLearningVolume(recommended);
        setTargetNodeCount(nextTargetNodeCount);
      }
      if (benchmarkStatus?.can_read_local_hardware) {
        const stabilityStatus = await directBackendJson<AnyRecord>(url, "/api/neuro/stability", {
          method: "POST",
          body: JSON.stringify(stabilityPayloadForVolume(
            nextVolume,
            nextTargetNodeCount,
            benchmarkStatus.hardware_profile,
          )),
        });
        setStability(stabilityStatus);
      }
    } catch (caught) {
      setLocalBackendStatus("failed");
      setLocalBackendMessage(localBackendErrorMessage(url, caught));
    }
  }

  function disconnectLocalBackend() {
    setLocalBackendStatus("idle");
    setLocalBackendMessage("배포 fallback 사용 중");
    removeBrowserStorage("atanor.localFastApiUrl");
  }

  async function refreshAll() {
    const localStrict = localBackendConnected ? { localOnly: true } : {};
    let benchmarkForRefresh = benchmark;
    const shouldProbeBenchmark = localBackendConnected && (
      !benchmarkForRefresh || Date.now() - benchmarkProbeAtRef.current > 120000
    );
    if (shouldProbeBenchmark) {
      benchmarkProbeAtRef.current = Date.now();
      benchmarkForRefresh = await apiJson<AnyRecord>("/api/neuro/benchmark", {
        method: "POST",
        body: JSON.stringify({ run_probes: true }),
      }, { localOnly: true }).catch(() => benchmark);
    }
    const [
      pipelineStatus,
      datagateStatus,
      ontologyStatus,
      ontologyGraph,
      memoryStatusResult,
      memoryGraphResult,
      memoryDriftResult,
      learningDaemonStatus,
      edgeBrokerStatus,
      cloudBrainStatusResult,
      cloudBrainSourceInspectorResult,
      semanticCloudStatusResult,
      controlledGrowthProofResult,
      cloudBudgetStatusResult,
      atlasStatusResult,
      cortexStatusResult,
      qCortexStatusResult,
      baseBrainStatusResult,
      answerQualityStatusResult,
      brainGraphLocalResult,
      brainGraphCloudResult,
      brainGraphOverlayResult,
      brainGraphStatusResult,
      graphragStatus,
      guardStatus,
      gpuStatus,
      systemStatus,
      ovenStatus,
      neuroStatus,
      stabilityStatus,
      contributionStatusResult,
    ] = await Promise.all([
      apiJson<PipelineStatus>("/api/pipeline/status"),
      apiJson<AnyRecord>("/api/datagate/status"),
      apiJson<AnyRecord>("/api/ontology/status"),
      apiJson<AnyRecord>("/api/ontology/graph"),
      apiJson<AnyRecord>("/api/memory/status"),
      fetchJson<AnyRecord>(graphStreamApiPath(localBackendUrl, 600)).catch(() => apiJson<AnyRecord>("/api/memory/graph?limit=600&include_cloud_attached=true", undefined, localStrict)),
      apiJson<AnyRecord>("/api/memory/drift-check"),
      apiJson<AnyRecord>("/api/learning/daemon/status"),
      fetchJson<AnyRecord>(edgeStatusApiPath(localBackendUrl)).catch(() => defaultEdgeBrokerStatus),
      apiJson<AnyRecord>("/api/cloud-brain/status"),
      apiJson<AnyRecord>("/api/cloud-brain/source-inspector"),
      apiJson<AnyRecord>("/api/cloud-brain/semantic/status"),
      apiJson<AnyRecord>("/api/cloud-brain/controlled-self-growth-proof"),
      apiJson<AnyRecord>("/api/neuro/cloud-budget", {
        method: "POST",
        body: JSON.stringify({
          plan: "plus",
          contribution_active: contributionEnabled && !contributionPaused,
          contribution_score: contributionEnabled && !contributionPaused ? 0.6 : 0,
          local_strength: contributionEnabled ? 0.55 : 0.78,
          cloud_coverage: contributionEnabled ? 0.72 : 0.28,
          seed_stability: 0.64,
          working_memory_capacity: 0.58,
          epistemic_confidence: contributionEnabled ? 0.7 : 0.45,
          provider_healthy: String(cloudBrainStatus?.broker_state ?? "") === "remote_connected",
          remaining_budget_ratio: 1,
        }),
      }),
      apiJson<AnyRecord>("/api/neuro/atlas"),
      localBackendConnected
        ? directBackendJson<AnyRecord>(localBackendUrl, "/api/cortex/status").catch(() => null)
        : Promise.resolve(null),
      localBackendConnected
        ? directBackendJson<AnyRecord>(localBackendUrl, "/api/q-cortex/status").catch(() => null)
        : apiJson<AnyRecord>("/api/q-cortex/status").catch(() => null),
      localBackendConnected
        ? directBackendJson<AnyRecord>(localBackendUrl, "/api/base-brain/status").catch(() => null)
        : apiJson<AnyRecord>("/api/base-brain/status").catch(() => null),
      localBackendConnected
        ? directBackendJson<AnyRecord>(localBackendUrl, "/api/answer-quality/status").catch(() => null)
        : apiJson<AnyRecord>("/api/answer-quality/status").catch(() => null),
      fetchJson<AnyRecord>(brainGraphApiPath("local", localBrainGraphLayers)).catch(() => null),
      fetchJson<AnyRecord>(brainGraphApiPath("cloud", cloudBrainGraphLayers)).catch(() => null),
      fetchJson<AnyRecord>("/api/brain/overlay-status").catch(() => null),
      fetchJson<AnyRecord>("/api/brain/graph/status").catch(() => null),
      apiJson<AnyRecord>("/api/graphrag/status"),
      apiJson<AnyRecord>("/api/guard/status"),
      apiJson<AnyRecord>("/api/telemetry/gpu"),
      apiJson<AnyRecord>("/api/telemetry/system"),
      apiJson<AnyRecord>("/api/oven/status"),
      apiJson<AnyRecord>("/api/neuro/plan"),
      apiJson<AnyRecord>("/api/neuro/stability", {
        method: "POST",
        body: JSON.stringify(stabilityPayloadForVolume(
          learningVolume,
          targetNodeCount,
          benchmarkForRefresh?.can_read_local_hardware ? benchmarkForRefresh.hardware_profile : null,
        )),
      }),
      localBackendConnected
        ? directBackendJson<AnyRecord>(localBackendUrl, "/api/contribution/status").catch(() => null)
        : Promise.resolve(null),
    ]);
    setPipeline(pipelineStatus);
    setDatagate(datagateStatus);
    setOntology(ontologyStatus);
    setMemoryStatus(memoryStatusResult);
    setMemoryDrift(memoryDriftResult);
    setLearningDaemon(learningDaemonStatus);
    setEdgeStatus(edgeBrokerStatus);
    setCloudBrainStatus(cloudBrainStatusResult);
    setCloudBrainSourceInspector(cloudBrainSourceInspectorResult);
    setSemanticCloudStatus(semanticCloudStatusResult);
    setControlledGrowthProof(controlledGrowthProofResult);
    setCloudBudgetStatus(cloudBudgetStatusResult);
    setAtlasStatus(atlasStatusResult);
    setCortexStatus((current) => (
      cortexStatusResult
        ? { ...cortexStatusResult, last_cycle: cortexStatusResult.last_cycle ?? current?.last_cycle }
        : current
    ));
    setQCortexStatus((current) => qCortexStatusResult ?? current);
    setBaseBrainStatus((current) => baseBrainStatusResult ?? current);
    setAnswerQualityStatus((current) => answerQualityStatusResult ?? current);
    setBrainGraphLocal((current) => keepNonEmptyGraph(current, brainGraphLocalResult));
    setBrainGraphCloud((current) => keepNonEmptyGraph(current, brainGraphCloudResult));
    setBrainGraphOverlayStatus((current) => brainGraphOverlayResult ?? current);
    setBrainGraphStatus((current) => brainGraphStatusResult ?? current);
    setGraph(memoryGraphResult && ("nodes" in memoryGraphResult || "working_memory_overlay" in memoryGraphResult) ? memoryGraphResult : ontologyGraph);
    setGraphRag(graphragStatus);
    setGuard(guardStatus);
    setGpu(gpuStatus);
    setSystem(systemStatus);
    if (benchmarkForRefresh) setBenchmark(benchmarkForRefresh);
    setOven(ovenStatus);
    setNeuro(neuroStatus);
    setStability(stabilityStatus);
    setContributionStatus(contributionStatusResult);
  }

  async function runControlledGrowthProof() {
    setControlledGrowthRunning(true);
    setControlledGrowthError(null);
    try {
      const proof = await apiJson<AnyRecord>("/api/cloud-brain/prove-controlled-self-growth", {
        method: "POST",
      }, localBackendConnected ? { localOnly: true } : {});
      setControlledGrowthProof(proof);
      const nextCloudStatus = await apiJson<AnyRecord>("/api/cloud-brain/status", undefined, localBackendConnected ? { localOnly: true } : {});
      setCloudBrainStatus(nextCloudStatus);
    } catch (caught) {
      setControlledGrowthError(caught instanceof Error ? caught.message : "Controlled self-growth proof failed.");
    } finally {
      setControlledGrowthRunning(false);
    }
  }

  async function refreshSemanticCloud() {
    setSemanticGrowthError(null);
    const [status, cloudGraph] = await Promise.all([
      apiJson<AnyRecord>("/api/cloud-brain/semantic/status", undefined, localBackendConnected ? { localOnly: true } : {}),
      fetchJson<AnyRecord>(brainGraphApiPath("cloud", cloudBrainGraphLayers, "full")).catch(() => null),
    ]);
    setSemanticCloudStatus(status);
    if (cloudGraph) setBrainGraphCloud(cloudGraph);
  }

  async function ingestSampleSemanticSource() {
    setSemanticGrowthRunning(true);
    setSemanticGrowthError(null);
    try {
      const summary = await apiJson<AnyRecord>("/api/cloud-brain/semantic/ingest", {
        method: "POST",
        body: JSON.stringify({
          text: "쿠버네티스는 컨테이너화된 애플리케이션을 자동으로 배포하고 관리하는 오픈소스 플랫폼입니다.",
          source_id: "ui-sample-kubernetes-ko",
          language: "ko",
          title: "ATANOR semantic growth sample",
          usage_allowed: false,
        }),
      }, localBackendConnected ? { localOnly: true } : {});
      setSemanticGrowthRun(summary);
      await refreshSemanticCloud();
    } catch (caught) {
      setSemanticGrowthError(caught instanceof Error ? caught.message : "Semantic Cloud ingest failed.");
    } finally {
      setSemanticGrowthRunning(false);
    }
  }

  async function accelerateSemanticCloudBatch() {
    setSemanticGrowthRunning(true);
    setSemanticGrowthError(null);
    try {
      const summary = await apiJson<AnyRecord>("/api/cloud-brain/semantic/accelerate", {
        method: "POST",
        body: JSON.stringify({ batch_size: 1000 }),
      }, localBackendConnected ? { localOnly: true } : {});
      setSemanticGrowthRun(summary);
      await refreshSemanticCloud();
    } catch (caught) {
      setSemanticGrowthError(caught instanceof Error ? caught.message : "Semantic Cloud acceleration failed.");
    } finally {
      setSemanticGrowthRunning(false);
    }
  }

  async function attachSemanticCloudSample() {
    setSemanticGrowthRunning(true);
    setSemanticGrowthError(null);
    try {
      const attach = await apiJson<AnyRecord>("/api/cloud-brain/semantic/attach", {
        method: "POST",
        body: JSON.stringify({ query: "쿠버네티스가 뭐야?", limit: 8 }),
      }, localBackendConnected ? { localOnly: true } : {});
      setSemanticAttachResult(attach);
      const [overlay, memoryGraph, cloudGraph] = await Promise.all([
        fetchJson<AnyRecord>("/api/brain/overlay-status").catch(() => null),
        apiJson<AnyRecord>("/api/memory/graph?limit=600&include_cloud_attached=true", undefined, localBackendConnected ? { localOnly: true } : {}).catch(() => null),
        fetchJson<AnyRecord>(brainGraphApiPath("cloud", cloudBrainGraphLayers, "full")).catch(() => null),
      ]);
      if (overlay) setBrainGraphOverlayStatus(overlay);
      if (memoryGraph && ("nodes" in memoryGraph || "working_memory_overlay" in memoryGraph)) setGraph(memoryGraph);
      if (cloudGraph) setBrainGraphCloud(cloudGraph);
    } catch (caught) {
      setSemanticGrowthError(caught instanceof Error ? caught.message : "Semantic Cloud attach failed.");
    } finally {
      setSemanticGrowthRunning(false);
    }
  }

  async function refreshGraphHub() {
    setGraphHubError(null);
    setGraphHubLoading(true);
    const query = new URLSearchParams();
    if (graphHubPricingFilter !== "all") query.set("pricing_model", graphHubPricingFilter);
    if (graphHubSearch.trim()) query.set("query", graphHubSearch.trim());
    const suffix = query.toString() ? `?${query.toString()}` : "";
    // Read Hub data over whichever channel answers first. When the Local Brain is CONNECTED
    // the demo fires many DIRECT browser→backend polls that saturate the browser's per-host
    // connection pool (~6 over HTTP/1.1), so a direct Hub read can hang → empty list. Racing
    // the direct call against the server-side proxy (which uses a different host pool and
    // reaches the same backend) fills the Hub reliably: in the local demo the proxy wins; in a
    // deployed local-first setup, where the proxy cannot reach the user's backend, the direct
    // call wins. Generous timeout because reads can be slow under polling congestion.
    const hubGet = async <T,>(path: string, fallback: T): Promise<T> => {
      const channels: Promise<T>[] = [fetchJson<T>(path, undefined, 9000)];
      if (localBackendConnected) {
        channels.push(directBackendJson<T>(localBackendUrl, path, undefined, 9000));
      }
      try {
        return await Promise.any(channels);
      } catch {
        return fallback;
      }
    };
    const [status, catalog, installed, attachments, audit] = await Promise.all([
      hubGet<AnyRecord | null>("/api/graph-hub/status", null),
      hubGet<AnyRecord[]>(`/api/graph-hub/catalog${suffix}`, []),
      hubGet<AnyRecord[]>("/api/graph-hub/installed", []),
      hubGet<AnyRecord[]>("/api/graph-hub/attachments", []),
      hubGet<AnyRecord[]>("/api/graph-hub/audit?limit=20", []),
    ]);
    if (status) setGraphHubStatus(status);
    setGraphHubCatalog(Array.isArray(catalog) ? catalog : []);
    setGraphHubInstalled(Array.isArray(installed) ? installed : []);
    setGraphHubAttachments(Array.isArray(attachments) ? attachments : []);
    setGraphHubAudit(Array.isArray(audit) ? audit : []);
    setGraphHubLoading(false);
    // Report whether real data arrived, so the auto-load effect can retry through a
    // backend-restart / first-load transient instead of showing an empty Hub.
    return (Array.isArray(installed) && installed.length > 0)
      || (Array.isArray(catalog) && catalog.length > 0)
      || (Array.isArray(attachments) && attachments.length > 0);
  }

  async function runGraphHubAction(action: string, path: string, body?: AnyRecord) {
    setGraphHubRunning(action);
    setGraphHubError(null);
    try {
      const result = await apiJson<AnyRecord>(path, {
        method: "POST",
        body: body ? JSON.stringify(body) : undefined,
      }, localBackendConnected ? { localOnly: true } : {});
      if (action === "export") setGraphHubExport(result);
      if (action === "proof") setGraphHubProof(result);
      await refreshGraphHub();
      const cloudGraph = await fetchJson<AnyRecord>(brainGraphApiPath("cloud", cloudBrainGraphLayers, "full")).catch(() => null);
      if (cloudGraph) setBrainGraphCloud(cloudGraph);
    } catch (caught) {
      setGraphHubError(caught instanceof Error ? caught.message : "Graph Hub action failed.");
    } finally {
      setGraphHubRunning(null);
    }
  }

  async function inspectGraphHubCartridge(item: AnyRecord) {
    const cartridgeId = String(item.cartridge_id);
    setGraphHubRunning(`inspect-${cartridgeId}`);
    setGraphHubError(null);
    try {
      const [profileResult, synergyResult] = await Promise.all([
        apiJson<AnyRecord>(`/api/graph-hub/cartridges/${encodeURIComponent(cartridgeId)}/profile`, undefined, localBackendConnected ? { localOnly: true } : {}),
        apiJson<AnyRecord>(`/api/graph-hub/cartridges/${encodeURIComponent(cartridgeId)}/synergy`, {
          method: "POST",
          body: JSON.stringify({ active_context: graphHubSearch.trim() || String(item.category ?? "") }),
        }, localBackendConnected ? { localOnly: true } : {}),
      ]);
      setGraphHubProfiles((current) => ({ ...current, [cartridgeId]: profileResult }));
      setGraphHubSynergy((current) => ({ ...current, [cartridgeId]: synergyResult }));
    } catch (caught) {
      setGraphHubError(caught instanceof Error ? caught.message : "Graph cartridge inspection failed.");
    } finally {
      setGraphHubRunning(null);
    }
  }

  async function startGraphHubTrial(item: AnyRecord) {
    const cartridgeId = String(item.cartridge_id);
    setGraphHubRunning(`trial-${cartridgeId}`);
    setGraphHubError(null);
    try {
      const trial = await apiJson<AnyRecord>(`/api/graph-hub/cartridges/${encodeURIComponent(cartridgeId)}/trial/start`, {
        method: "POST",
        body: JSON.stringify({ intent: graphHubSearch.trim() || String(item.subtitle ?? item.name ?? cartridgeId) }),
      }, localBackendConnected ? { localOnly: true } : {});
      setGraphHubTrials((current) => ({ ...current, [cartridgeId]: trial }));
      setGraphHubTrialInputs((current) => ({ ...current, [cartridgeId]: current[cartridgeId] ?? (language === "ko" ? "이 카트리지가 어떤 근거를 제공하나요?" : "What evidence does this cartridge provide?") }));
    } catch (caught) {
      setGraphHubError(caught instanceof Error ? caught.message : "Graph cartridge trial failed.");
    } finally {
      setGraphHubRunning(null);
    }
  }

  async function runGraphHubTrialQuery(item: AnyRecord) {
    const cartridgeId = String(item.cartridge_id);
    const trial = graphHubTrials[cartridgeId];
    const sessionId = String(trial?.session_id ?? "");
    if (!sessionId) return;
    setGraphHubRunning(`trial-query-${cartridgeId}`);
    setGraphHubError(null);
    try {
      const result = await apiJson<AnyRecord>(`/api/graph-hub/trials/${encodeURIComponent(sessionId)}/query`, {
        method: "POST",
        body: JSON.stringify({ query: graphHubTrialInputs[cartridgeId] || String(item.name ?? cartridgeId) }),
      }, localBackendConnected ? { localOnly: true } : {});
      setGraphHubTrials((current) => ({
        ...current,
        [cartridgeId]: {
          ...trial,
          ...result,
          query_results: [...(Array.isArray(trial?.query_results) ? trial.query_results : []), result],
        },
      }));
    } catch (caught) {
      setGraphHubError(caught instanceof Error ? caught.message : "Sandbox query failed.");
    } finally {
      setGraphHubRunning(null);
    }
  }

  async function runRemoteCloudBrainProof() {
    setRemoteCloudProofRunning(true);
    setRemoteCloudProofError(null);
    try {
      const result = await apiJson<AnyRecord>("/api/cloud-brain/prove-remote-cloud-brain", {
        method: "POST",
      }, localBackendConnected ? { localOnly: true } : {});
      const proof = (result.remote_proof && typeof result.remote_proof === "object" && !Array.isArray(result.remote_proof))
        ? result.remote_proof as AnyRecord
        : result;
      setRemoteCloudProof(proof);
      setCloudBrainSourceInspector(result);
      const nextCloudStatus = await apiJson<AnyRecord>("/api/cloud-brain/status", undefined, localBackendConnected ? { localOnly: true } : {});
      setCloudBrainStatus(nextCloudStatus);
    } catch (caught) {
      setRemoteCloudProofError(caught instanceof Error ? caught.message : "Remote Cloud Brain proof failed.");
    } finally {
      setRemoteCloudProofRunning(false);
    }
  }

  async function buildBaseBrainPack() {
    setBaseBrainRunning(true);
    setBaseBrainError(null);
    try {
      await fetchJson<AnyRecord>("/api/base-brain/build", {
        method: "POST",
      });
      const status = await fetchJson<AnyRecord>("/api/base-brain/status");
      setBaseBrainStatus(status);
    } catch (caught) {
      setBaseBrainError(caught instanceof Error ? caught.message : "Base Brain build failed.");
    } finally {
      setBaseBrainRunning(false);
    }
  }

  async function askBaseBrain() {
    setBaseBrainRunning(true);
    setBaseBrainError(null);
    try {
      const result = await fetchJson<AnyRecord>("/api/base-brain/answer", {
        method: "POST",
        body: JSON.stringify({
          query: baseBrainQuery,
          language,
          audience_level: "beginner",
          mode: "default",
        }),
      });
      setBaseBrainAnswer(result);
    } catch (caught) {
      setBaseBrainError(caught instanceof Error ? caught.message : "Base Brain answer failed.");
    } finally {
      setBaseBrainRunning(false);
    }
  }

  async function runBaseBrainBenchmark(limit = 10) {
    setBaseBrainRunning(true);
    setBaseBrainError(null);
    try {
      const result = await fetchJson<AnyRecord>("/api/base-brain/benchmark", {
        method: "POST",
        body: JSON.stringify({ limit }),
      });
      setBaseBrainBenchmark(result);
    } catch (caught) {
      setBaseBrainError(caught instanceof Error ? caught.message : "Base Brain benchmark failed.");
    } finally {
      setBaseBrainRunning(false);
    }
  }

  async function runAnswerQualityLab(limit = 8) {
    setAnswerQualityRunning(true);
    setAnswerQualityError(null);
    try {
      const result = await apiJson<AnyRecord>("/api/answer-quality/run", {
        method: "POST",
        body: JSON.stringify({
          benchmark_set: "core_ko_en_v1",
          limit,
        }),
      }, localBackendConnected ? { localOnly: true } : {});
      setAnswerQualityRun(result);
      setAnswerQualityStatus((current) => ({
        ...(current ?? {}),
        latest_run: result,
        state: "active",
      }));
    } catch (caught) {
      setAnswerQualityError(caught instanceof Error ? caught.message : "Answer Quality Lab failed.");
    } finally {
      setAnswerQualityRunning(false);
    }
  }

  async function runAnswerRepairComparison(limit = 8) {
    setAnswerRepairRunning(true);
    setAnswerRepairError(null);
    try {
      const result = await fetchJson<AnyRecord>("/api/answer-quality/run-repair-comparison", {
        method: "POST",
        body: JSON.stringify({
          benchmark_set: "core_ko_en_v1",
          limit,
        }),
      });
      setAnswerRepairComparison(result);
      writeBrowserStorage("atanor.latestAnswerRepairComparison", JSON.stringify(result));
    } catch (caught) {
      setAnswerRepairError(caught instanceof Error ? caught.message : "Repair comparison failed.");
    } finally {
      setAnswerRepairRunning(false);
    }
  }

  async function refreshRepairReviewQueue() {
    const [candidateResult, rulesResult, auditResult] = await Promise.all([
      fetchJson<AnyRecord>("/api/surface-brain/repair-candidates"),
      fetchJson<AnyRecord>("/api/surface-brain/production-rules"),
      fetchJson<AnyRecord>("/api/surface-brain/repair-audit?limit=8"),
    ]);
    setRepairCandidates(Array.isArray(candidateResult.candidates) ? candidateResult.candidates : []);
    setProductionRepairRules(Array.isArray(rulesResult.production_rules) ? rulesResult.production_rules : []);
    setRepairAuditEvents(Array.isArray(auditResult.events) ? auditResult.events : []);
  }

  async function generateRepairCandidatesFromFeedback() {
    if (!answerQualityFeedback.length) {
      setRepairReviewError(language === "ko" ? "먼저 Answer Quality Lab을 실행해 피드백을 생성하세요." : "Run Answer Quality Lab first to create feedback.");
      return;
    }
    setRepairReviewRunning(true);
    setRepairReviewError(null);
    try {
      await fetchJson<AnyRecord>("/api/surface-brain/feedback-to-repair-candidates", {
        method: "POST",
        body: JSON.stringify({
          run_id: String(latestAnswerQualityRun?.run_id ?? "ui-answer-quality-run"),
          feedback_items: answerQualityFeedback,
        }),
      });
      await refreshRepairReviewQueue();
    } catch (caught) {
      setRepairReviewError(caught instanceof Error ? caught.message : "Repair candidate generation failed.");
    } finally {
      setRepairReviewRunning(false);
    }
  }

  async function reviewCandidateAction(candidateId: string, action: "approve" | "reject") {
    setRepairReviewRunning(true);
    setRepairReviewError(null);
    try {
      await fetchJson<AnyRecord>(`/api/surface-brain/repair-candidates/${encodeURIComponent(candidateId)}/${action}`, {
        method: "POST",
        body: JSON.stringify({
          reviewer: "local_operator",
          comment: action === "approve" ? "Approved from ATANOR lab UI." : "Rejected from ATANOR lab UI.",
        }),
      });
      await refreshRepairReviewQueue();
    } catch (caught) {
      setRepairReviewError(caught instanceof Error ? caught.message : `Repair candidate ${action} failed.`);
    } finally {
      setRepairReviewRunning(false);
    }
  }

  async function rollbackProductionRepairRule(ruleId: string) {
    setRepairReviewRunning(true);
    setRepairReviewError(null);
    try {
      await fetchJson<AnyRecord>(`/api/surface-brain/production-rules/${encodeURIComponent(ruleId)}/rollback`, { method: "POST" });
      await refreshRepairReviewQueue();
    } catch (caught) {
      setRepairReviewError(caught instanceof Error ? caught.message : "Production rule rollback failed.");
    } finally {
      setRepairReviewRunning(false);
    }
  }

  useEffect(() => {
    if (workspaceMode !== "lab" || mainSection !== "cloud" || answerRepairComparison || answerRepairRunning) return;
    let cancelled = false;
    const saved = readBrowserStorage("atanor.latestAnswerRepairComparison");
    if (saved) {
      try {
        const parsed = JSON.parse(saved) as AnyRecord;
        if (parsed && parsed.run_id) {
          setAnswerRepairComparison(parsed);
          return () => {
            cancelled = true;
          };
        }
      } catch {
        writeBrowserStorage("atanor.latestAnswerRepairComparison", "");
      }
    }
    fetchJson<AnyRecord>("/api/answer-quality/repair-comparisons?limit=1")
      .then((result) => {
        if (cancelled) return;
        const rows = Array.isArray(result.repair_comparisons) ? result.repair_comparisons : [];
        if (rows[0]) {
          setAnswerRepairComparison(rows[0]);
          writeBrowserStorage("atanor.latestAnswerRepairComparison", JSON.stringify(rows[0]));
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [answerRepairComparison, answerRepairRunning, mainSection, workspaceMode]);

  useEffect(() => {
    if (workspaceMode !== "lab" || mainSection !== "cloud") return;
    refreshRepairReviewQueue().catch(() => undefined);
  }, [mainSection, workspaceMode]);

  async function refreshCloudProofFast() {
    const [semanticStatusResult, cloudSourceInspectorResult] = await Promise.all([
      fetchJson<AnyRecord>("/api/cloud-brain/semantic/status").catch(() => null),
      fetchJson<AnyRecord>("/api/cloud-brain/source-inspector").catch(() => null),
    ]);
    if (semanticStatusResult) setSemanticCloudStatus(semanticStatusResult);
    if (cloudSourceInspectorResult) setCloudBrainSourceInspector(cloudSourceInspectorResult);
  }

  async function refreshBrainGraphPanels(profile: "fast" | "full" = "fast") {
    async function fetchBrainGraph(view: "local" | "cloud", layers: string[]) {
      const selectedId = typeof selectedMemory?.id === "string" ? selectedMemory.id : "";
      const focusOptions = view === mainSection && selectedId
        ? { focusNodeId: selectedId, lod: profile === "full" ? 4 : 3 }
        : undefined;
      const path = brainGraphApiPath(view, layers, profile, focusOptions);
      const primary = await (localBackendConnected
        ? directBackendJson<AnyRecord>(localBackendUrl, path).catch(() => fetchJson<AnyRecord>(path).catch(() => null))
        : fetchJson<AnyRecord>(path).catch(() => null));
      const primaryNodeCount = Array.isArray(primary?.nodes) ? primary.nodes.length : 0;
      if (primaryNodeCount > 0) return primary;
      const fallbackPath = brainGraphApiPath(view, undefined, profile);
      return localBackendConnected
        ? directBackendJson<AnyRecord>(localBackendUrl, fallbackPath).catch(() => fetchJson<AnyRecord>(fallbackPath).catch(() => primary))
        : fetchJson<AnyRecord>(fallbackPath).catch(() => primary);
    }
    const semanticStatusPromise = fetchJson<AnyRecord>("/api/cloud-brain/semantic/status").catch(() => null);
    const cloudSourceInspectorPromise = fetchJson<AnyRecord>("/api/cloud-brain/source-inspector").catch(() => null);
    const [localResult, cloudResult, overlayResult, statusResult] = await Promise.all([
      fetchBrainGraph("local", localBrainGraphLayers),
      fetchBrainGraph("cloud", cloudBrainGraphLayers),
      fetchJson<AnyRecord>("/api/brain/overlay-status").catch(() => null),
      fetchJson<AnyRecord>("/api/brain/graph/status").catch(() => null),
    ]);
    if (localResult) setBrainGraphLocal((current) => keepNonEmptyGraph(current, localResult));
    if (cloudResult) setBrainGraphCloud((current) => keepNonEmptyGraph(current, cloudResult));
    if (overlayResult) setBrainGraphOverlayStatus(overlayResult);
    if (statusResult) setBrainGraphStatus(statusResult);
    Promise.all([semanticStatusPromise, cloudSourceInspectorPromise])
      .then(([semanticStatusResult, cloudSourceInspectorResult]) => {
        if (semanticStatusResult) setSemanticCloudStatus(semanticStatusResult);
        if (cloudSourceInspectorResult) setCloudBrainSourceInspector(cloudSourceInspectorResult);
      })
      .catch(() => undefined);
  }

  useEffect(() => {
    if (mainSection !== "local" && mainSection !== "cloud") return;
    refreshBrainGraphPanels().catch(() => undefined);
  }, [mainSection, localBrainGraphLayers, cloudBrainGraphLayers]);

  useEffect(() => {
    if (mainSection !== "local" && mainSection !== "cloud") return;
    let attempts = 0;
    const maxAttempts = localBackendConnected ? 3 : 2;
    const interval = window.setInterval(() => {
      attempts += 1;
      refreshBrainGraphPanels().catch(() => undefined);
      if (attempts >= maxAttempts) window.clearInterval(interval);
    }, localBackendConnected ? 700 : 1200);
    return () => window.clearInterval(interval);
  }, [mainSection, localBrainGraphLayers, cloudBrainGraphLayers, localBackendConnected]);

  function toggleBrainGraphLayer(view: "local" | "cloud", layer: string) {
    const setter = view === "local" ? setLocalBrainGraphLayers : setCloudBrainGraphLayers;
    setter((current) => (
      current.includes(layer)
        ? current.filter((item) => item !== layer)
        : [...current, layer]
    ));
  }

  async function refreshGraphWithCloudOverlay() {
    const localStrict = localBackendConnected ? { localOnly: true } : {};
    const attachmentResult = await apiJson<AnyRecord>("/api/working-memory/cloud-attachments", undefined, localStrict).catch(() => null);
    if (attachmentResult) setCloudAttachmentStatus(attachmentResult);
    const graphResult = await fetchJson<AnyRecord>(graphStreamApiPath(localBackendUrl, 600))
      .catch(() => apiJson<AnyRecord>("/api/memory/graph?limit=600&include_cloud_attached=true", undefined, localStrict));
    if (graphResult && ("nodes" in graphResult || "working_memory_overlay" in graphResult)) setGraph(graphResult);
    return graphResult;
  }

  async function attachCloudContext() {
    setCloudAttachmentRunning(true);
    setCloudAttachmentError(null);
    try {
      const localStrict = localBackendConnected ? { localOnly: true } : {};
      const created = await apiJson<AnyRecord>("/api/working-memory/cloud-attachments/create", {
        method: "POST",
        body: JSON.stringify({ query: chatInput.trim() || memoryQuery.trim() || "GraphRAG evidence" }),
      }, localStrict);
      const bundleId = String((created.bundle as AnyRecord | undefined)?.bundle_id ?? "");
      if (!bundleId) throw new Error(String(created.reason ?? "No Cloud Node Bundle was created."));
      const attached = await apiJson<AnyRecord>("/api/working-memory/cloud-attachments/attach", {
        method: "POST",
        body: JSON.stringify({ bundle_id: bundleId }),
      }, localStrict);
      setCloudAttachmentStatus(attached);
      if (attached.cortex_g2 && typeof attached.cortex_g2 === "object" && !Array.isArray(attached.cortex_g2)) {
        setCortexStatus((current) => ({
          ...(current ?? {}),
          state: "active",
          last_cycle: attached.cortex_g2 as AnyRecord,
        }));
      }
      await refreshGraphWithCloudOverlay();
    } catch (caught) {
      setCloudAttachmentError(caught instanceof Error ? caught.message : "Cloud context attachment failed.");
    } finally {
      setCloudAttachmentRunning(false);
    }
  }

  async function detachCloudContext() {
    setCloudAttachmentRunning(true);
    setCloudAttachmentError(null);
    try {
      const localStrict = localBackendConnected ? { localOnly: true } : {};
      const activeIds = ((cloudAttachmentStatus?.working_memory_overlay as AnyRecord | undefined)?.bundle_ids as string[] | undefined)
        ?? (cloudAttachmentStatus?.active_bundle_ids as string[] | undefined)
        ?? ((graph?.working_memory_overlay as AnyRecord | undefined)?.bundle_ids as string[] | undefined)
        ?? [];
      for (const bundleId of activeIds) {
        await apiJson<AnyRecord>("/api/working-memory/cloud-attachments/detach", {
          method: "POST",
          body: JSON.stringify({ bundle_id: bundleId }),
        }, localStrict);
      }
      const listed = await apiJson<AnyRecord>("/api/working-memory/cloud-attachments", undefined, localStrict);
      setCloudAttachmentStatus(listed);
      await refreshGraphWithCloudOverlay();
      if (Number(listed.cloud_attached_nodes ?? 0) === 0) {
        setGraph((current) => ({
          ...(current ?? {}),
          nodes: [],
          edges: [],
          counts: {
            local_nodes: 0,
            local_edges: 0,
            seed_anchor_nodes: 0,
            cloud_attached_nodes: 0,
            cloud_attached_edges: 0,
          },
          working_memory_overlay: {
            active: false,
            bundle_ids: [],
            cloud_attached_nodes: 0,
            cloud_attached_edges: 0,
            seed_anchor_nodes: 0,
            writes_to_local_brain: false,
            detachable: true,
          },
          local_brain_empty: true,
          cloud_mirror_excluded_from_local_brain: true,
        }));
      }
    } catch (caught) {
      setCloudAttachmentError(caught instanceof Error ? caught.message : "Cloud context detach failed.");
    } finally {
      setCloudAttachmentRunning(false);
    }
  }

  async function clearCloudOverlay() {
    setCloudAttachmentRunning(true);
    setCloudAttachmentError(null);
    try {
      const localStrict = localBackendConnected ? { localOnly: true } : {};
      const cleared = await apiJson<AnyRecord>("/api/working-memory/cloud-attachments/clear", { method: "POST" }, localStrict);
      setCloudAttachmentStatus(cleared);
      await refreshGraphWithCloudOverlay();
      setGraph((current) => ({
        ...(current ?? {}),
        nodes: [],
        edges: [],
        counts: {
          local_nodes: 0,
          local_edges: 0,
          seed_anchor_nodes: 0,
          cloud_attached_nodes: 0,
          cloud_attached_edges: 0,
        },
        working_memory_overlay: {
          active: false,
          bundle_ids: [],
          cloud_attached_nodes: 0,
          cloud_attached_edges: 0,
          seed_anchor_nodes: 0,
          writes_to_local_brain: false,
          detachable: true,
        },
        local_brain_empty: true,
        cloud_mirror_excluded_from_local_brain: true,
      }));
    } catch (caught) {
      setCloudAttachmentError(caught instanceof Error ? caught.message : "Cloud overlay clear failed.");
    } finally {
      setCloudAttachmentRunning(false);
    }
  }

  useEffect(() => {
    const requestedSection = new URLSearchParams(window.location.search).get("section");
    const deferFullRefresh = requestedSection === "home" || requestedSection === "local" || requestedSection === "cloud";
    // Only sections that display the live dashboard aggregate keep polling it. The recurring
    // ~24-endpoint refreshAll goes DIRECT to the backend; on light sections (Graph Hub, Brain
    // Link, Settings, Agora…) that storm saturates the browser's per-host socket pool and
    // stalls those panels' own reads (Graph Hub rendered empty). Light sections keep their
    // last-known status pills; one initial refresh still runs on first mount for baseline data.
    const aggregateSection = mainSection === "home" || mainSection === "local"
      || mainSection === "cloud" || mainSection === "atlas";
    let initialTimer: number | undefined;
    if (aggregateSection || !didInitialAggregateRef.current) {
      didInitialAggregateRef.current = true;
      initialTimer = window.setTimeout(() => {
      refreshAll().catch((caught) => setError(caught instanceof Error ? caught.message : "BakeBoard를 불러오지 못했습니다."));
      }, deferFullRefresh ? 1600 : 0);
    }
    const timer = aggregateSection
      ? window.setInterval(() => {
          refreshAll().catch(() => undefined);
        }, 10000)
      : null;
    return () => {
      if (initialTimer !== undefined) window.clearTimeout(initialTimer);
      if (timer !== null) window.clearInterval(timer);
    };
  }, [mainSection, learningVolume, targetNodeCount, benchmark?.can_read_local_hardware, benchmark?.generated_at, localBackendConnected, localBackendUrl]);

  useEffect(() => {
    if (mainSection !== "local") return;
    refreshGraphWithCloudOverlay().catch(() => undefined);
  }, [mainSection, localBackendConnected, localBackendUrl]);

  useEffect(() => {
    if (mainSection !== "graphhub") return;
    let cancelled = false;
    let attempts = 0;
    const run = async () => {
      if (cancelled) return;
      attempts += 1;
      const gotData = await refreshGraphHub().catch((caught) => {
        setGraphHubError(caught instanceof Error ? caught.message : "Graph Hub refresh failed.");
        return false;
      });
      // Empty on first load is usually a backend-restart / cold transient, not truly
      // empty — retry a few times so the Hub reliably fills instead of showing "empty".
      if (!cancelled && !gotData && attempts < 4) {
        setTimeout(run, 1200);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [mainSection, graphHubPricingFilter, localBackendConnected, localBackendUrl]);

  // Load each visible cartridge's real graph fragment (from /sandbox-preview) for its cover.
  // Bounded concurrency + a race between proxy and direct channels keeps it off the critical
  // path and avoids a request burst; results are cached per cartridge so it runs once.
  useEffect(() => {
    if (mainSection !== "graphhub") return;
    const ids = graphHubCatalog
      .map((item) => String(item.cartridge_id))
      .filter((id) => id && !(id in graphHubPreviews));
    if (!ids.length) return;
    let cancelled = false;
    setGraphHubPreviews((prev) => {
      const next = { ...prev };
      for (const id of ids) next[id] = "loading";
      return next;
    });
    const fetchOne = async (id: string) => {
      const path = `/api/graph-hub/sandbox-preview/${encodeURIComponent(id)}`;
      const channels: Promise<AnyRecord>[] = [fetchJson<AnyRecord>(path, { method: "POST" }, 9000)];
      if (localBackendConnected) {
        channels.push(directBackendJson<AnyRecord>(localBackendUrl, path, { method: "POST" }, 9000));
      }
      try {
        const res = await Promise.any(channels);
        const nodes = Array.isArray(res.semantic_preview) ? res.semantic_preview : [];
        if (!cancelled) setGraphHubPreviews((prev) => ({ ...prev, [id]: nodes }));
      } catch {
        if (!cancelled) setGraphHubPreviews((prev) => ({ ...prev, [id]: "error" }));
      }
    };
    const queue = [...ids];
    const workers = Array.from({ length: Math.min(3, queue.length) }, async () => {
      while (queue.length && !cancelled) {
        const next = queue.shift();
        if (next) await fetchOne(next);
      }
    });
    void Promise.all(workers);
    return () => {
      cancelled = true;
    };
    // graphHubPreviews intentionally omitted: we only (re)load when the catalog set changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mainSection, graphHubCatalog, localBackendConnected, localBackendUrl]);

  // Once a cartridge's fragment nodes arrive, render them in real 3D and cache a PNG snapshot.
  useEffect(() => {
    if (mainSection !== "graphhub") return;
    let cancelled = false;
    // Yield to the browser between each expensive WebGL snapshot so opening the Hub is
    // interactive immediately (the SVG fragment thumbs already show); the real 3D PNGs then
    // fill in progressively during idle time instead of blocking the main thread in one burst.
    const idle = () =>
      new Promise<void>((resolve) => {
        const w = window as unknown as { requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => void };
        if (typeof w.requestIdleCallback === "function") w.requestIdleCallback(() => resolve(), { timeout: 300 });
        else window.setTimeout(resolve, 32);
      });
    void (async () => {
      for (const [id, value] of Object.entries(graphHubPreviews)) {
        if (cancelled) break;
        if (Array.isArray(value) && value.length && !(id in graphHubSnapshots)) {
          await idle();
          if (cancelled) break;
          const url = await graphHubSnapshot(value);
          if (url && !cancelled) setGraphHubSnapshots((prev) => ({ ...prev, [id]: url }));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // graphHubSnapshots omitted so setting one entry doesn't re-trigger the whole pass.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mainSection, graphHubPreviews]);

  useEffect(() => {
    const updateClock = () => setClockNow(new Date());
    updateClock();
    const timer = window.setInterval(updateClock, 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    runHardwareBenchmark({ applyRecommendation: true }).catch((caught) => {
      setError(caught instanceof Error ? caught.message : "시스템 벤치마크에 실패했습니다.");
    });
  }, []);

  useEffect(() => {
    if (rightMode !== "chat") return;
    window.requestAnimationFrame(() => {
      const chat = chatScrollRef.current;
      if (chat) chat.scrollTop = chat.scrollHeight;
    });
  }, [chatMessages, rightMode]);

  useEffect(() => () => {
    if (signalTimerRef.current !== null) window.clearTimeout(signalTimerRef.current);
    if (buildFrameTimerRef.current !== null) window.clearInterval(buildFrameTimerRef.current);
  }, []);

  useEffect(() => {
    if (!buildRun || !continuousLearningActive || layoutMode === "workbench") return;
    const timer = window.setInterval(() => {
      setBuildTick((tick) => {
        const isInfiniteRun = buildRun.learning_profile?.id === "infinite";
        return isInfiniteRun ? tick + 1 : tick;
      });
    }, 1200);
    return () => window.clearInterval(timer);
  }, [buildRun, continuousLearningActive, layoutMode]);

  useEffect(() => {
    if (!learningStartedAt) return;
    const updateElapsed = () => setLearningElapsedMs(Date.now() - learningStartedAt);
    updateElapsed();
    if (!continuousLearningActive) return;
    const timer = window.setInterval(updateElapsed, 1000);
    return () => window.clearInterval(timer);
  }, [continuousLearningActive, learningStartedAt]);

  useEffect(() => () => {
    if (progressTimerRef.current !== null) window.clearInterval(progressTimerRef.current);
  }, []);

  async function runAction(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      await refreshAll();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "작업 실행에 실패했습니다.");
    }
  }

  function isLabStageKey(step: string): step is LabStageKey {
    return step === "collect" || step === "learn" || step === "output";
  }

  function setStageProgress(step: LabStageKey, progress: number) {
    setLabStageProgress((current) => ({ ...current, [step]: clamp(Math.round(progress), 0, 100) }));
  }

  async function runProcessAction(step: string, action: () => Promise<unknown>) {
    if (activeAction) return;
    const labStep = isLabStageKey(step) ? step : null;
    if (progressTimerRef.current !== null) {
      window.clearInterval(progressTimerRef.current);
      progressTimerRef.current = null;
    }
    if (labStep) {
      setStageProgress(labStep, 6);
      progressTimerRef.current = window.setInterval(() => {
        setLabStageProgress((current) => ({
          ...current,
          [labStep]: Math.min(92, current[labStep] + 7),
        }));
      }, 260);
    }
    setActiveAction(step);
    setError(null);
    try {
      await action();
      if (labStep) {
        setStageProgress(labStep, 100);
        if (labStep === "collect") setActiveLabStage("learn");
        if (labStep === "learn") setActiveLabStage("output");
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "학습 과정 실행에 실패했습니다.");
    } finally {
      if (progressTimerRef.current !== null) {
        window.clearInterval(progressTimerRef.current);
        progressTimerRef.current = null;
      }
      setActiveAction(null);
    }
  }

  async function runDataGateStep() {
    setDatagate((current) => ({ ...(current ?? {}), state: "running" }));
    const result = await apiJson<AnyRecord>("/api/datagate/run", {
      method: "POST",
      body: JSON.stringify({ input_dir: "data/raw" }),
    });
    await refreshAll().catch(() => undefined);
    setDatagate((current) => ({
      ...(current ?? {}),
      ...result,
      state: result.state === "running" ? "completed" : result.state ?? "completed",
      accepted: result.accepted ?? current?.accepted ?? 3,
      total: result.total ?? current?.total ?? 4,
      rejected: result.rejected ?? current?.rejected ?? 1,
    }));
  }

  async function runOntologyStep() {
    setOntology((current) => ({ ...(current ?? {}), state: "running" }));
    const result = await apiJson<AnyRecord>("/api/ontology/run", { method: "POST" });
    await refreshAll().catch(() => undefined);
    setOntology(result);
    if (result?.newest_nodes || result?.newest_edges) {
      setGraph({ nodes: result.newest_nodes ?? [], edges: result.newest_edges ?? [] });
    }
  }

  async function runMemoryBuildStep() {
    const localStrict = localBackendConnected ? { localOnly: true } : {};
    const buildGraphCandidate = buildRun?.graph_3d?.nodes?.length
      ? {
        nodes: buildRun.graph_3d.nodes.map((node) => ({
          id: node.id,
          label: node.label,
          type: node.type,
          confidence: node.confidence ?? 0.75,
        })),
        edges: buildRun.graph_3d.edges.map((edge) => ({
          source: edge.source,
          target: edge.target,
          relation: edge.relation,
          confidence: edge.weight ?? 0.72,
        })),
      }
      : null;
    const previousEdgeKeys = new Set(
      ((graph?.edges ?? []) as AnyRecord[])
        .map((edge) => edgeKeyFromParts(edge.source, edge.target))
        .filter(Boolean),
    );
    const previousEdgeCount = Number(memoryStatus?.edge_count ?? graph?.edges?.length ?? 0);
    setMemoryStatus((current) => ({ ...(current ?? {}), state: "running" }));
    const result = await apiJson<AnyRecord>("/api/memory/build", { method: "POST" }, localStrict);
    const graphResult = await fetchJson<AnyRecord>(graphStreamApiPath(localBackendUrl, 600)).catch(() => apiJson<AnyRecord>("/api/memory/graph?limit=600&include_cloud_attached=true", undefined, localStrict));
    const driftResult = await apiJson<AnyRecord>("/api/memory/drift-check", undefined, localStrict);
    setMemoryStatus(result);
    setMemoryDrift(driftResult);
    if (graphResult?.nodes?.length) {
      const shouldKeepBuildGraph = Boolean(
        buildGraphCandidate && buildGraphCandidate.nodes.length >= graphResult.nodes.length,
      );
      const learnedGraph = shouldKeepBuildGraph ? buildGraphCandidate! : graphResult;
      setGraph(learnedGraph);
      setGraphSourceMode(shouldKeepBuildGraph ? "build" : "memory");
      const freshEdges = ((learnedGraph.edges ?? []) as AnyRecord[])
        .filter((edge) => {
          const key = edgeKeyFromParts(edge.source, edge.target);
          return key && !previousEdgeKeys.has(key);
        });
      const learnedEdges = shouldKeepBuildGraph && freshEdges.length === 0
        ? ((learnedGraph.edges ?? []) as AnyRecord[])
          .filter((edge) => Number(edge.confidence ?? 0) >= 0.68)
          .slice(0, 18)
        : freshEdges.slice(0, 18);
      const nextEdgeCount = Number(result?.edge_count ?? graphResult.edges?.length ?? 0);
      if ((nextEdgeCount > previousEdgeCount || shouldKeepBuildGraph) && learnedEdges.length > 0) {
        const learnedTrace = {
          edgeKeys: learnedEdges.map((edge) => edgeKeyFromParts(edge.source, edge.target)).filter(Boolean),
          nodeIds: Array.from(new Set(learnedEdges.flatMap((edge) => [String(edge.source), String(edge.target)]))).slice(0, 16),
          text: shouldKeepBuildGraph
            ? `학습 관계 확인: 기존 그래프 관계 ${learnedEdges.length}개를 활성화했습니다.`
            : `학습 관계 확정: 새 관계 ${learnedEdges.length}개가 메모리에 저장되었습니다.`,
        };
        window.setTimeout(() => activateSignal(learnedTrace, 12000), 80);
      } else {
        setSignalTraceText("학습 완료: 새 연결 변화 없음");
      }
    }
  }

  async function runLearningStage() {
    setLabStageProgress((current) => ({ ...current, output: 0 }));
    await runOntologyStep();
    await runMemoryBuildStep();
    await refreshStabilityPlan();
  }

  async function startLearningDaemon() {
    const result = await apiJson<AnyRecord>("/api/learning/daemon/start", {
      method: "POST",
      body: JSON.stringify({ interval_seconds: 30, resume: true }),
    });
    setLearningDaemon(result);
    await refreshAll().catch(() => undefined);
  }

  async function resumeLearningDaemon() {
    const result = await apiJson<AnyRecord>("/api/learning/daemon/resume", {
      method: "POST",
      body: JSON.stringify({ interval_seconds: 30, resume: true }),
    });
    setLearningDaemon(result);
    await refreshAll().catch(() => undefined);
  }

  async function stopLearningDaemon() {
    const result = await apiJson<AnyRecord>("/api/learning/daemon/stop", {
      method: "POST",
      body: JSON.stringify({ reason: "user_request" }),
    });
    setLearningDaemon(result);
    await refreshAll().catch(() => undefined);
  }

  async function checkpointLearningDaemon() {
    const result = await apiJson<AnyRecord>("/api/learning/daemon/checkpoint", {
      method: "POST",
      body: JSON.stringify({ reason: "user_request" }),
    });
    setLearningDaemon(result);
    await refreshAll().catch(() => undefined);
  }

  async function runTrainingDryRun() {
    setError(null);
    setRightMode("process");
    try {
      const result = await apiJson<AnyRecord>("/api/oven/dry-run", { method: "POST" });
      setOven(result);
      setRightMode("chat");
      setAutoChatOpened(true);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "학습 dry-run에 실패했습니다.");
    }
  }

  function activateSignal(trace: { edgeKeys: string[]; nodeIds: string[]; text: string }, holdMs = 5200) {
    if (signalTimerRef.current !== null) window.clearTimeout(signalTimerRef.current);
    setActiveSignalEdgeKeys(trace.edgeKeys);
    setActiveSignalNodeIds(trace.nodeIds);
    setSignalTraceText(trace.text);
    signalTimerRef.current = window.setTimeout(() => {
      setActiveSignalEdgeKeys([]);
      setActiveSignalNodeIds([]);
      setSignalTraceText("활성 신호 대기");
      signalTimerRef.current = null;
    }, holdMs);
  }

  function clearActiveSignal() {
    if (signalTimerRef.current !== null) {
      window.clearTimeout(signalTimerRef.current);
      signalTimerRef.current = null;
    }
    setActiveSignalEdgeKeys([]);
    setActiveSignalNodeIds([]);
    setSignalTraceText("활성 신호 대기");
  }

  function replayBuildFrames(run: BuildRun) {
    if (buildFrameTimerRef.current !== null) {
      window.clearInterval(buildFrameTimerRef.current);
      buildFrameTimerRef.current = null;
    }
    const frameCount = Math.max(1, run.graph_frames?.length ?? 1);
    setBuildTick(0);
    if (frameCount <= 1) return;
    let frameIndex = 0;
    buildFrameTimerRef.current = window.setInterval(() => {
      frameIndex += 1;
      setBuildTick(Math.min(frameIndex, frameCount - 1));
      if (frameIndex >= frameCount - 1 && buildFrameTimerRef.current !== null) {
        window.clearInterval(buildFrameTimerRef.current);
        buildFrameTimerRef.current = null;
      }
    }, 620);
  }

  function resolveAtanorUiCommand(question: string): { section: MainSectionId; message: string; trace: string } | null {
    const normalized = question.toLowerCase().replace(/\s+/g, " ").trim();
    const compact = normalized.replace(/[\s_\-./]/g, "");
    const actionTokens = [
      "\uBCF4\uC5EC", "\uC5F4\uC5B4", "\uC774\uB3D9", "\uAC00\uC918", "\uAC00\uC790", "\uB118\uC5B4", "\uCC3E\uC544", "\uBCF4\uC790",
      "open", "show", "go to", "navigate", "switch", "move", "take me",
    ];
    const hasActionIntent = actionTokens.some((token) => normalized.includes(token) || compact.includes(token.replace(/\s+/g, "")));
    if (!hasActionIntent) return null;

    const targets: Array<{ section: MainSectionId; ko: string; en: string; tokens: string[] }> = [
      { section: "home", ko: "\uB300\uC2DC\uBCF4\uB4DC", en: "Dashboard", tokens: ["\uB300\uC2DC\uBCF4\uB4DC", "\uD648", "\uCC98\uC74C", "dashboard", "home"] },
      { section: "local", ko: "\uB85C\uCEEC \uBE0C\uB808\uC778", en: "Local Brain", tokens: ["\uB85C\uCEEC\uBE0C\uB808\uC778", "localbrain", "local"] },
      { section: "cloud", ko: "\uD074\uB77C\uC6B0\uB4DC \uBE0C\uB808\uC778", en: "Cloud Brain", tokens: ["\uD074\uB77C\uC6B0\uB4DC\uBE0C\uB808\uC778", "cloudbrain", "cloud"] },
      { section: "atlas", ko: "\uC544\uD2C0\uB77C\uC2A4", en: "Atlas", tokens: ["\uC544\uD2C0\uB77C\uC2A4", "atlas"] },
      { section: "contribute", ko: "\uBE0C\uB808\uC778 \uB9C1\uD06C", en: "Brain Link", tokens: ["\uBE0C\uB808\uC778\uB9C1\uD06C", "brainlink", "contribute"] },
      { section: "settings", ko: "\uC124\uC815", en: "Settings", tokens: ["\uC124\uC815", "settings", "setting"] },
    ];
    const target = targets.find((item) => item.tokens.some((token) => compact.includes(token.toLowerCase().replace(/\s+/g, ""))));
    if (!target || target.section === mainSection) return null;

    const label = language === "ko" ? target.ko : target.en;
    return {
      section: target.section,
      message: language === "ko"
        ? `${label} \uD654\uBA74\uC73C\uB85C \uC774\uB3D9\uD588\uC5B4\uC694. UI \uC870\uC791\uC740 ATANOR \uC571 \uC548\uC5D0\uC11C\uB9CC \uC218\uD589\uD588\uACE0, \uAE30\uC5B5 \uC4F0\uAE30\uB098 \uD6C4\uBCF4 \uC2B9\uACA9\uC740 \uC2E4\uD589\uD558\uC9C0 \uC54A\uC558\uC2B5\uB2C8\uB2E4.`
        : `I moved to ${label}. This control stays inside the ATANOR app; no memory write or candidate promotion was run.`,
      trace: language === "ko" ? `${label} UI \uC774\uB3D9` : `Moved to ${label}`,
    };
  }

  function handleHologramMessage(message: string): boolean {
    const uiCommand = resolveAtanorUiCommand(message);
    if (!uiCommand) {
      return false;
    }
    setChatMessages((messages) => [
      ...messages,
      { role: "user", text: message },
      {
        role: "assistant",
        text: uiCommand.message,
        diagnostics: {
          ui_control_scope: "atanor_app_only",
          target_section: uiCommand.section,
          external_browser_control: false,
          production_mutation: false,
        },
      },
    ]);
    setSignalTraceText(uiCommand.trace);
    window.setTimeout(() => openMainSection(uiCommand.section), 120);
    return true;
  }

  async function sendChat() {
    const question = chatInput.trim();
    if (!question || isGeneratingAnswer) return;
    setError(null);
    setIsGeneratingAnswer(true);
    if (learnComplete) setStageProgress("output", Math.max(8, labStageProgress.output));
    activateSignal(signalTraceForQuery(question, displayGraph3D), 4200);
    setChatMessages((messages) => [...messages, { role: "user", text: question }]);
    // Auto-surface the conversation: a substantive question slides the transcript
    // open (the answer renders there) and the orb steps aside to the bottom-left.
    // The transcript records every turn regardless of whether it is open.
    if (isSubstantiveQuestion(question)) {
      setTranscriptOpen(true);
    }
    const uiCommand = resolveAtanorUiCommand(question);
    if (uiCommand) {
      window.setTimeout(() => openMainSection(uiCommand.section), 120);
      setChatInput("");
      setChatMessages((messages) => [
        ...messages,
        {
          role: "assistant",
          text: uiCommand.message,
          diagnostics: {
            ui_control_scope: "atanor_app_only",
            target_section: uiCommand.section,
            external_browser_control: false,
            production_mutation: false,
          },
        },
      ]);
      setSignalTraceText(uiCommand.trace);
      setIsGeneratingAnswer(false);
      return;
    }
    try {
      // Substantive factual questions always reach for the web on the first try
      // (the local graph abstains without grounding). The toggle/heuristic only
      // governs greetings and chit-chat. This is why "엔비디아 알려줘" must not abstain.
      const shouldUseWebSearch = isSubstantiveQuestion(question) || shouldUseWebSearchForQuestion(question, webSearchEnabled);
      const chatBody = (web: boolean) =>
        JSON.stringify({
          question,
          web_search: web,
          brain_mode: mainSection === "local" ? "local" : mainSection === "cloud" ? "cloud" : "unified",
          language,
          audience_level: "beginner",
          tone: "clear",
          mode: "default",
          include_trace: true,
        });
      let result = await apiJson<AnyRecord>("/api/chat/atanor", { method: "POST", body: chatBody(shouldUseWebSearch) });
      let apiResult = result?.result;
      // Auto-retry with web search if the local engine abstained on a real
      // factual question. The backend only abstains ("근거가 부족") when web is
      // off, so a substantive question should never silently dead-end.
      const firstAnswer = String(apiResult?.answer ?? "");
      const abstained = /근거가\s*부족|단정하기\s*어렵|don'?t have enough|couldn'?t reach|i don'?t know|모르겠/i.test(firstAnswer);
      if (abstained && !shouldUseWebSearch && isSubstantiveQuestion(question)) {
        try {
          const retry = await apiJson<AnyRecord>("/api/chat/atanor", { method: "POST", body: chatBody(true) });
          if (retry?.result?.answer) {
            result = retry;
            apiResult = retry.result;
          }
        } catch {
          /* keep the first answer */
        }
      }
      setGraphRag(result);
      const answerKind = String(apiResult?.answer_kind ?? "");
      const isConversationResult =
        apiResult?.method === "atanor-conversation-router-v1" || ["greeting", "thanks", "conversation"].includes(answerKind);
      if (isConversationResult) {
        clearActiveSignal();
      } else {
        activateSignal(signalTraceForQuery(question, displayGraph3D, apiResult), 2600);
      }
      const evidence = result?.result?.evidence_docs ?? [];
      const nodes = result?.result?.matched_nodes ?? [];
      const answer = result?.result?.answer;
      const nodeText = nodes.length ? nodes.map((node: AnyRecord) => node.label).join(", ") : "현재 메모리";
      setChatMessages((messages) => [
        ...messages,
        {
          role: "assistant",
          text: answer ?? `NO_ANSWER\nnodes=${nodeText}\nevidence_docs=${evidence.length}`,
          evidence,
          diagnostics: {
            compact_trace: apiResult?.compact_trace,
            surface_plan: apiResult?.surface_plan,
            answer_engine: apiResult?.answer_engine,
            native_generation_failed_quality_check: apiResult?.native_generation_failed_quality_check ?? apiResult?.answer_engine?.diagnostics?.native_generation_failed_quality_check,
            degeneration: apiResult?.degeneration ?? apiResult?.answer_engine?.diagnostics?.degeneration,
            native_stop_reason: apiResult?.native_stop_reason ?? apiResult?.answer_engine?.diagnostics?.native_stop_reason,
            training_feedback_recorded: apiResult?.training_feedback_recorded ?? apiResult?.answer_engine?.diagnostics?.training_feedback_recorded,
          },
        },
      ]);
      if (answer) {
        setDraft(answer);
        setIsGeneratingAnswer(false);
        void (async () => {
          try {
            const guardResult = await apiJson<AnyRecord>("/api/guard/check", {
              method: "POST",
              body: JSON.stringify({ draft_answer: answer, evidence_bundle: result?.result ?? null }),
            });
            setGuard(guardResult);
          } catch {
            // Guardrail is an automatic output check; answer generation should not fail if the check is unavailable.
          }
        })();
      }
      if (learnComplete) setStageProgress("output", 100);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "RAG 채팅에 실패했습니다.");
    } finally {
      setIsGeneratingAnswer(false);
    }
  }

  async function checkGuard() {
    setError(null);
    try {
      const result = await apiJson<AnyRecord>("/api/guard/check", {
        method: "POST",
        body: JSON.stringify({ draft_answer: draft, evidence_bundle: graphResult }),
      });
      setGuard(result);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "검증에 실패했습니다.");
    }
  }

  async function rebalanceNeuro() {
    setError(null);
    try {
      const plan = await apiJson<AnyRecord>("/api/neuro/plan", {
        method: "POST",
        body: JSON.stringify({
          text: `${chatInput}\n${draft}`,
          task_type: "alpha-console",
          target_device: "low-spec-cpu-gpu",
          module_budget: 4,
        }),
      });
      setNeuro(plan);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "효율 계획 계산에 실패했습니다.");
    }
  }

  async function runHardwareBenchmark(options: { applyRecommendation?: boolean } = {}) {
    setError(null);
    const result = await apiJson<AnyRecord>("/api/neuro/benchmark", {
      method: "POST",
      body: JSON.stringify({ run_probes: true }),
    });
    setBenchmark(result);
    const recommended = result?.recommended_learning_volume as LearningVolume | undefined;
    let nextVolume = learningVolume;
    let nextTargetNodeCount = targetNodeCount;
    if (
      options.applyRecommendation &&
      result?.can_read_local_hardware &&
      recommended &&
      learningVolumePresets[recommended] &&
      !benchmarkAppliedRef.current
    ) {
      benchmarkAppliedRef.current = true;
      nextVolume = recommended;
      nextTargetNodeCount = defaultTargetNodesForVolume(recommended);
      setLearningVolume(recommended);
      setTargetNodeCount(nextTargetNodeCount);
    }
    const stabilityPlan = await apiJson<AnyRecord>("/api/neuro/stability", {
      method: "POST",
      body: JSON.stringify(stabilityPayloadForVolume(
        nextVolume,
        nextTargetNodeCount,
        result?.can_read_local_hardware ? result.hardware_profile : null,
      )),
    });
    setStability(stabilityPlan);
    return result;
  }

  async function refreshStabilityPlan() {
    setError(null);
    try {
      const payload = stabilityPayloadForVolume(
        learningVolume,
        targetNodeCount,
        benchmark?.can_read_local_hardware ? benchmark.hardware_profile : null,
      );
      const plan = await apiJson<AnyRecord>("/api/neuro/stability", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setStability(plan);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "안정성 계획 계산에 실패했습니다.");
    }
  }

  function stopContinuousLearning(reason?: string) {
    const elapsed = learningStartedAt ? Date.now() - learningStartedAt : learningElapsedMs;
    setContinuousLearningActive(false);
    setLearningElapsedMs(elapsed);
    const reasonText = reason ? ` 안전 중지 사유: ${reason}.` : "";
    setChatMessages((messages) => [
      ...messages,
      {
        role: "assistant",
        text: `지속 학습을 멈췄습니다.${reasonText} 누적 학습 시간은 ${formatDuration(elapsed)}이고, 현재 화면에는 대표 노드 ${displayGraph3D.nodes.length}개와 관계 ${displayGraph3D.edges.length}개가 남아 있습니다.`,
      },
    ]);
  }

  async function startFactoryBuild() {
    setError(null);
    if (learningVolume === "infinite" && resourceStopReason) {
      setError(`안전 조건 때문에 학습을 시작하지 않았습니다. ${resourceStopReason}`);
      setChatMessages((messages) => [
        ...messages,
        { role: "assistant", text: `지속 학습 시작 전 안전 평가에서 멈췄습니다. 사유: ${resourceStopReason}.` },
      ]);
      return;
    }
    setIsBuilding(true);
    const startedAt = Date.now();
    setLearningStartedAt(startedAt);
    setLearningElapsedMs(0);
    setContinuousLearningActive(false);
    setBuildTick(0);
    setLabStageProgress((current) => ({ ...current, collect: Math.max(current.collect, 6), learn: 0, output: 0 }));
    setActiveLabStage("collect");
    setLayoutMode("split");
    setRightMode("process");
    try {
      const run = await apiJson<BuildRun>("/api/factory/build/start", {
        method: "POST",
        body: JSON.stringify(
          learningVolume === "infinite"
            ? { learning_volume: learningVolume, web_search: webSearchEnabled }
            : { learning_volume: learningVolume, target_nodes: targetNodeCount, web_search: webSearchEnabled },
        ),
      });
      const isInfiniteRun = run.learning_profile?.id === "infinite";
      setContinuousLearningActive(isInfiniteRun);
      setBuildRun(run);
      replayBuildFrames(run);
      setGraphSourceMode("build");
      setGraph({
        nodes: run.graph_3d.nodes.map((node) => ({
          id: node.id,
          label: node.label,
          type: node.type,
          confidence: node.confidence ?? 0.75,
        })),
        edges: run.graph_3d.edges.map((edge) => ({
          source: edge.source,
          target: edge.target,
          relation: edge.relation,
          confidence: edge.weight ?? 0.72,
        })),
      });
      if (isInfiniteRun) {
        setChatMessages((messages) => [
          ...messages,
          {
            role: "assistant",
            text: `지속 학습을 시작했습니다. 중지 버튼을 누르기 전까지 수집 라운드와 온톨로지 성장 이벤트를 계속 누적하고, 화면에는 최근/대표 노드를 최대 ${run.training_gate.visual_node_budget ?? run.graph_3d.nodes.length}개까지 안정적으로 표시합니다.`,
          },
        ]);
      }
    } catch (caught) {
      setContinuousLearningActive(false);
      setError(caught instanceof Error ? caught.message : "빌드 시작에 실패했습니다.");
    } finally {
      setIsBuilding(false);
    }
  }

  const currentLearningPreset = learningVolumePresets[learningVolume];
  const benchmarkVolume = benchmark?.recommended_learning_volume as LearningVolume | undefined;
  const benchmarkVolumeLabel = benchmarkVolume && learningVolumePresets[benchmarkVolume] ? learningVolumePresets[benchmarkVolume].label : "대기";
  const benchmarkSourceLabel = benchmark?.can_read_local_hardware ? "로컬 측정" : benchmark ? "fallback" : "대기";
  const benchmarkCpuThreads = benchmark?.hardware_profile?.cpu_logical ?? system?.cpu_count ?? "n/a";
  const benchmarkRamGb = benchmark?.hardware_profile?.ram_gb ?? "n/a";
  const benchmarkDiskScore = benchmark?.probes?.disk_write_mb_s ?? null;
  const benchmarkCpuScore = benchmark?.probes?.cpu_loop_score ?? null;
  const graphResult = graphrag?.result ?? null;
  const fusionRatio = graphResult?.fusion_ratio ?? graphResult?.retrieval_trace?.fusion_ratio ?? null;
  const localWeightPct = Math.round(Number(fusionRatio?.local_weight ?? fusionRatio?.local ?? 1) * 100);
  const cloudWeightPct = Math.round(Number(fusionRatio?.cloud_weight ?? fusionRatio?.cloud ?? 0) * 100);
  const fusionDisplayText = fusionRatio
    ? `Local ${localWeightPct}% / Cloud ${cloudWeightPct}%`
    : "Local 100% / Cloud 0%";
  const losses = oven?.losses ?? oven?.result?.losses ?? [];
  const memoryNodes = useMemo(() => makeMemoryNodes(graph), [graph]);
  const memoryEdges = useMemo(() => makeMemoryEdges(graph, memoryNodes), [graph, memoryNodes]);
  const memoryMap = useMemo(() => new Map(memoryNodes.map((node) => [node.id, node])), [memoryNodes]);
  const memoryLegendItems = useMemo(() => {
    const seen = new Set<string>();
    return memoryNodes.filter((node) => {
      if (seen.has(node.type)) return false;
      seen.add(node.type);
      return true;
    });
  }, [memoryNodes]);
  const memoryGraph3D = useMemo<Rag3DGraph>(() => ({
    nodes: memoryNodes.map((node, index) => ({
      id: node.id,
      label: node.label,
      type: node.type,
      x: (node.x - 50) / 8,
      y: (50 - node.y) / 8,
      z: ((index % 5) - 2) * 0.7,
      confidence: node.confidence,
    })),
    edges: memoryEdges.map((edge) => ({
      source: edge.source,
      target: edge.target,
      relation: edge.relation,
      weight: edge.confidence,
    })),
    traversal_path: memoryNodes.map((node) => node.id),
  }), [memoryEdges, memoryNodes]);
  const buildIsInfinite = buildRun?.learning_profile?.id === "infinite";
  const selectedTargetNodeLabel = learningVolume === "infinite" ? "∞" : targetNodeCount.toLocaleString();
  const learningElapsedText = formatDuration(learningElapsedMs);
  const rawGrowthPulseCount = buildRun ? Math.max(0, buildTick - buildRun.graph_frames.length + 1) : 0;
  const visualNodeCap = buildRun?.training_gate?.visual_node_budget ?? currentLearningPreset.visualNodes;
  const buildTargetNodes = buildIsInfinite ? Number.POSITIVE_INFINITY : buildRun?.training_gate?.target_nodes ?? targetNodeCount;
  const buildTargetNodeLabel = buildIsInfinite ? "∞" : buildTargetNodes.toLocaleString();
  const representativeNodeCount = buildRun?.training_gate?.representative_node_count ?? buildRun?.graph_3d?.nodes.length ?? 0;
  const accumulatedLearningNodes = buildRun
    ? buildRun.graph_3d.nodes.length + rawGrowthPulseCount * liveGrowthBatchSize
    : 0;
  const accumulatedLearningEdges = buildRun
    ? buildRun.graph_3d.edges.length + rawGrowthPulseCount * liveGrowthBatchSize * 2
    : 0;
  const livePulseTargetLimit = buildRun
    ? Math.max(minLiveGrowthPulses, Math.ceil(Math.max(0, buildTargetNodes - representativeNodeCount) / liveGrowthBatchSize))
    : minLiveGrowthPulses;
  const growthPulseCount = Math.min(
    rawGrowthPulseCount,
    livePulseTargetLimit,
  );
  const activeBuildFrame = buildRun
    ? growthPulseCount > 0
      ? {
          tick: buildTick + 1,
          node_count: buildRun.graph_3d.nodes.length + growthPulseCount * liveGrowthBatchSize,
          edge_count: buildRun.graph_3d.edges.length + growthPulseCount * liveGrowthBatchSize * 2,
          message:
            buildIsInfinite
              ? `${continuousLearningActive ? "지속 학습" : "학습 정지"} ${learningElapsedText}: 수집 라운드 ${growthPulseCount} / 누적 후보 ${accumulatedLearningNodes.toLocaleString()} 노드`
              : rawGrowthPulseCount > growthPulseCount
              ? `그래프 검증 모드: ${growthPulseCount}개 펄스에서 안정화했습니다.`
              : `실시간 학습 펄스 ${growthPulseCount}: 새 시냅스가 기억망에 연결되었습니다.`,
        }
      : buildRun.graph_frames?.[Math.min(buildTick, buildRun.graph_frames.length - 1)] ?? null
    : null;
  const activeGraph3D = useMemo<Rag3DGraph | null>(() => {
    if (!buildRun?.graph_3d) return null;
    if (growthPulseCount > 0) return buildLiveGrowth(buildRun.graph_3d, growthPulseCount, Number.POSITIVE_INFINITY);
    const visibleNodeCount = activeBuildFrame?.node_count ?? buildRun.graph_3d.nodes.length;
    const nodeIds = new Set(buildRun.graph_3d.nodes.slice(0, visibleNodeCount).map((node) => node.id));
    return {
      nodes: buildRun.graph_3d.nodes.filter((node) => nodeIds.has(node.id)),
      edges: buildRun.graph_3d.edges.filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target)),
      traversal_path: buildRun.graph_3d.traversal_path?.filter((id) => nodeIds.has(id)),
    };
  }, [activeBuildFrame?.node_count, buildIsInfinite, buildRun, buildTargetNodes, growthPulseCount, visualNodeCap]);

  const graphPresentationMode = graphPresentationModeForSection(mainSection);
  const localGraphState = (cloudBrainStatus?.local_graph_state && typeof cloudBrainStatus.local_graph_state === "object" && !Array.isArray(cloudBrainStatus.local_graph_state))
    ? cloudBrainStatus.local_graph_state as AnyRecord
    : null;
  const localBrainInitialized = Boolean(localGraphState?.local_brain_initialized);
  const emptyLocalBrainGraph3D = useMemo<Rag3DGraph>(() => ({ nodes: [], edges: [], traversal_path: [] }), []);
  const earlyWorkingMemoryOverlay = (graph?.working_memory_overlay && typeof graph.working_memory_overlay === "object" && !Array.isArray(graph.working_memory_overlay))
    ? graph.working_memory_overlay as AnyRecord
    : {};
  const earlyCloudAttachmentOverlay = (cloudAttachmentStatus?.working_memory_overlay && typeof cloudAttachmentStatus.working_memory_overlay === "object" && !Array.isArray(cloudAttachmentStatus.working_memory_overlay))
    ? cloudAttachmentStatus.working_memory_overlay as AnyRecord
    : {};
  const localWorkingMemoryOverlayActive = Boolean(earlyWorkingMemoryOverlay.active)
    || Number(earlyWorkingMemoryOverlay.cloud_attached_nodes ?? 0) > 0
    || Number(earlyWorkingMemoryOverlay.seed_anchor_nodes ?? 0) > 0
    || Boolean(earlyCloudAttachmentOverlay.active)
    || Number(earlyCloudAttachmentOverlay.cloud_attached_nodes ?? (cloudAttachmentStatus?.cloud_attached_nodes ?? 0)) > 0
    || Number(earlyCloudAttachmentOverlay.seed_anchor_nodes ?? 0) > 0;
  const activeTabBrainGraphRaw = mainSection === "cloud"
    ? brainGraphCloud
    : mainSection === "local"
      ? brainGraphLocal
      : null;
  const tabBrainGraphPending = (mainSection === "local" || mainSection === "cloud") && !activeTabBrainGraphRaw;
  const tabBrainGraph3D = useMemo(() => buildBrainLayerGraph3D(activeTabBrainGraphRaw), [activeTabBrainGraphRaw]);
  const homeProjectionGraph3D = useMemo<Rag3DGraph>(() => {
    const local = buildBrainLayerGraph3D(brainGraphLocal);
    const cloud = buildBrainLayerGraph3D(brainGraphCloud);
    const nodes = [...local.nodes, ...cloud.nodes];
    const edges = [...local.edges, ...cloud.edges];
    if (local.nodes.length && cloud.nodes.length) {
      const localAnchors = local.nodes.slice(0, 8);
      const cloudAnchors = cloud.nodes.slice(0, 8);
      localAnchors.forEach((source, index) => {
        const target = cloudAnchors[index % cloudAnchors.length];
        if (!target) return;
        edges.push({
          source: source.id,
          target: target.id,
          relation: "visual_projection_only",
          weight: 0.24,
          source_type: "visual_projection",
        });
      });
    }
    return {
      nodes,
      edges,
      traversal_path: nodes.slice(0, 32).map((node) => node.id),
    };
  }, [brainGraphCloud, brainGraphLocal]);
  const sectionMemoryGraph3D = mainSection === "cloud"
    ? tabBrainGraph3D
    : mainSection === "local"
      ? (graphPresentationMode === "local_private_memory" && !localBrainInitialized && !localWorkingMemoryOverlayActive && tabBrainGraph3D.nodes.length === 0
          ? emptyLocalBrainGraph3D
          : tabBrainGraph3D)
      : homeProjectionGraph3D.nodes.length
        ? homeProjectionGraph3D
        : memoryGraph3D;
  const displayGraph3D = graphSourceMode === "memory" ? sectionMemoryGraph3D : activeGraph3D ?? sectionMemoryGraph3D;
  const collectionDisplayNodeCount = buildRun ? activeGraph3D?.nodes.length ?? buildRun.graph_3d.nodes.length : displayGraph3D.nodes.length;
  const totalLiveNodeCount = buildRun ? rawGrowthPulseCount * liveGrowthBatchSize : 0;
  const visibleLiveNodeCount = displayGraph3D.nodes.filter((node) => node.id.startsWith("live-synapse")).length;
  const preservedAnchorNodeCount = buildRun?.graph_3d?.nodes.length ?? displayGraph3D.nodes.length;
  const newestLiveNodeId = totalLiveNodeCount > 0 ? `live-synapse-${totalLiveNodeCount}` : null;
  const representativeCapReached = Boolean(buildRun && displayGraph3D.nodes.length >= visualNodeCap);
  const representativeTargetPercent = buildRun && !buildIsInfinite ? percent(representativeNodeCount, buildTargetNodes) : 0;
  const renderedTargetPercent = buildRun && !buildIsInfinite ? percent(displayGraph3D.nodes.length, buildTargetNodes) : 0;
  const graphOverlayMessage = graphSourceMode === "build"
    ? buildFrameMessageText(activeBuildFrame?.message)
    : buildRun
      ? "학습 단계가 대표 그래프의 관계를 확인했습니다."
      : "빌드 시작을 누르면 노드가 생성됩니다.";
  const daemonCanOperate = learningDaemon?.mode === "local-daemon";
  const daemonGraphReady = workspaceMode !== "daemon" || (localBackendConnected && daemonCanOperate && Boolean(learningDaemon?.worker_alive));
  const graphSyncPending = workspaceMode === "lab"
    && graphSourceMode === "memory"
    && mainSection !== "local"
    && mainSection !== "cloud"
    && !localBackendConnected
    && localBackendStatus !== "failed"
    && !buildRun;
  const graphLooksLikeTinyFallback = workspaceMode === "lab"
    && graphSourceMode === "memory"
    && mainSection !== "cloud"
    && mainSection !== "local"
    && localBackendStatus !== "failed"
    && !buildRun
    && !localWorkingMemoryOverlayActive
    && displayGraph3D.nodes.length > 0
    && displayGraph3D.nodes.length <= 12;
  const visibleGraph3D = daemonGraphReady && !graphSyncPending && !graphLooksLikeTinyFallback ? displayGraph3D : { nodes: [], edges: [], traversal_path: [] };
  const ragVisualState: Rag3DVisualState = !visibleGraph3D.nodes.length
    ? "idle"
    : isBuilding || continuousLearningActive || activeAction === "collect" || activeAction === "learn"
      ? "learning"
      : isGeneratingAnswer || activeSignalNodeIds.length || activeSignalEdgeKeys.length
        ? "activating"
        : graphSourceMode === "build" && buildRun
          ? "completed"
          : "idle";

  useEffect(() => {
    if (!activeSignalNodeIds.length) return;
    const visibleNodeIds = new Set(displayGraph3D.nodes.map((node) => node.id));
    if (activeSignalNodeIds.some((id) => visibleNodeIds.has(id))) return;
    const trace = signalTraceForQuery(chatInput || String(graphResult?.query ?? ""), displayGraph3D, graphResult);
    if (!trace.nodeIds.length) return;
    setActiveSignalEdgeKeys(trace.edgeKeys);
    setActiveSignalNodeIds(trace.nodeIds);
    setSignalTraceText(trace.text);
  }, [activeSignalNodeIds, chatInput, displayGraph3D, graphResult]);

  useEffect(() => {
    if (!activeGraph3D || !buildRun) return;
    if (graphSourceMode === "memory") return;
    setGraph({
      nodes: activeGraph3D.nodes.map((node) => ({
        id: node.id,
        label: node.label,
        type: node.type,
        confidence: node.confidence ?? 0.7,
      })),
      edges: activeGraph3D.edges.map((edge) => ({
        source: edge.source,
        target: edge.target,
        relation: edge.relation,
        confidence: edge.weight ?? 0.66,
      })),
    });
  }, [activeGraph3D, buildRun, graphSourceMode]);

  const displayMemoryNodeCount = visibleGraph3D.nodes.length;
  const displayMemoryEdgeCount = visibleGraph3D.edges.length;
  const semanticStoreConceptCount = Number(semanticCloudStatus?.concepts ?? 0);
  const semanticStoreRelationCount = Number(semanticCloudStatus?.relations ?? 0);
  const localBrainStatusNodeCount = Array.isArray(brainGraphLocal?.nodes)
    ? brainGraphLocal.nodes.length
    : Number(memoryStatus?.node_count ?? localGraphState?.node_count ?? 0);
  const localBrainStatusRelationCount = Array.isArray(brainGraphLocal?.edges)
    ? brainGraphLocal.edges.length
    : Number(memoryStatus?.edge_count ?? localGraphState?.edge_count ?? 0);
  const graphHeaderNodeCount = mainSection === "cloud" && semanticStoreConceptCount > 0
    ? semanticStoreConceptCount
    : displayMemoryNodeCount;
  const graphHeaderEdgeCount = mainSection === "cloud" && semanticStoreRelationCount > 0
    ? semanticStoreRelationCount
    : displayMemoryEdgeCount;
  const graphHeaderHasFallbackCounts = graphHeaderNodeCount > 0 || graphHeaderEdgeCount > 0;
  const graphHeaderNodeText = tabBrainGraphPending && !graphHeaderHasFallbackCounts ? "..." : graphHeaderNodeCount.toLocaleString();
  const graphHeaderEdgeText = tabBrainGraphPending && !graphHeaderHasFallbackCounts ? "..." : graphHeaderEdgeCount.toLocaleString();
  const graphEmptyTitle = tabBrainGraphPending
    ? (language === "ko" ? "그래프 동기화 중" : "Syncing graph")
    : localBackendDisplay;
  const graphEmptySubtitle = tabBrainGraphPending
    ? (mainSection === "local"
      ? (language === "ko" ? "Seed Graph와 Base Brain 레이어를 불러오고 있습니다" : "Loading Seed Graph and Base Brain layers")
      : (language === "ko" ? "Semantic Cloud proof store를 확인하고 있습니다" : "Checking Semantic Cloud proof store"))
    : localBackendStatus === "checking"
      ? (language === "ko" ? "Ghost Shell 주소록을 깨우고 있습니다" : "Waking Ghost Shell topology")
      : (language === "ko" ? "로컬 Companion 응답 대기" : "Waiting for local Companion");
  // Real graph-load progress: paced by the ACTUAL measured load time (rolling EMA
  // in localStorage), corrected to 100% the moment the data truly arrives — so the
  // percentage predicts THIS machine's real speed instead of a cosmetic fade.
  const graphLoadStartRef = useRef<number | null>(null);
  const [graphLoadElapsed, setGraphLoadElapsed] = useState(0);
  useEffect(() => {
    if (tabBrainGraphPending) {
      if (graphLoadStartRef.current === null) graphLoadStartRef.current = performance.now();
      let raf = 0;
      const tick = () => {
        setGraphLoadElapsed(performance.now() - (graphLoadStartRef.current ?? performance.now()));
        raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
      return () => cancelAnimationFrame(raf);
    }
    if (graphLoadStartRef.current !== null) {
      const dur = performance.now() - graphLoadStartRef.current;
      try {
        const prev = Number(localStorage.getItem("atanor_graph_load_ms")) || dur;
        localStorage.setItem("atanor_graph_load_ms", String(Math.round(prev * 0.7 + dur * 0.3)));
      } catch {}
      graphLoadStartRef.current = null;
    }
    setGraphLoadElapsed(0);
    return undefined;
  }, [tabBrainGraphPending]);
  const graphLoadingPercent = tabBrainGraphPending
    ? (() => {
        let est = 4000;
        try { est = Number(localStorage.getItem("atanor_graph_load_ms")) || 4000; } catch {}
        est = Math.max(800, est);
        return Math.max(3, Math.min(95, Math.round((graphLoadElapsed / est) * 100)));
      })()
    : 100;
  const studioGraph3D = useMemo(() => buildStudioTopologyGraph(visibleGraph3D), [visibleGraph3D]);
  // Onion growth: the cloud sphere slowly expands as the brain accumulates real
  // learning (candidate concepts), quantised so it grows in gentle steps. The
  // Rag3D camera auto-fit follows the larger radius and zooms out naturally.
  const onionScale = useMemo(() => {
    if (mainSection !== "cloud") return 1;
    const cc = Number(cloudCandidateStatus?.candidate_concepts ?? 0);
    const raw = 1 + Math.max(0, cc - 5000) / 45000;
    return Math.min(1.7, Math.round(raw * 40) / 40);
  }, [mainSection, cloudCandidateStatus]);
  const sphereGraph3D = useMemo(() => {
    const g = buildSphericalTopologyGraph(visibleGraph3D, graphPresentationMode);
    if (onionScale === 1) return g;
    return {
      ...g,
      nodes: g.nodes.map((node) => ({ ...node, x: node.x * onionScale, y: node.y * onionScale, z: node.z * onionScale })),
    };
  }, [visibleGraph3D, graphPresentationMode, onionScale]);
  const usesStudioGraph = mainSection === "home";
  const usesSphereGraph = mainSection === "graph" || mainSection === "local" || mainSection === "cloud" || mainSection === "chat";
  const userSceneGraph3D = usesStudioGraph ? studioGraph3D : usesSphereGraph ? sphereGraph3D : studioGraph3D;
  const cloudSceneGraph3D = useMemo(
    () => (mainSection === "cloud" ? appendCloudArrivals(userSceneGraph3D, cloudArrivals) : userSceneGraph3D),
    [mainSection, userSceneGraph3D, cloudArrivals],
  );

  // ── 시냅스 추적 (owner spec): ?trace=<labels,…> replays an answer's reasoning
  // path in the cloud graph — the camera flies node to node while the walked
  // path lights up in order, so reading the labels IS reading the inference.
  const [requestedTraceLabels, setRequestedTraceLabels] = useState<string[]>([]);
  const [synapseTrace, setSynapseTrace] = useState<{ ids: string[]; labels: string[] } | null>(null);
  const [synapseStep, setSynapseStep] = useState(0);
  const [synapseFocus, setSynapseFocus] = useState<{ serial: number; id: string } | null>(null);
  useEffect(() => {
    if (!requestedTraceLabels.length) return;
    const nodes = cloudSceneGraph3D?.nodes ?? [];
    if (!nodes.length) return;
    const norm = (value: string) => value.toLowerCase().replace(/\s+/g, "");
    const ids: string[] = [];
    const labels: string[] = [];
    for (const raw of requestedTraceLabels) {
      const target = norm(raw);
      if (!target) continue;
      const hit = nodes.find((node) => norm(String(node.label ?? "")) === target || norm(String(node.id ?? "")) === target)
        ?? nodes.find((node) => norm(String(node.label ?? "")).includes(target));
      if (hit && !ids.includes(String(hit.id))) {
        ids.push(String(hit.id));
        labels.push(String(hit.label || hit.id));
      }
    }
    if (ids.length) {
      setSynapseTrace({ ids, labels });
      setSynapseStep(0);
      setSynapseFocus({ serial: 1, id: ids[0] });
      setRequestedTraceLabels([]); // resolved once — graph refreshes must not restart the replay
    }
  }, [requestedTraceLabels, cloudSceneGraph3D]);
  useEffect(() => {
    if (!synapseTrace || synapseTrace.ids.length < 2) return;
    let step = 0;
    const timer = window.setInterval(() => {
      step += 1;
      if (step >= synapseTrace.ids.length) {
        window.clearInterval(timer);
        return;
      }
      setSynapseStep(step);
      setSynapseFocus({ serial: step + 1, id: synapseTrace.ids[step] });
    }, 1600);
    return () => window.clearInterval(timer);
  }, [synapseTrace]);
  const synapseTraceNodeIds = useMemo(
    () => (synapseTrace ? synapseTrace.ids.slice(0, synapseStep + 1) : EMPTY_STRING_ARRAY),
    [synapseTrace, synapseStep],
  );
  const synapseTraceEdgeKeys = useMemo(() => {
    if (!synapseTrace) return EMPTY_STRING_ARRAY;
    const keys: string[] = [];
    for (let index = 0; index < synapseStep && index + 1 < synapseTrace.ids.length; index += 1) {
      keys.push(`${synapseTrace.ids[index]}:${synapseTrace.ids[index + 1]}`);
    }
    return keys;
  }, [synapseTrace, synapseStep]);

  // Fetch the SURFACE (construction / sentence) knowledge graph when its view is
  // selected in the Cloud Brain tab. Refresh periodically so newly-learned
  // constructions show up.
  useEffect(() => {
    // Prefetch the surface graph whenever the Cloud tab is open (not only when the
    // surface view is selected), so switching to it is instant and reliable.
    if (mainSection !== "cloud") return;
    let alive = true;
    const load = async () => {
      try {
        const res = await fetch("/api/cloud-brain/surface-graph/graph?max_nodes=520&max_edges=900", { cache: "no-store" });
        const data = (await res.json()) as AnyRecord;
        if (alive && Array.isArray(data?.nodes) && data.nodes.length) setSurfaceGraphData(data);
      } catch {
        /* keep last */
      }
    };
    load();
    const id = setInterval(load, 8000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [mainSection]);

  const surfaceSceneGraph3D = useMemo<Rag3DGraph>(() => {
    const rawNodes = Array.isArray(surfaceGraphData?.nodes) ? (surfaceGraphData!.nodes as AnyRecord[]) : [];
    const rawEdges = Array.isArray(surfaceGraphData?.edges) ? (surfaceGraphData!.edges as AnyRecord[]) : [];
    if (!rawNodes.length) return { nodes: [], edges: [], traversal_path: [] };
    // Spherical layout (latitude by index, golden-angle longitude) — a clean
    // round ball like the concept graph, instead of scattered clusters.
    const count = rawNodes.length;
    const sphereR = 9.5;
    const clustered: Rag3DGraph = {
      nodes: rawNodes.map((node, index) => {
        const lat = 1 - ((index + 0.5) / count) * 2;
        const latRadial = Math.sqrt(Math.max(0.02, 1 - lat * lat));
        const lon = index * 2.399963229728653 + stableUnit(String(node.id), 811) * 0.2;
        const r = sphereR + stableUnit(String(node.id), 7) * 0.7;
        return {
          id: String(node.id),
          label: String(node.label ?? node.id),
          type: String(node.type ?? "surface_construction"),
          x: Math.cos(lon) * latRadial * r,
          y: lat * r,
          z: Math.sin(lon) * latRadial * r,
          source_type: "surface_construction",
        };
      }),
      edges: rawEdges.map((edge) => ({
        source: String(edge.source),
        target: String(edge.target),
        relation: String(edge.relation ?? "shares_concept"),
        weight: 0.6,
        source_type: "surface_construction",
      })),
      traversal_path: [],
    };
    // Surface arrivals (same flash/freeze/grow as concept) so the construction
    // graph visibly grows from the same learning.
    return appendCloudArrivals(clustered, surfaceArrivals);
  }, [surfaceGraphData, surfaceArrivals]);

  const cloudShowsSurface = mainSection === "cloud" && cloudGraphView === "surface" && surfaceSceneGraph3D.nodes.length > 0;

  // Drive "arrival" nodes from the REAL continuous-learning metrics. Each tick we
  // read how many concepts/relations were just learned and spawn that many fresh
  // nodes on the cloud's outer shell (capped per tick), then expire them after a
  // few seconds so they flash, connect, and fade rather than pile up.
  useEffect(() => {
    if (mainSection !== "cloud") {
      cloudArrivalPrevRef.current = null;
      surfaceArrivalPrevRef.current = null;
      setCloudArrivals((prev) => (prev.length ? [] : prev));
      setSurfaceArrivals((prev) => (prev.length ? [] : prev));
      return;
    }
    // New nodes flash orange, freeze to white, then linger as part of the body
    // (they "stay where they appeared"); the cap rotates the oldest out within
    // the render budget. Driven by the SHARED metrics subscription (no own poll).
    const data = cloudLearnMetrics as AnyRecord | null;
    if (!data) return;
    const ARRIVAL_TTL = 45000;
    const total = (Number(data.concepts_added) || 0) + (Number(data.relations_added) || 0);
    const titles = Array.isArray(data.last_titles) ? (data.last_titles as unknown[]).map(String) : [];
    const now = Date.now();
    // Drive the sky-blue activation density from the REAL relation-check rate
    // (scaled up so the sweep reads as a fast, lively verification pass).
    setSynapseRate(Math.min(280, Math.round((Number(data.relation_checks_per_second) || 0) * 1.8)));
    if (cloudArrivalPrevRef.current === null) {
      cloudArrivalPrevRef.current = total;
    } else {
      const delta = Math.max(0, total - cloudArrivalPrevRef.current);
      cloudArrivalPrevRef.current = total;
      setCloudArrivals((prev) => {
        const live = prev.filter((arrival) => now - arrival.born < ARRIVAL_TTL);
        if (delta <= 0) return live.length === prev.length ? prev : live;
        const spawnCount = Math.min(delta, 16);
        const fresh: CloudArrival[] = Array.from({ length: spawnCount }, (_, i) => ({
          id: `cloud-arrival-${now}-${i}`,
          label: titles.length ? titles[i % titles.length] : "새 개념",
          born: now,
          anchorSeed: Math.floor(Math.random() * 1_000_000_000),
          seq: arrivalSeqRef.current++,
        }));
        return [...live, ...fresh].slice(-180);
      });
    }
    // Surface (construction) graph learns from the SAME sentences — spawn
    // surface arrivals from the surface_added delta so both grow together.
    const surfaceTotal = Number(data.surface_added) || 0;
    if (surfaceArrivalPrevRef.current === null) {
      surfaceArrivalPrevRef.current = surfaceTotal;
    } else {
      const sDelta = Math.max(0, surfaceTotal - surfaceArrivalPrevRef.current);
      surfaceArrivalPrevRef.current = surfaceTotal;
      setSurfaceArrivals((prev) => {
        const live = prev.filter((arrival) => now - arrival.born < ARRIVAL_TTL);
        if (sDelta <= 0) return live.length === prev.length ? prev : live;
        const spawnCount = Math.min(sDelta, 16);
        const fresh: CloudArrival[] = Array.from({ length: spawnCount }, (_, i) => ({
          id: `surface-arrival-${now}-${i}`,
          label: titles.length ? titles[i % titles.length] : "새 문장",
          born: now,
          anchorSeed: Math.floor(Math.random() * 1_000_000_000),
          seq: arrivalSeqRef.current++,
        }));
        return [...live, ...fresh].slice(-180);
      });
    }
  }, [mainSection, cloudLearnMetrics]);
  const energyReduction = asPercent(neuro?.energy_estimate?.reduction_ratio);
  const eventSparsity = asPercent(neuro?.event_gate?.sparsity);
  const ramSoftGb = stability?.runtime_envelope?.ram_soft_gb ?? 23;
  const vramSoftGb = stability?.runtime_envelope?.vram_soft_gb ?? 12;
  const hotWindowNodes = stability?.graph_policy?.hot_window_nodes ?? 2048;
  const uiRenderNodes = stability?.graph_policy?.ui_render_nodes ?? 240;
  const telemetryLabel = telemetrySourceText(system, benchmark);
  const edgeTierLabel = String(edgeStatus?.capacity?.tier ?? "unknown").replace(/^tier_/, "T").replace(/_/g, "-").toUpperCase();
  const edgeBrokerState = edgeStatus?.capacity?.idle
    ? "idle"
    : edgeStatus?.state === "viewer_only"
      ? "viewer"
      : edgeStatus?.state ?? "waiting";
  const edgeBrokerLabel = `Edge ${edgeTierLabel} 쨌 Broker ${edgeBrokerState}`;
  const cloudRemoteConfig = (cloudBrainStatus?.remote_config && typeof cloudBrainStatus.remote_config === "object" && !Array.isArray(cloudBrainStatus.remote_config))
    ? cloudBrainStatus.remote_config as AnyRecord
    : null;
  const cloudRemoteStatus = (cloudBrainStatus?.remote_status && typeof cloudBrainStatus.remote_status === "object" && !Array.isArray(cloudBrainStatus.remote_status))
    ? cloudBrainStatus.remote_status as AnyRecord
    : null;
  const cloudProviderName = String(cloudBrainStatus?.cloud_provider ?? cloudRemoteStatus?.provider ?? "local");
  const cloudBrokerState = String(cloudBrainStatus?.broker_state ?? "local_broker_mode");
  const cloudEndpointLabel = String(cloudRemoteConfig?.endpoint ?? "").includes("workers.dev")
    ? "Cloudflare Workers"
    : cloudRemoteConfig?.endpoint ? "Remote endpoint" : "Local broker";
  const cloudBudget = (cloudBudgetStatus?.cloud_budget && typeof cloudBudgetStatus.cloud_budget === "object" && !Array.isArray(cloudBudgetStatus.cloud_budget))
    ? cloudBudgetStatus.cloud_budget as AnyRecord
    : null;
  const cloudBalance = (cloudBudgetStatus?.actual_context_balance && typeof cloudBudgetStatus.actual_context_balance === "object" && !Array.isArray(cloudBudgetStatus.actual_context_balance))
    ? cloudBudgetStatus.actual_context_balance as AnyRecord
    : (cloudBudgetStatus?.planned_balance && typeof cloudBudgetStatus.planned_balance === "object" && !Array.isArray(cloudBudgetStatus.planned_balance))
      ? cloudBudgetStatus.planned_balance as AnyRecord
      : null;
  const cloudBudgetPlan = String(cloudBudgetStatus?.plan ?? cloudBudget?.plan ?? "free");
  const cloudBudgetRequests = Number(cloudBudget?.effective_fragment_requests_per_day ?? cloudBudget?.cloud_fragment_requests_per_day ?? 0);
  const syncLocalWeight = typeof brainSyncStatus?.local_weight === "number" ? brainSyncStatus.local_weight : null;
  const syncCloudWeight = typeof brainSyncStatus?.cloud_weight === "number" ? brainSyncStatus.cloud_weight : null;
  const budgetLocalPct = Math.round(Number(syncLocalWeight ?? cloudBalance?.local ?? 1) * 100);
  const budgetCloudPct = Math.round(Number(syncCloudWeight ?? cloudBalance?.cloud ?? 0) * 100);
  const resourceStopReason = resourcePressureReason(system, gpu, stability, benchmark);
  const resourceSlowNotice = resourceStopReason ? null : resourceSoftNotice(system, gpu, stability, benchmark);
  const diskFreeGb = numeric(system?.disk_free_gb);
  const ramUsedGb = numeric(system?.ram_used_gb);
  const vramUsedGb = numeric(gpu?.vram_used) === null ? null : (numeric(gpu?.vram_used) ?? 0) / 1024;
  const daemonViewerOnly = !daemonCanOperate;
  const daemonCumulativeSeconds = Math.max(
    persistedLearningSeconds,
    Math.floor(Number(learningDaemon?.cumulative_learning_seconds ?? learningDaemon?.total_runtime_seconds ?? 0)),
    Math.floor(learningElapsedMs / 1000),
  );
  const contributionBackendState = String(contributionStatus?.contributor_state ?? "local_only");
  const contributionBrokerState = String(contributionStatus?.broker_state ?? (localBackendConnected ? "local_broker_mode" : "viewer_only"));
  const contributionCurrentTask = contributionStatus?.current_task as AnyRecord | null | undefined;
  const contributionCompletedTasks = Number(contributionStatus?.total_tasks_completed ?? 0);
  const contributionPendingCredit = numeric(contributionStatus?.pending_credits) ?? 0;
  const contributionConfirmedCredit = numeric(contributionStatus?.confirmed_credits) ?? 0;
  const contributionPreviewDisclaimer = String(
    contributionStatus?.preview_disclaimer
      ?? (language === "ko"
        ? "브레인 링크 노드는 원격 브로커와 안전한 공개 fragment 작업만 교환합니다. 개인 Payload Vault와 로컬 브레인 데이터는 공유하지 않습니다."
        : "Brain Link Node is running in Local Broker Mode. Private Payload Vault and Local Brain data are never shared."),
  );
  const contributionCpuUsage = Math.round(numeric(system?.cpu_percent ?? system?.cpu_usage_percent ?? system?.cpu?.usage_percent) ?? 8);
  const contributionRamGb = numeric(system?.ram_used_gb ?? system?.memory_used_gb ?? edgeStatus?.capacity?.ram_used_gb) ?? 1.2;
  const contributionGpuAvailable = Boolean(gpu?.available);
  const contributionGpuUsage = Math.round(numeric(gpu?.utilization) ?? 0);
  const contributionGpuLimitEffective = contributionGpuAvailable ? contributionGpuLimit : 0;
  const contributionCreditMultiplier = Number((1 + Math.min(0.35, Math.max(0, contributionCpuLimit - 20) / 60 * 0.35) + (contributionGpuLimitEffective / 95 * 1.65)).toFixed(2));
  const contributionEstimatedTaskCredit = Number(((numeric(contributionCurrentTask?.credit_estimate) ?? 1) * contributionCreditMultiplier).toFixed(2));
  const contributionNetworkLabel = localBackendConnected
    ? (language === "ko" ? "정상" : "Normal")
    : (language === "ko" ? "낮음" : "Low");
  const contributionThermalLabel = resourceStopReason
    ? (language === "ko" ? "보류" : "Hold")
    : (language === "ko" ? "정상" : "Normal");
  const contributionBlockedBySafety = Boolean(resourceStopReason);
  const contributionIsBackendActive = [
    "contributor_active",
    "contributor_registered",
    "task_polling",
    "task_running",
    "task_submitted",
    "verification_pending",
    "credit_confirmed",
  ].includes(contributionBackendState);
  const contributionIsActive = contributionEnabled && contributionIsBackendActive && !contributionPaused && !contributionBlockedBySafety;
  const contributionStatusText = !localBackendConnected
    ? (language === "ko" ? "연결 확인" : "Checking link")
    : contributionBlockedBySafety
      ? (language === "ko" ? "보호 모드" : "Protected")
      : contributionBackendState === "verification_pending"
        ? (language === "ko" ? "검증 준비" : "Verification ready")
        : contributionBackendState === "task_running"
          ? (language === "ko" ? "동기화 중" : "Syncing")
          : contributionPaused || contributionBackendState === "paused"
            ? (language === "ko" ? "일시정지" : "Paused")
            : contributionIsActive
              ? (language === "ko" ? "연결됨" : "Linked")
              : (language === "ko" ? "대기 안정" : "Stable idle");
  const contributionTodayCredit = contributionPendingCredit;
  const contributionTotalCredit = contributionConfirmedCredit + contributionPendingCredit;
  const contributionWaitingCredit = contributionPendingCredit;
  const contributionCreditTrend = useMemo(() => {
    const base = Math.max(0.2, contributionTotalCredit || contributionEstimatedTaskCredit || 0.8);
    const activityBoost = contributionIsActive ? 0.48 : 0.12;
    const gpuBoost = contributionGpuAvailable ? contributionGpuLimitEffective / 95 : 0.05;
    const cpuBoost = contributionCpuUsage / 220;
    const phase = contributionChartTick / 0.72;
    const samples = Array.from({ length: 42 }, (_, index) => {
      const localSpike = index % 7 === 0 ? 0.2 : index % 11 === 0 ? -0.14 : 0;
      return 0.82 + Math.sin(index * 0.92) * 0.12 + Math.cos(index * 1.83) * 0.08 + localSpike;
    });
    const values = samples.map((sample, index) => {
      const liveBias = (index / Math.max(1, samples.length - 1)) * (activityBoost + gpuBoost + cpuBoost);
      const wave = Math.sin(phase + index * 0.96) * 0.18
        + Math.cos(phase * 2.35 + index * 0.57) * 0.1
        + Math.sin(phase * 4.1 + index * 1.31) * 0.045;
      return Number(Math.max(0, base * (sample + wave) + liveBias).toFixed(2));
    });
    const max = Math.max(...values, 1);
    const min = Math.min(...values, 0);
    const range = Math.max(0.1, max - min);
    return values.map((value, index) => ({
      value,
      x: Number(((index / Math.max(1, values.length - 1)) * 100).toFixed(2)),
      y: Number((80 - ((value - min) / range) * 62).toFixed(2)),
    }));
  }, [contributionChartTick, contributionCpuUsage, contributionEstimatedTaskCredit, contributionGpuAvailable, contributionGpuLimitEffective, contributionIsActive, contributionTotalCredit]);
  const contributionCreditPolyline = contributionCreditTrend.map((point) => `${point.x},${point.y}`).join(" ");
  const contributionCreditArea = contributionCreditTrend.length
    ? `0,96 ${contributionCreditPolyline} 100,96`
    : "";
  const contributionCreditLatest = contributionCreditTrend[contributionCreditTrend.length - 1]?.value ?? contributionTotalCredit;
  const contributionSharedRatio = contributionAllowPublic && contributionIsActive ? 100 : 0;
  const contributionLocalShareRatio = 0;
  const contributionSafeSummary = contributionBlockedBySafety
    ? resourceStopReason
    : contributionGpuLimitEffective > 0
      ? (language === "ko" ? `GPU ${contributionGpuLimitEffective}% 보호 한도` : `GPU protected cap ${contributionGpuLimitEffective}%`)
      : (language === "ko" ? "CPU 경량 모드" : "CPU light mode");
  const daemonRuntimeText = formatDuration(daemonCumulativeSeconds * 1000);
  const daemonStateText = learningDaemon?.state === "resume_needed" ? "재개 필요" : learningDaemon?.state === "demo" ? "실험실 뷰어" : statusText(learningDaemon?.state);
  const daemonModeText = daemonCanOperate ? "로컬 클라우드 브레인 워커" : "배포 클라우드 브레인 뷰어";
  const daemonCheckpointText = learningDaemon?.last_checkpoint_at
    ? new Date(learningDaemon.last_checkpoint_at).toLocaleString("ko-KR")
    : "아직 없음";
  const daemonStatusState = daemonCanOperate
    ? learningDaemon?.worker_alive ? "running" : learningDaemon?.state === "failed" ? "failed" : learningDaemon?.state === "resume_needed" ? "warning" : "idle"
    : "completed";
  const labStatusState = error
    ? "failed"
    : isBuilding || continuousLearningActive || Boolean(activeAction) || isGeneratingAnswer
      ? "running"
      : "ready";
  const headerStatusState = workspaceMode === "daemon"
    ? daemonStatusState
    : labStatusState;
  const guardScore = guard?.overall_guard_score ?? guard?.result?.overall_guard_score ?? null;
  const guardClaimCount = guard?.result?.claims?.length ?? 0;
  const compactInfoSummary = [
    `${currentLearningPreset.label}${learningVolume === "infinite" ? "" : ` ${targetNodeCount.toLocaleString()}`}`,
    localBackendConnected ? "로컬 연결" : "fallback",
    edgeBrokerLabel,
    `GPU ${gpu?.utilization ?? 0}%`,
    `RAM ${ramSoftGb}GB`,
  ].join(" · ");
  const chatSummaryText = [
    `RAG ${Math.round((graphResult?.confidence ?? graphrag?.confidence ?? 0) * 100)}%`,
    fusionDisplayText,
    `근거 ${graphResult?.evidence_docs?.length ?? 0}`,
    guardScore === null ? "Guard 자동" : `Guard ${guardScore}`,
  ].join(" · ");
  const flowHealth = useMemo(() => {
    const complete = pipeline?.stages.filter((stage) => stage.state === "complete").length ?? 0;
    return Math.round((complete / Math.max(1, pipeline?.stages.length ?? 8)) * 100);
  }, [pipeline]);
  const collectComplete = labStageProgress.collect >= 100;
  const learnComplete = labStageProgress.learn >= 100;
  const outputComplete = labStageProgress.output >= 100;

  useEffect(() => {
    if (!continuousLearningActive || !resourceStopReason) return;
    stopContinuousLearning(resourceStopReason);
  }, [continuousLearningActive, resourceStopReason]);

  useEffect(() => {
    if (mainSection !== "contribute") return;
    const timer = window.setInterval(() => setContributionChartTick((tick) => tick + 1), 1000);
    return () => window.clearInterval(timer);
  }, [mainSection]);

  // Brain Link — real P2P coordinator pool (peers, queue, per-peer contribution).
  const [brainLinkPool, setBrainLinkPool] = useState<AnyRecord | null>(null);
  useEffect(() => {
    if (mainSection !== "contribute") return;
    let alive = true;
    const load = () => {
      fetchJson<AnyRecord>("/api/brain-link/pool/status")
        .then((data) => { if (alive) setBrainLinkPool(data); })
        .catch(() => {});
    };
    load();
    const timer = window.setInterval(load, 4000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [mainSection]);

  const processSteps = [
    {
      key: "collect" as LabStageKey,
      number: "01",
      title: language === "ko" ? "수집" : "Collect",
      api: "POST /api/factory/build/start + DataGate",
      state: isBuilding || continuousLearningActive || activeAction === "collect" ? "running" : collectComplete ? "completed" : "idle",
      description: language === "ko"
        ? "원문과 웹 참조를 문장 단위로 분해하고 GraphRAG가 읽을 후보 chunk와 초기 앵커 그래프를 만듭니다."
        : "Collects raw text and web references, splits them into sentence chunks, and prepares initial GraphRAG anchors.",
      progress: labStageProgress.collect,
      available: true,
      metrics: [
        `${buildRun?.harvest_docs?.length ?? datagate?.total ?? 0} docs`,
        `${buildRun?.training_gate?.chunk_count ?? currentLearningPreset.chunkBudget} chunks`,
        `${collectionDisplayNodeCount.toLocaleString()} visible nodes`,
        buildIsInfinite ? `∞ ${learningElapsedText}` : `${selectedTargetNodeLabel} target`,
      ],
      action: () => continuousLearningActive ? stopContinuousLearning() : runProcessAction("collect", startFactoryBuild),
      actionLabel: continuousLearningActive
        ? (language === "ko" ? "수집 중지" : "Stop collect")
        : isBuilding || activeAction === "collect"
          ? (language === "ko" ? "수집 중" : "Collecting")
          : (language === "ko" ? "수집 시작" : "Start collect"),
      blockedText: "",
    },
    {
      key: "learn" as LabStageKey,
      number: "02",
      title: language === "ko" ? "학습" : "Learn",
      api: "POST /api/ontology/run + /api/memory/build",
      state: activeAction === "learn" ? "running" : learnComplete ? "completed" : collectComplete ? "ready" : "idle",
      description: language === "ko"
        ? "분해된 문장 요소를 온톨로지 노드로 누적하고, 공출현과 전후 관계를 계산해 그래프 메모리로 굽습니다."
        : "Accumulates extracted sentence elements as ontology nodes and computes relation weights into graph memory.",
      progress: labStageProgress.learn,
      available: collectComplete,
      metrics: buildRun
        ? [
          `${displayGraph3D.nodes.length.toLocaleString()} representative nodes`,
          `${displayGraph3D.edges.length.toLocaleString()} representative edges`,
          `${memoryStatus?.node_count ?? 0} stored nodes`,
          `${memoryStatus?.edge_count ?? 0} stored edges`,
        ]
        : [
          `${memoryStatus?.node_count ?? ontology?.node_count ?? displayGraph3D.nodes.length} nodes`,
          `${memoryStatus?.edge_count ?? ontology?.edge_count ?? displayGraph3D.edges.length} edges`,
          `${memoryStatus?.transition_count ?? 0} transitions`,
          `drift ${memoryDrift?.state ?? "waiting"}`,
        ],
      action: () => runProcessAction("learn", runLearningStage),
      actionLabel: activeAction === "learn" ? (language === "ko" ? "학습 중" : "Learning") : (language === "ko" ? "관계 계산" : "Compute relations"),
      blockedText: language === "ko" ? "수집이 완료된 뒤 학습할 수 있습니다." : "Collect must complete before learning.",
    },
    {
      key: "output" as LabStageKey,
      number: "03",
      title: language === "ko" ? "출력" : "Output",
      api: "POST /api/graphrag/query + /api/guard/check",
      state: activeAction === "output" || isGeneratingAnswer ? "running" : outputComplete ? "completed" : learnComplete ? "ready" : "idle",
      description: language === "ko"
        ? "질문을 자연어로 입력하면 활성 노드와 그래프 경로를 읽고, 같은 근거 묶음으로 자동 검증합니다."
        : "Reads active nodes and graph paths for a question, then checks the answer against the same evidence bundle.",
      progress: labStageProgress.output,
      available: learnComplete,
      metrics: [
        `RAG ${Math.round((graphResult?.confidence ?? graphrag?.confidence ?? 0) * 100)}%`,
        `${graphResult?.evidence_docs?.length ?? 0} evidence`,
        guardScore === null ? "Guard waiting" : `Guard ${guardScore}`,
        `Web ${webSearchEnabled ? graphResult?.web_search?.provider ?? "on" : "off"}`,
      ],
      action: () => runProcessAction("output", async () => {
        setRightMode("chat");
        await sendChat();
      }),
      actionLabel: activeAction === "output" || isGeneratingAnswer ? (language === "ko" ? "생성 중" : "Generating") : (language === "ko" ? "질문 보내기" : "Send question"),
      blockedText: language === "ko" ? "학습이 완료된 뒤 출력 단계로 넘어갑니다." : "Learning must complete before output.",
    },
  ];


  const activeLabStageIndex = Math.max(0, labStageOrder.indexOf(activeLabStage));
  const activeProcessStep = processSteps.find((step) => step.key === activeLabStage) ?? processSteps[0];
  const previousProcessKey = activeLabStageIndex > 0 ? labStageOrder[activeLabStageIndex - 1] : null;
  const nextProcessKey = activeLabStageIndex < labStageOrder.length - 1 ? labStageOrder[activeLabStageIndex + 1] : null;

  function canOpenProcessStep(step: LabStageKey) {
    if (step === "collect") return true;
    if (step === "learn") return collectComplete;
    return learnComplete;
  }

  function openProcessStep(step: LabStageKey) {
    if (!canOpenProcessStep(step)) return;
    setRightMode("process");
    setActiveLabStage(step);
  }

  const logTime = clockNow ? fmtClock(clockNow) : "--:--:--";
  const logs = [
    ...(buildRun ? [{ time: logTime, message: `Build ${buildRun.run_id}: ${activeBuildFrame?.message ?? "factory build ready"} / gate ${buildRun.training_gate.ready ? "ready" : "waiting"}${buildIsInfinite ? ` / accumulated ${learningElapsedText}` : ""}` }] : []),
    { time: logTime, message: `Cloud Brain: ${daemonModeText} / state ${daemonStateText} / runtime ${daemonRuntimeText}` },
    { time: logTime, message: `Benchmark: ${benchmark?.profile_name ?? "waiting"} / recommended ${benchmarkVolumeLabel} / ${benchmarkSourceLabel}` },
    { time: logTime, message: `Memory graph loaded: ${displayMemoryNodeCount} nodes / ${displayMemoryEdgeCount} edges` },
    { time: logTime, message: `Provider: ${cloudProviderName} / broker ${cloudBrokerState} / budget ${cloudBudgetPlan} ${cloudBudgetRequests || 0}/day` },
    { time: logTime, message: `Brain Balance: Local ${budgetLocalPct}% / Cloud ${budgetCloudPct}%` },
    { time: logTime, message: `RAG state: ${statusText(graphrag?.state)} / confidence ${Math.round((graphrag?.confidence ?? 0) * 100)}%` },
    { time: logTime, message: `Learning state: ${statusText(oven?.state)} / last loss ${oven?.last_loss ?? "none"}` },
    { time: logTime, message: `Efficiency plan: estimated compute reduction ${energyReduction}%` },
    { time: logTime, message: `Stability: RAM soft ${ramSoftGb}GB / VRAM soft ${vramSoftGb}GB / hot window ${hotWindowNodes} nodes` },
  ];

  const headerBuildLabel = continuousLearningActive
    ? (language === "ko" ? "학습 중지" : "Stop learning")
    : isBuilding || activeAction === "collect"
      ? (language === "ko" ? "수집 중" : "Collecting")
      : activeAction === "learn"
        ? (language === "ko" ? "학습 중" : "Learning")
        : activeAction === "output" || isGeneratingAnswer
          ? (language === "ko" ? "출력 중" : "Generating")
          : !collectComplete
            ? (language === "ko" ? "빌드 시작" : "Start build")
            : !learnComplete
              ? (language === "ko" ? "다음: 학습" : "Next: learn")
              : (language === "ko" ? "RAG 채팅" : "RAG chat");

  async function runNextLabStage() {
    if (continuousLearningActive) {
      stopContinuousLearning();
      return;
    }
    if (!collectComplete) {
      await runProcessAction("collect", startFactoryBuild);
      return;
    }
    if (!learnComplete) {
      await runProcessAction("learn", runLearningStage);
      return;
    }
    setRightMode("chat");
    setLabStageProgress((current) => ({ ...current, output: Math.max(current.output, 6) }));
  }

  function changeLayoutMode(mode: LayoutMode) {
    setLayoutMode(mode);
  }

  function changeWorkspaceMode(mode: WorkspaceMode) {
    setWorkspaceMode(mode);
    const url = new URL(window.location.href);
    url.searchParams.set("workspace", mode);
    window.history.replaceState(null, "", url);
  }

  function resetConsole() {
    changeLayoutMode("split");
    changeWorkspaceMode("lab");
    setRightMode("chat");
    setSelectedMemory(null);
    setGraphView({ scale: 1, x: 0, y: 0 });
    setRag3dControl((control) => ({ serial: control.serial + 1, action: "reset" }));
  }

  function resetGraph() {
    setGraphView({ scale: 1, x: 0, y: 0 });
    setRag3dControl((control) => ({ serial: control.serial + 1, action: "reset" }));
  }

  function zoomGraph(delta: number, anchor = { x: 50, y: 50 }) {
    if (graphMode === "3d") {
      setRag3dControl((control) => ({ serial: control.serial + 1, action: delta > 0 ? "zoom-in" : "zoom-out" }));
      return;
    }
    setGraphView((view) => {
      const scale = clamp(view.scale + delta, 0.65, 3.25);
      const ratio = scale / view.scale;
      return {
        scale,
        x: clamp(anchor.x - (anchor.x - view.x) * ratio, -140, 140),
        y: clamp(anchor.y - (anchor.y - view.y) * ratio, -140, 140),
      };
    });
  }

  function panGraph(dx: number, dy: number) {
    if (graphMode === "3d") {
      const action = Math.abs(dx) > Math.abs(dy)
        ? dx > 0 ? "right" : "left"
        : dy > 0 ? "down" : "up";
      setRag3dControl((control) => ({ serial: control.serial + 1, action }));
      return;
    }
    setGraphView((view) => ({
      ...view,
      x: clamp(view.x + dx, -140, 140),
      y: clamp(view.y + dy, -140, 140),
    }));
  }

  function focusMemory(node: MemoryNode) {
    const scale = Math.max(graphView.scale, 1.45);
    setSelectedMemory(node);
    setGraphView({
      scale,
      x: clamp(50 - node.x * scale, -140, 140),
      y: clamp(50 - node.y * scale, -140, 140),
    });
  }

  function focusSearchResult() {
    const query = memoryQuery.trim().toLowerCase();
    if (!query) return;
    const node = memoryNodes.find((item) => `${item.label} ${item.type} ${item.id}`.toLowerCase().includes(query));
    if (node) focusMemory(node);
  }

  function handleGraphWheel(event: ReactWheelEvent<SVGSVGElement>) {
    event.preventDefault();
    const rect = event.currentTarget.getBoundingClientRect();
    zoomGraph(event.deltaY > 0 ? -0.13 : 0.13, {
      x: ((event.clientX - rect.left) / rect.width) * 100,
      y: ((event.clientY - rect.top) / rect.height) * 100,
    });
  }

  function handleGraphPointerDown(event: ReactPointerEvent<SVGSVGElement>) {
    if (event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragState({
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      view: graphView,
    });
  }

  function handleGraphPointerMove(event: ReactPointerEvent<SVGSVGElement>) {
    if (!dragState || dragState.pointerId !== event.pointerId) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const dx = ((event.clientX - dragState.startX) / rect.width) * 100;
    const dy = ((event.clientY - dragState.startY) / rect.height) * 100;
    setGraphView({
      scale: dragState.view.scale,
      x: clamp(dragState.view.x + dx, -140, 140),
      y: clamp(dragState.view.y + dy, -140, 140),
    });
  }

  function handleGraphPointerUp(event: ReactPointerEvent<SVGSVGElement>) {
    if (dragState?.pointerId === event.pointerId) {
      event.currentTarget.releasePointerCapture(event.pointerId);
      setDragState(null);
    }
  }

  function handleAtlasPointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    setAtlasDragState({
      pointerId: event.pointerId,
      startX: event.clientX,
      startRotationDeg: atlasRotationDeg,
    });
  }

  function handleAtlasPointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    if (!atlasDragState || atlasDragState.pointerId !== event.pointerId) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const deltaRatio = rect.width > 0 ? (event.clientX - atlasDragState.startX) / rect.width : 0;
    const nextRotation = atlasDragState.startRotationDeg + deltaRatio * 180;
    setAtlasRotationDeg((((nextRotation % 360) + 360) % 360));
  }

  function handleAtlasPointerUp(event: ReactPointerEvent<HTMLDivElement>) {
    if (atlasDragState?.pointerId === event.pointerId) {
      event.currentTarget.releasePointerCapture(event.pointerId);
      setAtlasDragState(null);
    }
  }

  const copy = EFFECTIVE_MAIN_COPY[language];
  const graphSparsity = displayMemoryNodeCount > 1
    ? ((displayMemoryEdgeCount / Math.max(1, displayMemoryNodeCount * (displayMemoryNodeCount - 1))) * 100).toFixed(2)
    : "0.00";
  const graphCommunities = Math.max(1, Math.round(Math.sqrt(Math.max(1, displayMemoryNodeCount)) / 2));
  const rawCloudAssistRatio =
    graphResult?.fusion?.cloud_ratio
    ?? graphResult?.fusion_ratio?.cloud_weight
    ?? graphResult?.retrieval_trace?.fusion_ratio?.cloud_weight
    ?? graphResult?.cloud_ratio;
  const generationLowConfidence = Boolean(
    graphResult?.native_generation_failed_quality_check
    || graphResult?.answer_engine?.diagnostics?.quality_guarded_surface
  );
  const cloudAssistRatio = graphPresentationMode === "local_private_memory"
    ? 0
    : graphPresentationMode === "cloud_world_knowledge"
      ? 100
      : rawCloudAssistRatio === undefined || rawCloudAssistRatio === null
        ? 50
        : Math.max(generationLowConfidence ? 35 : 0, Math.round(Number(rawCloudAssistRatio) * 100));
  const localAssistRatio = Math.max(0, 100 - cloudAssistRatio);
  const presentationCopy = (() => {
    if (graphPresentationMode === "local_private_memory") {
      return {
        graphTitle: language === "ko" ? "로컬 브레인 지식 그래프" : "Local Brain Knowledge Graph",
        graphSubtitle: language === "ko"
          ? "로컬 브레인과 Payload Vault 안에서만 탐색하고 답합니다."
          : "Searches and answers only inside the Local Brain and Payload Vault.",
        localLabel: language === "ko" ? "로컬 브레인" : "Local Brain",
        localDetail: language === "ko" ? "로컬 브레인 / 프로젝트 문맥" : "Local Brain / Project Context",
        cloudLabel: language === "ko" ? "클라우드 비활성" : "Cloud Disabled",
        cloudDetail: language === "ko" ? "명시적으로 켜기 전까지 사용하지 않음" : "Not used unless explicitly enabled",
        centerLabel: "Local Anchor",
        localNode: language === "ko" ? "로컬 브레인" : "Local Brain",
        cloudNode: language === "ko" ? "비활성 Cloud" : "Disabled Cloud",
        fragmentNode: "Payload Vault",
      };
    }
    if (graphPresentationMode === "cloud_world_knowledge") {
      return {
        graphTitle: language === "ko" ? "클라우드 브레인 지식 그래프" : "Cloud Brain Knowledge Graph",
        graphSubtitle: language === "ko"
          ? "클라우드 브레인 후보와 fragment 흐름을 읽기 전용으로 관찰합니다."
          : "Observes public ontology candidates and public fragment flow in read-only mode.",
        localLabel: language === "ko" ? "엣지 미러" : "Edge Mirror",
        localDetail: language === "ko" ? "읽기 전용 소비자" : "Read-only consumer",
        cloudLabel: language === "ko" ? "클라우드 브레인" : "Cloud Brain",
        cloudDetail: "Public Ontology / World Knowledge",
        centerLabel: "Public Anchor",
        localNode: language === "ko" ? "엣지 미러" : "Edge Mirror",
        cloudNode: language === "ko" ? "클라우드 브레인 노드" : "Cloud Brain",
        fragmentNode: language === "ko" ? "실시간 Fragment" : "Live Fragment",
      };
    }
    return {
      graphTitle: mainSection === "home" ? copy.graphTitle : (language === "ko" ? "통합 지식 그래프" : "Unified Knowledge Graph"),
      graphSubtitle: mainSection === "home"
        ? copy.graphSubtitle
        : (language === "ko"
          ? "로컬, 시드, 클라우드 레이어를 하나의 시각 투영으로만 표시합니다. 실제 브리지 연결을 뜻하지 않습니다."
          : "Local, Seed, and Cloud layers are shown as a visual projection only, not a live bridge."),
      localLabel: copy.localBrain,
      localDetail: "Private Boundary",
      cloudLabel: copy.cloudBrain,
      cloudDetail: "Public Fragment",
      centerLabel: "Working Memory",
      localNode: copy.localNode,
      cloudNode: copy.cloudNode,
      fragmentNode: copy.fragmentNode,
    };
  })();
  const activeTaskLabel = continuousLearningActive || learningDaemon?.worker_alive
    ? copy.learningEngine
    : isGeneratingAnswer
      ? copy.generationEngine
      : activeAction
        ? String(activeAction).toUpperCase()
        : "Adaptive Local-Cloud Ratio";
  const activeTaskRouteText = graphPresentationMode === "local_private_memory"
    ? (language === "ko" ? "로컬 브레인 전용" : "Local Brain only")
    : graphPresentationMode === "cloud_world_knowledge"
      ? (language === "ko" ? "클라우드 브레인 뷰어 / 읽기 전용 proof store" : "Cloud Brain viewer / read-only proof store")
      : graphPresentationMode === "home_unified_overview" || graphPresentationMode === "unified_projection"
        ? (language === "ko" ? "시각 투영 전용" : "Visual projection only")
        : `${localAssistRatio}% local / ${cloudAssistRatio}% cloud`;
  const graphFitScale = usesStudioGraph
    ? 1.18
    : graphPresentationMode === "local_private_memory"
      ? 1.58
      : graphPresentationMode === "cloud_world_knowledge"
        ? 1.5
        : 1.34;
  const activeTaskProgress = continuousLearningActive || learningDaemon?.worker_alive
    ? 100
    : isGeneratingAnswer
      ? 62
      : Math.max(4, cloudAssistRatio);
  const statusRows = graphPresentationMode === "local_private_memory"
    ? [
      { label: language === "ko" ? "로컬 브레인" : "Local Brain", value: localBrainInitialized ? copy.running : (language === "ko" ? "학습 전" : "Not trained"), tone: localBrainInitialized ? "green" : "orange" },
      { label: language === "ko" ? "저장 메모리" : "Stored Memories", value: displayMemoryNodeCount.toLocaleString(), tone: "white" },
      { label: "Payload Vault", value: language === "ko" ? "봉인됨" : "Sealed", tone: "white" },
      { label: "Ghost Shell", value: localBrainInitialized ? (language === "ko" ? "활성" : "Active") : (language === "ko" ? "비어 있음" : "Empty"), tone: "cyan" },
      { label: "Cloud Access", value: language === "ko" ? "최소화" : "Minimal", tone: "blue" },
    ]
    : graphPresentationMode === "cloud_world_knowledge"
      ? [
        { label: language === "ko" ? "클라우드 커버리지" : "Cloud Coverage", value: "100%", tone: "blue" },
        { label: language === "ko" ? "공용 Fragment" : "Public Fragments", value: displayMemoryNodeCount.toLocaleString(), tone: "cyan" },
        { label: language === "ko" ? "최신성" : "Freshness", value: learningDaemon?.worker_alive ? copy.listening : copy.ready, tone: "cyan" },
        { label: language === "ko" ? "Source Trust" : "Source Trust", value: "Tracked", tone: "white" },
        { label: language === "ko" ? "Edge Mirrors" : "Edge Mirrors", value: language === "ko" ? "읽기 전용" : "Read-only", tone: "green" },
      ]
      : [
        { label: copy.localBrain, value: graphPresentationMode === "home_unified_overview" || graphPresentationMode === "unified_projection" ? (language === "ko" ? "시각 레이어" : "Visual layer") : `${localAssistRatio}%`, tone: "green" },
        { label: copy.cloudBrain, value: graphPresentationMode === "home_unified_overview" || graphPresentationMode === "unified_projection" ? (language === "ko" ? "시각 레이어" : "Visual layer") : `${cloudAssistRatio}%`, tone: "blue" },
        { label: copy.learningEngine, value: learningDaemon?.worker_alive ? copy.listening : copy.ready, tone: "white" },
        { label: copy.generationEngine, value: isGeneratingAnswer ? copy.running : copy.ready, tone: "white" },
        { label: copy.fragmentSync, value: graphPresentationMode === "home_unified_overview" || graphPresentationMode === "unified_projection" ? (language === "ko" ? "연출" : "Staged") : copy.synced, tone: "cyan" },
      ];
  const providerStatusRows = [
    { label: "Cloud Provider", value: `${cloudProviderName} / ${cloudEndpointLabel}`, tone: cloudBrokerState === "remote_connected" ? "blue" : "white" },
    { label: "Broker State", value: cloudBrokerState, tone: cloudBrokerState === "remote_connected" ? "green" : "white" },
    { label: "Cloud Budget", value: `${cloudBudgetPlan.toUpperCase()} ${cloudBudgetRequests || 0}/day`, tone: "cyan" },
    { label: "Brain Balance", value: `${budgetLocalPct}% local / ${budgetCloudPct}% cloud`, tone: "blue" },
  ];
  const displayStatusRows = [...statusRows, ...providerStatusRows];
  const recentCards = [
    { title: copy.activity.graphUpdate, value: `${displayMemoryNodeCount.toLocaleString()} nodes / ${displayMemoryEdgeCount.toLocaleString()} relations`, time: logTime },
    { title: copy.activity.patchSync, value: signalTraceText, time: logTime },
    { title: copy.activity.runtime, value: daemonRuntimeText, time: logTime },
    { title: copy.activity.selected, value: selectedMemory?.label ?? "none", time: logTime },
  ];
  const sectionFallbackLabel: Record<MainSectionId, string> = {
    home: language === "ko" ? "대시보드" : "Dashboard",
    graph: language === "ko" ? "통합 지식 그래프" : "Unified Knowledge Graph",
    local: copy.localBrain,
    cloud: copy.cloudBrain,
    atlas: language === "ko" ? "아틀라스" : "Atlas",
    congress: "AGORA",
    "agent-os": "Agentic OS",
    selfhood: "Selfhood Lab",
    "live-scheduler": "Live Scheduler",
    "memory-approval": "Memory Approval",
    graphhub: "Graph Hub",
    autonomous: language === "ko" ? "자율 실행" : "Autonomous",
    contribute: language === "ko" ? "브레인 링크" : "Brain Link",
    chat: language === "ko" ? "채팅" : "Chat",
    settings: language === "ko" ? "설정" : "Settings",
  };
  const activeSectionLabel = copy.nav.find((item) => item.id === mainSection)?.label ?? sectionFallbackLabel[mainSection] ?? copy.nav[0].label;
  const isCloudViewerSection = mainSection === "cloud";
  // Local Brain no longer embeds its own chat panel (owner: local brain chat 제거) —
  // conversation lives in the Dashboard/Chat surface; Local Brain stays a graph/memory view.
  const isLocalChatSection = mainSection === "chat";
  const isOntologyChatSection = mainSection === "graph";
  const showInlineChatPanel = isOntologyChatSection || isLocalChatSection;
  const showRightRail = !isLocalChatSection;
  const showLowerSection = false;
  let lowerPanelTitle = isCloudViewerSection
    ? (language === "ko" ? "클라우드 브레인 뷰어" : "Cloud Brain Viewer")
    : isOntologyChatSection
      ? (language === "ko" ? "온톨로지 그래프 채팅" : "Ontology Graph Chat")
      : isLocalChatSection
      ? (language === "ko" ? "로컬 브레인 채팅" : "Local Brain Chat")
      : copy.chatTitle;
  let lowerPanelSubtitle = isCloudViewerSection
    ? (language === "ko"
      ? "클라우드 브레인 후보를 읽기 전용으로 관찰합니다. 질문 생성은 로컬 브레인에서만 실행됩니다."
      : "Read-only view of shared ontology candidates. Generative chat stays inside the Local Brain.")
    : isOntologyChatSection
      ? (language === "ko"
        ? "로컬/클라우드/작업 메모리의 관계를 함께 보며 질문합니다."
        : "Ask while inspecting Local, Cloud, and Working Memory relationships.")
      : isLocalChatSection
      ? (language === "ko"
        ? "로컬 Ghost Shell과 Payload Vault만 사용해 답변합니다."
        : "Chat against the local Ghost Shell and Payload Vault only.")
      : copy.chatSubtitle;
  if (language === "ko") {
    lowerPanelTitle = isCloudViewerSection
      ? "클라우드 브레인 뷰어"
      : isOntologyChatSection
        ? "온톨로지 그래프 채팅"
        : isLocalChatSection
          ? "로컬 브레인 채팅"
          : copy.chatTitle;
    lowerPanelSubtitle = isCloudViewerSection
      ? "클라우드 브레인 후보를 읽기 전용으로 관찰합니다. 질문 생성은 로컬 브레인에서만 실행됩니다."
      : isOntologyChatSection
        ? "그래프를 보면서 활성 노드와 Payload Vault 문맥을 기준으로 질문합니다."
        : isLocalChatSection
          ? "로컬 Ghost Shell과 Payload Vault만 사용해 답변합니다."
          : copy.chatSubtitle;
  }
  const ontologyPromptChips = language === "ko"
    ? ["브레인 라우팅 설명", "관련 메모리 보기", "앵커는 어떻게 선택해?"]
    : ["Explain unified-brain routing", "Show related memories", "How are anchors selected?"];
  const localPromptChips = language === "ko"
    ? ["내 로컬 브레인 구조 설명", "Payload Vault에는 뭐가 저장돼?", "최근 학습한 개념 보여줘"]
    : ["Explain my Local Brain", "What is stored in Payload Vault?", "Show recently learned concepts"];
  const activePromptChips = isLocalChatSection ? localPromptChips : ontologyPromptChips;
  const cloudViewerRows = [
    {
      label: language === "ko" ? "표시 노드" : "Visible nodes",
      value: displayMemoryNodeCount.toLocaleString(),
    },
    {
      label: language === "ko" ? "표시 관계" : "Visible relations",
      value: displayMemoryEdgeCount.toLocaleString(),
    },
    {
      label: language === "ko" ? "클라우드 보조" : "Cloud assist",
      value: `${cloudAssistRatio}%`,
    },
    {
      label: language === "ko" ? "조작 권한" : "Interaction",
      value: language === "ko" ? "읽기 전용" : "Viewer only",
    },
  ];
  const localBrainLayerCatalog = [
    { id: "local_user", label: language === "ko" ? "로컬 브레인" : "Local Brain" },
    { id: "working_memory_local", label: language === "ko" ? "작업 메모리" : "Working Memory" },
    { id: "local_base", label: language === "ko" ? "기본 지식" : "Base Brain" },
    { id: "seed", label: language === "ko" ? "시드 앵커" : "Seed" },
    { id: "local_memory_candidate", label: language === "ko" ? "승격 후보" : "Candidates" },
  ];
  const cloudBrainLayerCatalog = [
    { id: "semantic_cloud", label: language === "ko" ? "의미 클라우드" : "Semantic Cloud" },
    { id: "graph_cartridge", label: language === "ko" ? "그래프 카트리지" : "Graph Cartridge" },
    { id: "cloud_attached", label: language === "ko" ? "임시 부착" : "Cloud Attached" },
    { id: "contributor", label: language === "ko" ? "기여 노드" : "Contributor" },
    { id: "working_memory_cloud", label: language === "ko" ? "클라우드 작업 메모리" : "Cloud WM" },
    { id: "surface_trace_summary", label: language === "ko" ? "표현 요약" : "Surface Summary" },
  ];
  const activeBrainGraph = activeTabBrainGraphRaw;
  const activeBrainLayerCatalog = mainSection === "cloud" ? cloudBrainLayerCatalog : localBrainLayerCatalog;
  const activeBrainLayerSelection = mainSection === "cloud" ? cloudBrainGraphLayers : localBrainGraphLayers;
  const activeBrainView = mainSection === "cloud" ? "cloud" : "local";
  const activeBrainLayerCounts = (activeBrainGraph?.stats as AnyRecord | undefined)?.layer_counts as AnyRecord | undefined;
  const activeBrainMissing = Array.isArray(activeBrainGraph?.layers_missing) ? activeBrainGraph.layers_missing as AnyRecord[] : [];
  const activeBrainRenderedNodes = Number((activeBrainGraph?.stats as AnyRecord | undefined)?.rendered_nodes ?? 0);
  const activeBrainRenderedEdges = Number((activeBrainGraph?.stats as AnyRecord | undefined)?.rendered_edges ?? 0);
  const activeBrainVisualizationState = (
    (activeBrainGraph?.visualization_state && typeof activeBrainGraph.visualization_state === "object" && !Array.isArray(activeBrainGraph.visualization_state))
      ? activeBrainGraph.visualization_state
      : (activeBrainGraph?.stats as AnyRecord | undefined)?.visualization_state
  ) as AnyRecord | undefined;
  const graphVizLogical = (activeBrainVisualizationState?.logical && typeof activeBrainVisualizationState.logical === "object" && !Array.isArray(activeBrainVisualizationState.logical))
    ? activeBrainVisualizationState.logical as AnyRecord
    : {};
  const graphVizMaterialized = (activeBrainVisualizationState?.materialized && typeof activeBrainVisualizationState.materialized === "object" && !Array.isArray(activeBrainVisualizationState.materialized))
    ? activeBrainVisualizationState.materialized as AnyRecord
    : {};
  const graphVizRendered = (activeBrainVisualizationState?.rendered && typeof activeBrainVisualizationState.rendered === "object" && !Array.isArray(activeBrainVisualizationState.rendered))
    ? activeBrainVisualizationState.rendered as AnyRecord
    : {};
  const graphVizVirtualization = (activeBrainVisualizationState?.virtualization && typeof activeBrainVisualizationState.virtualization === "object" && !Array.isArray(activeBrainVisualizationState.virtualization))
    ? activeBrainVisualizationState.virtualization as AnyRecord
    : {};
  const surfaceGraphMeta = (surfaceGraphData?.metadata && typeof surfaceGraphData.metadata === "object" && !Array.isArray(surfaceGraphData.metadata))
    ? surfaceGraphData.metadata as AnyRecord
    : {};
  const graphHeaderStats = mainSection === "cloud"
    ? (cloudShowsSurface
      // Surface (construction / sentence) graph — its OWN counts, distinct from
      // the concept graph (the two are learned together but are not the same).
      ? [
        { label: language === "ko" ? "Constructions" : "Constructions", value: Number(surfaceGraphMeta.total_constructions ?? cloudCandidateStatus?.candidate_case_frames ?? 0).toLocaleString() },
        { label: language === "ko" ? "Concept links" : "Concept links", value: Number(surfaceGraphMeta.materialized_surface_edges ?? 0).toLocaleString() },
        { label: language === "ko" ? "Materialized" : "Materialized", value: Number(surfaceGraphMeta.materialized_surface_nodes ?? 0).toLocaleString() },
        { label: language === "ko" ? "Linked concepts" : "Linked concepts", value: Number(surfaceGraphMeta.distinct_concepts_linked ?? 0).toLocaleString() },
      ]
      // Logical Sphere count semantics: verified only grows on promotion; live
      // cumulative learning lands in the candidate store. Both are shown, but
      // SEPARATED ("A + B") — candidate learning must never be presented as one
      // production graph size (docs/ATANOR_logical_sphere_semantics.md).
      : [
        // the KG SUBSTRATE (int-columnar triple store that ANSWERS questions) is a
        // separate, far larger store than this semantic concept graph — shown first
        // so tens of millions of curated triples are never invisible in the lab
        ...(Number(cloudCandidateStatus?.kg_substrate_triples ?? 0) > 0
          ? [{ label: language === "ko" ? "지식 트리플 (KG 기반)" : "Knowledge triples (KG substrate)", value: Number(cloudCandidateStatus?.kg_substrate_triples ?? 0).toLocaleString() }]
          : []),
        { label: language === "ko" ? "노드 (검증+후보)" : "Nodes (verified+cand.)", value: `${Number(Number(graphVizLogical.node_count ?? semanticStoreConceptCount ?? displayMemoryNodeCount) || 0).toLocaleString()} + ${Number(Number(cloudCandidateStatus?.candidate_concepts ?? 0) || 0).toLocaleString()}` },
        { label: language === "ko" ? "관계 (검증+후보)" : "Relations (verified+cand.)", value: `${Number(Number(graphVizLogical.stored_relation_count ?? semanticStoreRelationCount ?? displayMemoryEdgeCount) || 0).toLocaleString()} + ${Number(Number(cloudCandidateStatus?.candidate_relations ?? 0) || 0).toLocaleString()}` },
        { label: language === "ko" ? "Materialized" : "Materialized", value: Number(graphVizMaterialized.node_count ?? displayMemoryNodeCount).toLocaleString() },
        { label: language === "ko" ? "렌더 샘플 엣지" : "Rendered sample edges", value: Number(graphVizRendered.edge_count ?? displayMemoryEdgeCount).toLocaleString() },
      ])
    : [
      { label: copy.nodes, value: graphHeaderNodeText },
      { label: copy.relations, value: graphHeaderEdgeText },
      { label: copy.sparsity, value: `${graphSparsity}%` },
      { label: copy.communities, value: String(graphCommunities) },
    ];
  const activeBrainOverlay = brainGraphOverlayStatus ?? ((activeBrainGraph?.stats as AnyRecord | undefined)?.overlay as AnyRecord | undefined) ?? {};
  const activeBrainGraphRows = activeBrainLayerCatalog.map((item) => {
    const count = Number(activeBrainLayerCounts?.[item.id] ?? 0);
    const missing = activeBrainMissing.find((entry) => entry.layer === item.id);
    return {
      ...item,
      enabled: activeBrainLayerSelection.includes(item.id),
      count,
      missingReason: missing ? String(missing.reason ?? "unavailable") : "",
    };
  });
  const sourceInspector = (cloudBrainSourceInspector && typeof cloudBrainSourceInspector === "object" && !Array.isArray(cloudBrainSourceInspector))
    ? cloudBrainSourceInspector as AnyRecord
    : {};
  const remoteBrokerInspector = (sourceInspector.remote_cloudflare_broker && typeof sourceInspector.remote_cloudflare_broker === "object" && !Array.isArray(sourceInspector.remote_cloudflare_broker))
    ? sourceInspector.remote_cloudflare_broker as AnyRecord
    : {};
  const localProofInspector = (sourceInspector.local_proof_store && typeof sourceInspector.local_proof_store === "object" && !Array.isArray(sourceInspector.local_proof_store))
    ? sourceInspector.local_proof_store as AnyRecord
    : {};
  const mirrorInspector = (sourceInspector.cloud_mirror_snapshot && typeof sourceInspector.cloud_mirror_snapshot === "object" && !Array.isArray(sourceInspector.cloud_mirror_snapshot))
    ? sourceInspector.cloud_mirror_snapshot as AnyRecord
    : {};
  const activeCloudSourceMode = String(sourceInspector.active_source_mode ?? "local_broker_mode");
  const verifiedRemoteCloudBrain = activeCloudSourceMode === "remote_cloudflare_broker";
  const remoteProofStatus = String(remoteCloudProof?.result ?? (remoteBrokerInspector.remote_persistence ? "PASS" : "UNVERIFIED"));
  const sourceInspectorRows = [
    { label: language === "ko" ? "활성 소스" : "Active source", value: activeCloudSourceMode },
    { label: language === "ko" ? "Local proof" : "Local proof", value: `${Number(localProofInspector.fragments ?? 0)} / ${Number(localProofInspector.nodes ?? 0)}n` },
    { label: language === "ko" ? "Mirror snapshot" : "Mirror snapshot", value: `${Number(mirrorInspector.nodes ?? 0).toLocaleString()} / ${Number(mirrorInspector.edges ?? 0).toLocaleString()}` },
    { label: language === "ko" ? "Remote broker" : "Remote broker", value: remoteBrokerInspector.reachable ? String(remoteBrokerInspector.broker_state ?? "reachable") : "not verified" },
    { label: language === "ko" ? "Storage" : "Storage", value: String(remoteBrokerInspector.storage_backend ?? "unknown") },
    { label: language === "ko" ? "Read-back" : "Read-back", value: remoteBrokerInspector.fragment_readback_success ? "ok" : "not proven" },
  ];
  const sourceInspectorWarning = verifiedRemoteCloudBrain
    ? (language === "ko" ? "검증된 원격 Cloud Brain 브로커를 보고 있습니다." : "You are viewing a verified remote Cloud Brain broker.")
    : (language === "ko" ? "현재 화면은 실시간 원격 Cloud Brain이 아닙니다. 로컬 proof, 로컬 브로커 또는 미러 스냅샷입니다." : "You are not viewing the live remote Cloud Brain. This view is local proof, local broker, or mirror snapshot.");
  const cloudGraphStats = (brainGraphCloud?.stats && typeof brainGraphCloud.stats === "object" && !Array.isArray(brainGraphCloud.stats))
    ? brainGraphCloud.stats as AnyRecord
    : {};
  const cloudGraphLayerCounts = (cloudGraphStats.layer_counts && typeof cloudGraphStats.layer_counts === "object" && !Array.isArray(cloudGraphStats.layer_counts))
    ? cloudGraphStats.layer_counts as AnyRecord
    : {};
  const cloudGraphEdgeLayerCounts = (cloudGraphStats.edge_layer_counts && typeof cloudGraphStats.edge_layer_counts === "object" && !Array.isArray(cloudGraphStats.edge_layer_counts))
    ? cloudGraphStats.edge_layer_counts as AnyRecord
    : {};
  const semanticCloudConcepts = semanticStoreConceptCount || Number(cloudGraphLayerCounts.semantic_cloud ?? 0);
  const semanticCloudRelations = semanticStoreRelationCount || Number(cloudGraphEdgeLayerCounts.semantic_cloud ?? 0);
  const semanticCloudEvidence = Number(semanticCloudStatus?.evidence ?? 0);
  const semanticCloudLoaded = Boolean(semanticCloudStatus) || semanticCloudConcepts > 0 || semanticCloudRelations > 0;
  const cloudLoadingText = language === "ko" ? "확인 중" : "Checking";
  const cloudNumberText = (value: number) => Number.isFinite(value) ? value.toLocaleString() : "0";
  const semanticLastGrowthRun = (semanticCloudStatus?.last_growth_run && typeof semanticCloudStatus.last_growth_run === "object" && !Array.isArray(semanticCloudStatus.last_growth_run))
    ? semanticCloudStatus.last_growth_run as AnyRecord
    : {};
  const semanticRecentGrowthDelta = Number(semanticLastGrowthRun.concepts_created ?? 0)
    + Number(semanticLastGrowthRun.concepts_merged ?? 0)
    + Number(semanticLastGrowthRun.relations_created ?? 0)
    + Number(semanticLastGrowthRun.relations_strengthened ?? 0)
    + Number(semanticLastGrowthRun.evidence_added ?? 0);
  const semanticWebSeedActive = Boolean(semanticCloudStatus?.web_seed_feeder_active);
  const semanticSelfGrowthActive = Boolean(semanticCloudStatus?.self_growth_active) || semanticWebSeedActive;
  const semanticCloudRows = [
    { label: language === "ko" ? "개념" : "Concepts", value: cloudNumberText(semanticCloudConcepts) },
    { label: language === "ko" ? "관계" : "Relations", value: cloudNumberText(semanticCloudRelations) },
    { label: language === "ko" ? "근거" : "Evidence", value: cloudNumberText(semanticCloudEvidence) },
    { label: language === "ko" ? "저장소" : "Store", value: semanticCloudStatus?.proof_store_only === false ? "external" : "proof only" },
    { label: language === "ko" ? "자가증식" : "Self-growth", value: semanticSelfGrowthActive ? (language === "ko" ? "활성" : "active") : (language === "ko" ? "대기" : "idle") },
    { label: language === "ko" ? "최근 변화" : "Recent delta", value: String(semanticRecentGrowthDelta) },
  ];
  const semanticGrowthRows = [
    { label: language === "ko" ? "생성 개념" : "Concepts created", value: String(semanticGrowthRun?.concepts_created ?? 0) },
    { label: language === "ko" ? "병합 개념" : "Concepts merged", value: String(semanticGrowthRun?.concepts_merged ?? 0) },
    { label: language === "ko" ? "생성 관계" : "Relations created", value: String(semanticGrowthRun?.relations_created ?? 0) },
    { label: language === "ko" ? "강화 관계" : "Relations strengthened", value: String(semanticGrowthRun?.relations_strengthened ?? 0) },
    { label: language === "ko" ? "Local 기록" : "Local write", value: semanticGrowthRun?.honesty?.local_brain_write ? (language === "ko" ? "기록함" : "on") : (language === "ko" ? "기록 안 함" : "off") },
    { label: language === "ko" ? "외부 LLM" : "External LLM", value: semanticGrowthRun?.honesty?.external_llm_used ? "true" : "false" },
  ];
  const semanticAttachRows = [
    { label: language === "ko" ? "임시 노드" : "Attached nodes", value: String((semanticAttachResult?.attached_nodes as AnyRecord[] | undefined)?.length ?? 0) },
    { label: language === "ko" ? "임시 관계" : "Attached edges", value: String((semanticAttachResult?.attached_edges as AnyRecord[] | undefined)?.length ?? 0) },
    { label: language === "ko" ? "임시성" : "Temporary", value: semanticAttachResult?.temporary ? "true" : "-" },
    { label: language === "ko" ? "Local 기록" : "Local write", value: semanticAttachResult?.local_brain_write ? (language === "ko" ? "기록함" : "on") : (language === "ko" ? "기록 안 함" : "off") },
  ];
  const graphOverlay = (graph?.working_memory_overlay && typeof graph.working_memory_overlay === "object" && !Array.isArray(graph.working_memory_overlay))
    ? graph.working_memory_overlay as AnyRecord
    : ((cloudAttachmentStatus?.working_memory_overlay && typeof cloudAttachmentStatus.working_memory_overlay === "object" && !Array.isArray(cloudAttachmentStatus.working_memory_overlay))
      ? cloudAttachmentStatus.working_memory_overlay as AnyRecord
      : {});
  const cloudAttachedNodeCount = Number(graphOverlay.cloud_attached_nodes ?? (cloudAttachmentStatus?.cloud_attached_nodes ?? 0));
  const cloudAttachedEdgeCount = Number(graphOverlay.cloud_attached_edges ?? (cloudAttachmentStatus?.cloud_attached_edges ?? 0));
  const overlayBundleIds = Array.isArray(graphOverlay.bundle_ids) ? graphOverlay.bundle_ids as string[] : [];
  const webFeederState = (cloudBrainStatus?.web_feeder_state && typeof cloudBrainStatus.web_feeder_state === "object" && !Array.isArray(cloudBrainStatus.web_feeder_state))
    ? cloudBrainStatus.web_feeder_state as AnyRecord
    : {};
  const webFeederEnabled = Boolean(webFeederState.enabled) || semanticWebSeedActive;
  const webFeederStatus = String(semanticCloudStatus?.web_seed_feeder_status ?? webFeederState.status ?? webFeederState.last_status ?? "idle");
  const webFeederLastRun = String(webFeederState.last_run_at ?? "-");
  const webFeederCreated = Number(webFeederState.fragments_created ?? 0);
  const webFeederRejected = Number(webFeederState.fragments_rejected ?? 0);
  const webFeederSemanticIngested = Number(semanticCloudStatus?.web_seed_semantic_ingested ?? webFeederState.semantic_ingested ?? 0);
  const webFeederDiscovered = Number(semanticCloudStatus?.web_seed_discovered_sources_added ?? webFeederState.discovered_sources_added ?? 0);
  const webFeederRows = [
    { label: language === "ko" ? "상태" : "State", value: webFeederEnabled ? (language === "ko" ? "활성" : "Enabled") : (language === "ko" ? "비활성" : "Disabled") },
    { label: language === "ko" ? "최근 실행" : "Last run", value: webFeederLastRun },
    { label: language === "ko" ? "확인 소스" : "Sources checked", value: String(webFeederState.sources_checked ?? 0) },
    { label: language === "ko" ? "후보 생성" : "Candidates", value: String(webFeederCreated) },
    { label: language === "ko" ? "수집 반영" : "Semantic ingest", value: String(webFeederSemanticIngested) },
    { label: language === "ko" ? "발견 소스" : "Discovered", value: String(webFeederDiscovered) },
    { label: language === "ko" ? "거절" : "Rejected", value: String(webFeederRejected) },
    { label: language === "ko" ? "마지막 상태" : "Last status", value: webFeederStatus },
  ];
  const webFeederMessage = !webFeederEnabled
    ? (language === "ko" ? "Web Seed Feeder는 비활성 상태입니다." : "Web Seed Feeder is disabled.")
    : webFeederSemanticIngested > 0 || semanticRecentGrowthDelta > 0
      ? (language === "ko" ? "공개 웹 시드가 Semantic Cloud proof store에 반영되고 있습니다." : "Public web seeds are being reflected into the Semantic Cloud proof store.")
      : webFeederCreated > 0
        ? (language === "ko" ? "새 공개 후보 fragment가 생성되었습니다. 검증/수집 대기 중입니다." : "New public candidate fragments were created. Waiting for verification/ingestion.")
      : webFeederStatus === "no_new_payload" || webFeederStatus === "listening"
        ? (language === "ko" ? "새 공개 seed payload를 대기 중입니다." : "Listening for new public seed payloads.")
        : (language === "ko" ? "Cloud Brain 카운트는 수집과 검증 이후에만 갱신됩니다." : "Cloud Brain counts update only after ingestion and verification.");
  const controlledGrowthState = (cloudBrainStatus?.controlled_self_growth_state && typeof cloudBrainStatus.controlled_self_growth_state === "object" && !Array.isArray(cloudBrainStatus.controlled_self_growth_state))
    ? cloudBrainStatus.controlled_self_growth_state as AnyRecord
    : {};
  const autonomousSelfGrowthActive = Boolean(semanticSelfGrowthActive && (semanticRecentGrowthDelta > 0 || webFeederSemanticIngested > 0 || semanticCloudConcepts > 0));
  const candidateOverlayAvailable = Boolean(cloudCandidateStatus?.candidate_available);
  const candidateOverlayLabel = candidateOverlayAvailable
    ? (language === "ko" ? "후보 / 미승격" : "candidate / unpromoted")
    : (language === "ko" ? "후보 없음" : "none");
  const cloudTruthRows = [
    { label: "Logical Sphere", value: graphVizLogical.sphere_topology === false ? "off" : "ON" },
    { label: "Nodes", value: cloudNumberText(Number(graphVizLogical.node_count ?? semanticCloudConcepts)) },
    { label: "Stored relations", value: cloudNumberText(Number(graphVizLogical.stored_relation_count ?? semanticCloudRelations)) },
    { label: "Candidate pairs", value: `${cloudNumberText(Number(graphVizLogical.possible_candidate_pairs ?? graphVizLogical.possible_pair_candidates ?? 0))} implicit` },
    { label: "Active Chunks", value: `${Number(graphVizMaterialized.active_chunks ?? 0).toLocaleString()} · LOD ${String((activeBrainVisualizationState?.spherical_view as AnyRecord | undefined)?.lod ?? graphVizMaterialized.zoom_level ?? 0)}` },
    { label: "Materialized nodes", value: Number(graphVizMaterialized.node_count ?? activeBrainRenderedNodes ?? 0).toLocaleString() },
    { label: "Verified relations", value: Number(graphVizMaterialized.verified_relation_count ?? graphVizMaterialized.relation_count ?? semanticCloudRelations).toLocaleString() },
    { label: "Focus relations", value: Number(graphVizMaterialized.focus_relation_count ?? 0).toLocaleString() },
    { label: "Implicit pairs", value: Number(graphVizMaterialized.implicit_candidate_pairs ?? 0).toLocaleString() },
    { label: "Rendered Frame", value: `${Number(graphVizRendered.node_count ?? activeBrainRenderedNodes ?? 0).toLocaleString()} / ${Number(graphVizRendered.edge_count ?? activeBrainRenderedEdges ?? 0).toLocaleString()}` },
    { label: "Visual hints", value: Number(graphVizRendered.visual_edge_hints ?? 0).toLocaleString() },
    { label: "Pair edges sent", value: String(graphVizMaterialized.candidate_pair_edges_sent ?? 0) },
    { label: "Virtualization", value: graphVizVirtualization.candidate_pairs_implicit === false ? "off" : "ON" },
    { label: language === "ko" ? "후보 오버레이" : "Candidate overlay", value: candidateOverlayLabel },
    { label: language === "ko" ? "후보 concepts" : "Candidate concepts", value: cloudNumberText(Number(cloudCandidateStatus?.candidate_concepts ?? 0)) },
    { label: language === "ko" ? "후보 relations" : "Candidate relations", value: cloudNumberText(Number(cloudCandidateStatus?.candidate_relations ?? 0)) },
    { label: language === "ko" ? "후보 evidence" : "Candidate evidence", value: cloudNumberText(Number(cloudCandidateStatus?.candidate_evidence ?? 0)) },
    { label: language === "ko" ? "후보 case frames" : "Candidate case frames", value: cloudNumberText(Number(cloudCandidateStatus?.candidate_case_frames ?? 0)) },
    { label: "Surface / CGSR / RHFC", value: `${cloudNumberText(Number(cloudCandidateStatus?.surface_candidates ?? 0))} / ${cloudNumberText(Number(cloudCandidateStatus?.cgsr_frames ?? 0))} / ${cloudNumberText(Number(cloudCandidateStatus?.rhfc_candidates ?? 0))}` },
  ];
  // The human-readable summary shown by default — a few meaningful numbers, not the 18-row engine
  // dump (owner: "이런 사용자친화적이지 않은 UI 제거하자"). The full raw grid lives under Diagnostics.
  const cloudSummaryRows = [
    { label: language === "ko" ? "개념" : "Concepts", value: cloudNumberText(Number(graphVizLogical.node_count ?? semanticCloudConcepts)) },
    { label: language === "ko" ? "관계" : "Relations", value: cloudNumberText(Number(graphVizLogical.stored_relation_count ?? semanticCloudRelations)) },
    { label: language === "ko" ? "검증됨" : "Verified", value: Number(graphVizMaterialized.verified_relation_count ?? graphVizMaterialized.relation_count ?? semanticCloudRelations).toLocaleString() },
  ];
  const cloudSourceCompactRows = [
    { label: language === "ko" ? "소스" : "Source", value: cloudBrainSourceInspector ? activeCloudSourceMode : cloudLoadingText },
    { label: language === "ko" ? "원격" : "Remote", value: cloudBrainSourceInspector ? (remoteBrokerInspector.reachable ? String(remoteBrokerInspector.broker_state ?? "reachable") : "not verified") : cloudLoadingText },
    { label: language === "ko" ? "로컬" : "Local", value: `${Number(sourceInspector.local_brain_state?.local_total_nodes ?? 0)} / ${Number(sourceInspector.local_brain_state?.local_total_edges ?? 0)}` },
  ];
  const cloudAttachmentCompactRows = [
    { label: language === "ko" ? "임시 노드" : "Temp nodes", value: `${cloudAttachedNodeCount}` },
    { label: language === "ko" ? "임시 관계" : "Temp edges", value: `${cloudAttachedEdgeCount}` },
    { label: language === "ko" ? "상태" : "State", value: cloudAttachedNodeCount > 0 ? "temporary" : "idle" },
  ];
  const cloudProofGraphState = (cloudBrainStatus?.cloud_graph_state && typeof cloudBrainStatus.cloud_graph_state === "object" && !Array.isArray(cloudBrainStatus.cloud_graph_state))
    ? cloudBrainStatus.cloud_graph_state as AnyRecord
    : {};
  const controlledGrowthRows = [
    { label: language === "ko" ? "검증 방식" : "Proof mode", value: String(controlledGrowthProof?.mode ?? controlledGrowthState.mode ?? "controlled_fixture_only") },
    { label: language === "ko" ? "후보 fragment" : "Candidate fragment", value: String(controlledGrowthProof?.fragment_id ?? controlledGrowthState.last_ingested_fragment_id ?? "-") },
    { label: language === "ko" ? "정렬" : "Alignment", value: controlledGrowthProof?.alignment_success ? (language === "ko" ? "seed 정렬" : "seed aligned") : (language === "ko" ? "대기" : "waiting") },
    { label: language === "ko" ? "수집 상태" : "Ingestion", value: controlledGrowthProof?.ingestion_success || controlledGrowthState.last_ingestion_success ? "ingested" : "pending" },
    { label: language === "ko" ? "신뢰 상태" : "Trust", value: controlledGrowthProof?.trust_state ? String(controlledGrowthProof.trust_state) : (controlledGrowthProof?.ingestion_success ? "seed_aligned" : "unverified") },
    { label: language === "ko" ? "읽기 검증" : "Read-back", value: controlledGrowthProof?.query_readback_success ? "ok" : "-" },
    { label: language === "ko" ? "추가 노드" : "Nodes added", value: String(controlledGrowthProof?.nodes_added ?? 0) },
    { label: language === "ko" ? "추가 관계" : "Edges added", value: String(controlledGrowthProof?.edges_added ?? 0) },
    { label: language === "ko" ? "Cloud 노드" : "Cloud nodes", value: String(controlledGrowthProof?.new_cloud_nodes ?? cloudProofGraphState.proof_store_nodes ?? 0) },
    { label: language === "ko" ? "Cloud 관계" : "Cloud edges", value: String(controlledGrowthProof?.new_cloud_edges ?? cloudProofGraphState.proof_store_edges ?? 0) },
    { label: language === "ko" ? "Local 기록" : "Local write", value: "0 / 0" },
    { label: language === "ko" ? "광역 크롤링" : "Broad crawl", value: "false" },
  ];
  const controlledGrowthMessage = controlledGrowthProof?.controlled_self_growth
    ? (language === "ko"
      ? "공개 fixture fragment가 Seed Graph에 정렬된 뒤 Cloud Brain proof store에만 수집되고, fragment query로 다시 읽혔습니다."
      : "The public fixture fragment aligned to the Seed Graph, entered only the Cloud Brain proof store, and was read back through fragment query.")
    : (language === "ko"
      ? "아직 controlled self-growth proof를 실행하지 않았습니다. 이 검증은 제한된 fixture만 사용하며 광역 크롤링을 주장하지 않습니다."
      : "Controlled self-growth proof has not run yet. This uses a bounded fixture only and does not claim broad crawling.");
  const cloudSphereRows = [
    { label: language === "ko" ? "Logical nodes" : "Logical nodes", value: cloudSphereStats?.logicalNodes ?? "0" },
    { label: language === "ko" ? "Actual materialized" : "Actual materialized", value: String(cloudSphereStats?.actualMaterializedNodes ?? 0) },
    { label: language === "ko" ? "Rendered nodes" : "Rendered nodes", value: String(cloudSphereStats?.renderedNodes ?? 0) },
    { label: language === "ko" ? "Active tiles" : "Active tiles", value: String(cloudSphereStats?.activeTiles ?? 0) },
    { label: language === "ko" ? "Zoom level" : "Zoom level", value: String(cloudSphereStats?.zoomLevel ?? 0) },
    { label: language === "ko" ? "Render budget" : "Render budget", value: `${cloudSphereStats?.renderBudgetNodes ?? 5000} / ${cloudSphereStats?.renderBudgetEdges ?? 10000}` },
    { label: language === "ko" ? "Compression" : "Compression", value: String(Boolean(cloudSphereStats?.compressionUsed)) },
    { label: language === "ko" ? "Aggregate nodes" : "Aggregate nodes", value: String(Boolean(cloudSphereStats?.semanticAggregateNodesUsed)) },
    { label: language === "ko" ? "Shell mode" : "Shell mode", value: String(Boolean(cloudSphereStats?.shellMode)) },
    { label: language === "ko" ? "Actual-node mode" : "Actual-node mode", value: String(Boolean(cloudSphereStats?.actualNodeMode)) },
  ];
  const cortexLastCycle = (cortexStatus?.last_cycle && typeof cortexStatus.last_cycle === "object" && !Array.isArray(cortexStatus.last_cycle))
    ? cortexStatus.last_cycle as AnyRecord
    : {};
  const cortexRows = [
    { label: language === "ko" ? "활성 노드" : "Active nodes", value: String(cortexLastCycle.activated_nodes ?? 0) },
    { label: language === "ko" ? "억제 노드" : "Inhibited nodes", value: String(cortexLastCycle.inhibited_nodes ?? 0) },
    { label: language === "ko" ? "작업공간" : "Workspace", value: String(cortexLastCycle.salience_nodes ?? 0) },
    { label: language === "ko" ? "예측 경로" : "Prediction paths", value: String(cortexLastCycle.prediction_paths ?? 0) },
    { label: language === "ko" ? "오차" : "Error", value: `${Math.round(Number(cortexLastCycle.prediction_error ?? 0) * 100)}%` },
    { label: language === "ko" ? "Crystal 후보" : "Crystal candidate", value: cortexLastCycle.knowledge_crystal_candidate ? "true" : "false" },
    { label: language === "ko" ? "Dream 질문" : "Dream questions", value: String(cortexStatus?.dream_questions ?? 0) },
    { label: language === "ko" ? "Local 기록" : "Local write", value: cortexLastCycle.local_brain_write ? (language === "ko" ? "기록함" : "on") : (language === "ko" ? "기록 안 함" : "off") },
  ];
  const cortexPanelState = cortexLastCycle.enabled
    ? (language === "ko" ? "활성 trace" : "TRACE ACTIVE")
    : (language === "ko" ? "대기" : "READY");
  const qCortexLastRun = (qCortexStatus?.last_run && typeof qCortexStatus.last_run === "object" && !Array.isArray(qCortexStatus.last_run))
    ? qCortexStatus.last_run as AnyRecord
    : {};
  const qCortexTrace = (qCortexLastRun.trace && typeof qCortexLastRun.trace === "object" && !Array.isArray(qCortexLastRun.trace))
    ? qCortexLastRun.trace as AnyRecord
    : {};
  const qCortexRows = [
    { label: language === "ko" ? "문제 유형" : "Problem", value: String(qCortexLastRun.problem_type ?? "idle") },
    { label: language === "ko" ? "Solver" : "Solver", value: String(qCortexLastRun.solver_name ?? "local") },
    { label: language === "ko" ? "입력" : "Inputs", value: String(qCortexLastRun.input_count ?? 0) },
    { label: language === "ko" ? "선택" : "Selected", value: String(qCortexLastRun.selected_count ?? 0) },
    { label: language === "ko" ? "목적값" : "Objective", value: Number.isFinite(Number(qCortexLastRun.objective_value)) ? Number(qCortexLastRun.objective_value).toFixed(2) : "0.00" },
    { label: language === "ko" ? "Baseline Δ" : "Baseline delta", value: Number.isFinite(Number(qCortexTrace.baseline_delta)) ? Number(qCortexTrace.baseline_delta).toFixed(2) : "0.00" },
    { label: language === "ko" ? "양자 HW" : "Quantum HW", value: qCortexStatus?.real_quantum_hardware_used ? "true" : "false" },
    { label: language === "ko" ? "Local 기록" : "Local write", value: qCortexStatus?.local_brain_write ? (language === "ko" ? "기록함" : "on") : (language === "ko" ? "기록 안 함" : "off") },
  ];
  const qCortexPanelState = qCortexStatus?.state === "active"
    ? (language === "ko" ? "고전 최적화" : "CLASSICAL OPTIMIZER")
    : (language === "ko" ? "대기" : "READY");
  const baseBrainPct = (value: unknown) => Number.isFinite(Number(value)) ? `${Math.round(Number(value) * 100)}%` : "-";
  const baseBrainRows = [
    { label: language === "ko" ? "팩" : "Pack", value: baseBrainStatus?.pack_exists ? "true" : "false" },
    { label: language === "ko" ? "Seed 관계" : "Seed relations", value: String(baseBrainStatus?.seed_relation_primitive_count ?? 0) },
    { label: language === "ko" ? "Semantic" : "Semantic", value: String(baseBrainStatus?.semantic_node_count ?? 0) },
    { label: language === "ko" ? "Relations" : "Relations", value: String(baseBrainStatus?.semantic_relation_count ?? 0) },
    { label: language === "ko" ? "Surface" : "Surface", value: String(baseBrainStatus?.surface_construction_count ?? 0) },
    { label: language === "ko" ? "Bench" : "Bench", value: String(baseBrainStatus?.benchmark_prompt_count ?? 0) },
    { label: "LLM", value: baseBrainStatus?.external_llm_used ? "true" : "false" },
    { label: "sLLM", value: baseBrainStatus?.external_sllm_used ? "true" : "false" },
  ];
  const baseBrainBenchmarkRows = [
    { label: language === "ko" ? "실행" : "Run", value: String(baseBrainBenchmark?.total_prompts ?? 0) },
    { label: language === "ko" ? "유용 답변" : "Useful", value: String(baseBrainBenchmark?.useful_answer_count ?? 0) },
    { label: language === "ko" ? "Trace hygiene" : "Trace hygiene", value: baseBrainPct(baseBrainBenchmark?.trace_hygiene_rate) },
    { label: language === "ko" ? "평균 품질" : "Avg quality", value: baseBrainPct(baseBrainBenchmark?.average_answer_quality) },
  ];
  const baseBrainPanelState = baseBrainRunning
    ? (language === "ko" ? "실행 중" : "RUNNING")
    : baseBrainStatus?.pack_exists
      ? (language === "ko" ? "팩 준비됨" : "PACK READY")
      : (language === "ko" ? "팩 대기" : "READY");
  const latestAnswerQualityRun = answerQualityRun ?? (
    answerQualityStatus?.latest_run && typeof answerQualityStatus.latest_run === "object" && !Array.isArray(answerQualityStatus.latest_run)
      ? answerQualityStatus.latest_run as AnyRecord
      : null
  );
  const answerQualityScores = (latestAnswerQualityRun?.average_scores && typeof latestAnswerQualityRun.average_scores === "object" && !Array.isArray(latestAnswerQualityRun.average_scores))
    ? latestAnswerQualityRun.average_scores as AnyRecord
    : {};
  const answerQualityCategories = (latestAnswerQualityRun?.category_scores && typeof latestAnswerQualityRun.category_scores === "object" && !Array.isArray(latestAnswerQualityRun.category_scores))
    ? latestAnswerQualityRun.category_scores as AnyRecord
    : {};
  const answerQualityFeedback = Array.isArray(latestAnswerQualityRun?.surface_feedback)
    ? latestAnswerQualityRun.surface_feedback as AnyRecord[]
    : [];
  const answerQualityWorstCases = Array.isArray(latestAnswerQualityRun?.worst_cases)
    ? latestAnswerQualityRun.worst_cases as AnyRecord[]
    : [];
  const answerQualityPct = (value: unknown) => Number.isFinite(Number(value)) ? `${Math.round(Number(value) * 100)}%` : "-";
  const answerQualityRows = [
    { label: language === "ko" ? "Overall" : "Overall", value: answerQualityPct(answerQualityScores.overall) },
    { label: language === "ko" ? "한국어 자연도" : "Korean naturalness", value: answerQualityPct((answerQualityCategories.korean_natural as AnyRecord | undefined)?.naturalness ?? answerQualityScores.naturalness) },
    { label: language === "ko" ? "영어 자연도" : "English naturalness", value: answerQualityPct((answerQualityCategories.english_answer as AnyRecord | undefined)?.naturalness ?? answerQualityScores.naturalness) },
    { label: language === "ko" ? "Trace hygiene" : "Trace hygiene", value: answerQualityPct(answerQualityScores.trace_hygiene) },
    { label: language === "ko" ? "Template score" : "Template score", value: answerQualityPct(answerQualityScores.template_smell) },
    { label: language === "ko" ? "Grounding" : "Grounding", value: answerQualityPct(answerQualityScores.grounding) },
    { label: language === "ko" ? "피드백" : "Feedback", value: String(answerQualityFeedback.length) },
    { label: language === "ko" ? "프롬프트" : "Prompts", value: String(latestAnswerQualityRun?.total_prompts ?? answerQualityStatus?.benchmark_prompts ?? 0) },
  ];
  const answerRepairRows = [
    { label: language === "ko" ? "Trace before" : "Trace before", value: answerQualityPct(answerRepairComparison?.trace_hygiene_before) },
    { label: language === "ko" ? "Trace after" : "Trace after", value: answerQualityPct(answerRepairComparison?.trace_hygiene_after) },
    { label: language === "ko" ? "Trace delta" : "Trace delta", value: Number.isFinite(Number(answerRepairComparison?.trace_hygiene_delta)) ? `${Math.round(Number(answerRepairComparison?.trace_hygiene_delta) * 100)}pt` : "-" },
    { label: language === "ko" ? "Overall delta" : "Overall delta", value: Number.isFinite(Number(answerRepairComparison?.overall_delta)) ? `${Math.round(Number(answerRepairComparison?.overall_delta) * 100)}pt` : "-" },
    { label: language === "ko" ? "수리 적용" : "Repairs", value: String(answerRepairComparison?.repairs_applied ?? 0) },
    { label: language === "ko" ? "남은 누출" : "Remaining leaks", value: String(Array.isArray(answerRepairComparison?.remaining_leakages) ? answerRepairComparison.remaining_leakages.length : 0) },
  ];
  const pendingRepairCandidates = repairCandidates.filter((item) => item.status === "pending");
  const approvedRepairCandidates = repairCandidates.filter((item) => item.status === "approved");
  const rejectedRepairCandidates = repairCandidates.filter((item) => item.status === "rejected");
  const enabledProductionRepairRules = productionRepairRules.filter((item) => item.enabled);
  const disabledProductionRepairRules = productionRepairRules.filter((item) => !item.enabled);
  const reviewQueueRows = [
    { label: language === "ko" ? "대기 후보" : "Pending", value: String(pendingRepairCandidates.length) },
    { label: language === "ko" ? "승인 후보" : "Approved", value: String(approvedRepairCandidates.length) },
    { label: language === "ko" ? "거절 후보" : "Rejected", value: String(rejectedRepairCandidates.length) },
    { label: language === "ko" ? "활성 규칙" : "Enabled rules", value: String(enabledProductionRepairRules.length) },
    { label: language === "ko" ? "비활성 규칙" : "Disabled rules", value: String(disabledProductionRepairRules.length) },
    { label: language === "ko" ? "감사 이벤트" : "Audit events", value: String(repairAuditEvents.length) },
  ];
  const answerQualityPanelState = answerQualityRunning
    ? (language === "ko" ? "측정 중" : "RUNNING")
    : answerRepairRunning
      ? (language === "ko" ? "수리 비교 중" : "REPAIR CHECK")
    : latestAnswerQualityRun
      ? (language === "ko" ? "최근 측정" : "LATEST RUN")
      : (language === "ko" ? "대기" : "READY");
  const atlasHub = (atlasStatus?.hub && typeof atlasStatus.hub === "object" && !Array.isArray(atlasStatus.hub))
    ? atlasStatus.hub as AnyRecord
    : { label: "Seoul Hub", lat: 37.5665, lng: 126.978 };
  const atlasNodes = Array.isArray(atlasStatus?.nodes) ? atlasStatus.nodes as AnyRecord[] : [];
  const atlasStats = (atlasStatus?.stats && typeof atlasStatus.stats === "object" && !Array.isArray(atlasStatus.stats))
    ? atlasStatus.stats as AnyRecord
    : {};
  const atlasRelay = (atlasStatus?.relay && typeof atlasStatus.relay === "object" && !Array.isArray(atlasStatus.relay))
    ? atlasStatus.relay as AnyRecord
    : { active_region: "East Asia", sequence: ["East Asia", "Europe", "North America", "Pacific"], status: "local_preview" };
  const atlasMyNode = (atlasStatus?.my_node && typeof atlasStatus.my_node === "object" && !Array.isArray(atlasStatus.my_node))
    ? atlasStatus.my_node as AnyRecord
    : {};
  const atlasPrivacy = (atlasStatus?.privacy && typeof atlasStatus.privacy === "object" && !Array.isArray(atlasStatus.privacy))
    ? atlasStatus.privacy as AnyRecord
    : {};
  const atlasMode = String(atlasStatus?.mode ?? "preview");
  const atlasProvider = String(atlasStatus?.provider ?? cloudProviderName ?? "local");
  const atlasBrokerState = String(atlasStatus?.broker_state ?? cloudBrokerState ?? "local_broker_mode");
  const atlasRemoteConnected = atlasBrokerState === "remote_connected";
  const atlasStatusCopy = atlasRemoteConnected
    ? (language === "ko" ? "Cloud Brain 원격 브로커에 연결되었습니다. 표시된 해외 릴레이 점은 실제 사용자 위치가 아니라 프리뷰 지역 신호입니다." : "Connected to the Cloud Brain remote broker. Overseas relay points are preview regional signals, not verified user locations.")
    : (language === "ko" ? "현재는 로컬/프리뷰 모드입니다. 글로벌 브레인 링크 네트워크는 아직 완전 활성화되지 않았습니다." : "Local/preview mode. The global Brain Link Network is not fully live yet.");
  const atlasRelaySequence = Array.isArray(atlasRelay.sequence) && atlasRelay.sequence.length
    ? atlasRelay.sequence.map((item) => String(item))
    : ["East Asia", "Europe", "North America", "Pacific"];
  const atlasUtcHour = clockNow ? clockNow.getUTCHours() : new Date().getUTCHours();
  const atlasComputedRelayRegion = atlasUtcHour <= 5
    ? "East Asia"
    : atlasUtcHour <= 11
      ? "Europe"
      : atlasUtcHour <= 18
        ? "North America"
        : "Pacific";
  const atlasActiveRelayRegion = String(atlasRelay.active_region ?? atlasComputedRelayRegion);
  const atlasRelayRegionLabel = (region: string) => {
    if (language !== "ko") return region;
    const labels: Record<string, string> = {
      "East Asia": "동아시아",
      Europe: "유럽",
      "North America": "북미",
      Pacific: "태평양",
    };
    return labels[region] ?? region;
  };
  const atlasDayNightAngle = Math.round((atlasUtcHour / 24) * 360 - 90);
  const atlasFragmentStore = String(
    cloudRemoteStatus?.storage && typeof cloudRemoteStatus.storage === "object" && !Array.isArray(cloudRemoteStatus.storage)
      ? (cloudRemoteStatus.storage as AnyRecord).fragment_store ?? "unknown"
      : atlasStatus?.fragment_store ?? "unknown",
  );
  const atlasHubPoint = projectAtlasPoint(
    Number(atlasHub.lat ?? 37.5665),
    Number(atlasHub.lng ?? 126.978) + atlasRotationDeg,
  );
  const atlasNodePoints = atlasNodes.map((node, index) => {
    const projected = projectAtlasPoint(Number(node.approximate_lat ?? 0), Number(node.approximate_lng ?? 0) + atlasRotationDeg);
    return {
      ...node,
      x: projected.x,
      y: projected.y,
      activity: Math.max(0.12, Math.min(1, Number(node.activity_level ?? 0.3))),
      state: String(node.state ?? "idle"),
      source: String(node.source ?? "preview"),
      key: String(node.display_id ?? `atlas-node-${index}`),
    };
  });
  const atlasGlobeNodes = useMemo(
    () => atlasNodes.map((node, index) => ({
      key: String(node.display_id ?? `atlas-node-${index}`),
      lat: Number(node.approximate_lat ?? 0),
      lng: Number(node.approximate_lng ?? 0),
                    activity: Math.max(0.12, Math.min(1, Number(node.activity_level ?? 0.3))),
                    state: String(node.state ?? "idle"),
                    source: String(node.source ?? "preview"),
                    role: String(node.role ?? ""),
                  })),
    [atlasNodes],
  );
  const atlasStatusCards = [
    { label: "Provider", value: atlasProvider },
    { label: "Broker", value: atlasBrokerState },
    { label: language === "ko" ? "Fragment Store" : "Fragment Store", value: atlasFragmentStore },
    { label: language === "ko" ? "활성 브레인 링크 노드" : "Active Brain Link Nodes", value: String(atlasStats.active_contributor_nodes ?? 0) },
    { label: language === "ko" ? "검증된 원격 노드" : "Verified Remote Nodes", value: String(atlasStats.verified_remote_contributor_nodes ?? 0) },
    { label: language === "ko" ? "공용 작업 / 분" : "Public Tasks / min", value: String(atlasStats.public_tasks_per_min ?? 0) },
  ];
  const atlasPrivacyRows = [
    { label: language === "ko" ? "Raw IP 저장" : "Raw IP stored", value: atlasPrivacy.raw_ip_stored ? "YES" : "NO" },
    { label: language === "ko" ? "정확 위치 표시" : "Exact location shown", value: atlasPrivacy.exact_location_shown ? "YES" : "NO" },
    { label: language === "ko" ? "개인 데이터 공유" : "Private data shared", value: atlasPrivacy.private_data_shared ? "YES" : "NO" },
    { label: language === "ko" ? "표시 정밀도" : "Display precision", value: String(atlasPrivacy.display_precision ?? "coarse_region_jittered") },
  ];
  const selectedMemoryTitle = selectedMemory
    ? String(selectedMemory.label ?? selectedMemory.id ?? "Selected Memory")
    : (language === "ko" ? "선택 대기" : "No node selected");
  const selectedMemoryDetail = selectedMemory
    ? String(selectedMemory.type ? memoryTypeText(String(selectedMemory.type)) : selectedMemory.id ?? "Graph node")
    : "";
  const epistemicRows = language === "ko"
    ? [
      { label: "Anchor", value: "Stable", tone: "green" },
      { label: "Evidence", value: cloudAssistRatio > 8 ? "Mixed" : "Partial", tone: "orange" },
      { label: "Noise Rejected", value: String(Math.max(1, Math.round(displayMemoryEdgeCount / Math.max(2200, displayMemoryNodeCount * 5)))), tone: "white" },
    ]
    : [
      { label: "Anchor", value: "Stable", tone: "green" },
      { label: "Evidence", value: cloudAssistRatio > 8 ? "Mixed" : "Partial", tone: "orange" },
      { label: "Noise Rejected", value: String(Math.max(1, Math.round(displayMemoryEdgeCount / Math.max(2200, displayMemoryNodeCount * 5)))), tone: "white" },
    ];
  const ontologyGuideTitle = language === "ko"
    ? "ATANOR에 오신 것을 환영합니다.\n당신의 통합 온톨로지 파트너."
    : "Welcome to ATANOR.\nYour unified ontology partner.";
  const ontologyGuideBody = language === "ko"
    ? "로컬 지식의 정확성과 Cloud Brain의 확장성을 함께 읽고, 연결하고, 검증합니다."
    : "It combines private precision with public breadth to reason, connect, and generate with confidence.";
  const activeSectionDetail: Record<MainSectionId, string> = {
    "live-scheduler": "Inspect opt-in Live Selfhood scheduler bounds and safety locks.",
    home: language === "ko" ? "그래프, 런타임, 생성 상태를 한 화면에서 봅니다." : "Overview of graph, runtime, and generation state.",
    graph: language === "ko" ? "통합 온톨로지 그래프를 탐색합니다." : "3D ontology graph exploration mode.",
    local: language === "ko" ? "로컬 브레인과 Payload Vault를 기준으로 대화합니다." : "Prioritizing Local Brain and Payload Vault.",
    cloud: language === "ko" ? "클라우드 브레인 Fragment와 브로커 상태를 읽기 전용으로 봅니다." : "Viewing Cloud Brain bridge status.",
    atlas: language === "ko" ? "익명 지역 단위로 Cloud Brain 브레인 링크 신호를 시각화합니다." : "Visualizing anonymous regional Cloud Brain Link signals.",
    congress: "AGORA proof-only agent congress.",
    "agent-os": "Proof-only Agentic Micro-OS status surface.",
    selfhood: language === "ko" ? "proof-only 자기 모델 런타임 상태와 승인 대기 제안을 봅니다." : "Proof-only self-model runtime state and approval-required proposals.",
    "memory-approval": language === "ko" ? "Local Brain 쓰기 없이 메모리 후보를 검토합니다." : "Review proposed memories while Local Brain writes stay locked.",
    graphhub: language === "ko" ? "Graph Cartridge를 설치하고 읽기 전용으로 연결합니다." : "Install and attach Graph Cartridges read-only.",
    autonomous: language === "ko" ? "자율 실행 모드 및 PHFE 드라이버 상태를 봅니다." : "View autonomous mode and PHFE driver status.",
    contribute: language === "ko" ? "유휴 자원을 안전하게 Cloud Brain 검증에 연결합니다." : "Link safe idle compute to the Cloud Brain.",
    chat: language === "ko" ? "로컬 브레인과 대화합니다." : "Chat with the Local Brain.",
    settings: language === "ko" ? "언어와 로컬 Companion 동기화 상태를 조정합니다." : "Language and local companion sync controls.",
  };

  const visibleMainNav = copy.nav.filter((item) => mainSectionSurface[item.id] === "product");
  const labMainNav: typeof copy.nav = [];

  function setMainLanguage(nextLanguage: Language) {
    setLanguage(nextLanguage);
    writeBrowserStorage("atanor.uiLanguage", nextLanguage);
    const url = new URL(window.location.href);
    url.searchParams.set("lang", nextLanguage);
    window.history.replaceState(null, "", url);
  }

  function openMainSection(id: MainSectionId) {
    setMainSection(id);
    setSelectedMemory(null);
    if (id === "home") {
      changeWorkspaceMode("lab");
      changeLayoutMode("split");
      setRightMode("process");
      resetGraph();
      return;
    }
    if (id === "graph") {
      changeWorkspaceMode("lab");
      changeLayoutMode("graph");
      setRightMode("process");
      resetGraph();
      return;
    }
    if (id === "local") {
      changeWorkspaceMode("lab");
      changeLayoutMode("split");
      setRightMode("process");
      setGraphSourceMode("memory");
      resetGraph();
      return;
    }
    if (id === "cloud") {
      changeWorkspaceMode("lab");
      changeLayoutMode("split");
      setRightMode("process");
      setGraphSourceMode("memory");
      resetGraph();
      return;
    }
    if (id === "atlas") {
      changeWorkspaceMode("daemon");
      changeLayoutMode("split");
      setRightMode("process");
      return;
    }
    if (id === "contribute") {
      changeWorkspaceMode("lab");
      changeLayoutMode("split");
      setRightMode("process");
      return;
    }
    if (id === "chat") {
      changeWorkspaceMode("lab");
      changeLayoutMode("split");
      setRightMode("chat");
      return;
    }
    changeLayoutMode("workbench");
    setRightMode("process");
  }

  async function enableContribution() {
    setContributionEnabled(true);
    setContributionPaused(false);
    if (!localBackendConnected) {
      setError(language === "ko" ? "로컬 Companion 연결 후 브레인 링크 노드를 시작할 수 있습니다." : "Connect the local companion before starting Brain Link Node.");
      return;
    }
    await directBackendJson<AnyRecord>(localBackendUrl, "/api/contribution/settings", {
      method: "POST",
      body: JSON.stringify({
        cpu_limit_percent: contributionCpuLimit,
        gpu_enabled: contributionGpuLimit > 0,
        gpu_limit_percent: contributionGpuLimit,
        ram_limit_gb: 2,
        battery_pause: true,
        thermal_pause: true,
      }),
    });
    await directBackendJson<AnyRecord>(localBackendUrl, "/api/contribution/register", { method: "POST" });
    const response = await directBackendJson<AnyRecord>(localBackendUrl, "/api/contribution/run-once", { method: "POST" });
    setContributionStatus(response);
    await refreshAll();
  }

  async function pauseContribution() {
    setContributionPaused(true);
    if (localBackendConnected) {
      const response = await directBackendJson<AnyRecord>(localBackendUrl, "/api/contribution/pause", { method: "POST" }).catch(() => null);
      if (response) setContributionStatus(response);
    }
  }

  async function resumeContribution() {
    setContributionEnabled(true);
    setContributionPaused(false);
    if (localBackendConnected) {
      const response = await directBackendJson<AnyRecord>(localBackendUrl, "/api/contribution/resume", { method: "POST" }).catch(() => null);
      if (response) setContributionStatus(response);
    }
  }

  async function handleGraphHubPrimary(item: AnyRecord) {
    const cartridgeId = String(item.cartridge_id);
    const pricingModel = String(item.pricing_model ?? "free");
    const entitlementStatus = String(item.entitlement_status ?? "locked");
    const installed = Boolean(item.installed);
    const attached = graphHubAttachments.some((row) => row.cartridge_id === cartridgeId && row.status === "attached");
    setGraphHubRunning(cartridgeId);
    setGraphHubError(null);
    try {
      if (attached) {
        await apiJson<AnyRecord>(`/api/graph-hub/detach/${encodeURIComponent(cartridgeId)}`, { method: "POST" }, localBackendConnected ? { localOnly: true } : {});
      } else if (pricingModel === "free" && entitlementStatus === "locked") {
        await apiJson<AnyRecord>(`/api/graph-hub/entitlements/free/${encodeURIComponent(cartridgeId)}`, { method: "POST" }, localBackendConnected ? { localOnly: true } : {});
        await apiJson<AnyRecord>(`/api/graph-hub/install/${encodeURIComponent(cartridgeId)}`, { method: "POST" }, localBackendConnected ? { localOnly: true } : {});
      } else if (pricingModel === "one_time" && entitlementStatus !== "owned") {
        await apiJson<AnyRecord>(`/api/graph-hub/entitlements/local-one-time-simulation/${encodeURIComponent(cartridgeId)}`, { method: "POST" }, localBackendConnected ? { localOnly: true } : {});
      } else if (pricingModel === "subscription" && entitlementStatus !== "active_subscription") {
        await apiJson<AnyRecord>(`/api/graph-hub/entitlements/local-subscription-simulation/${encodeURIComponent(cartridgeId)}`, { method: "POST" }, localBackendConnected ? { localOnly: true } : {});
      } else if (!installed) {
        await apiJson<AnyRecord>(`/api/graph-hub/install/${encodeURIComponent(cartridgeId)}`, { method: "POST" }, localBackendConnected ? { localOnly: true } : {});
      } else {
        await apiJson<AnyRecord>(`/api/graph-hub/attach/${encodeURIComponent(cartridgeId)}`, {
          method: "POST",
          body: JSON.stringify({ scope: "session", read_only: true }),
        }, localBackendConnected ? { localOnly: true } : {});
      }
      await refreshGraphHub();
      const cloudGraph = await fetchJson<AnyRecord>(brainGraphApiPath("cloud", cloudBrainGraphLayers, "full")).catch(() => null);
      if (cloudGraph) setBrainGraphCloud(cloudGraph);
    } catch (caught) {
      setGraphHubError(caught instanceof Error ? caught.message : "Graph Hub action failed.");
    } finally {
      setGraphHubRunning(null);
    }
  }

  function graphHubPrimaryLabel(item: AnyRecord) {
    const pricingModel = String(item.pricing_model ?? "free");
    const entitlementStatus = String(item.entitlement_status ?? "locked");
    const installed = Boolean(item.installed);
    const attached = graphHubAttachments.some((row) => row.cartridge_id === item.cartridge_id && row.status === "attached");
    if (attached) return language === "ko" ? "분리" : "Detach";
    if (pricingModel === "free" && entitlementStatus === "locked") return language === "ko" ? "검사 후 설치" : "Inspect & install";
    if (pricingModel === "one_time" && entitlementStatus !== "owned") return language === "ko" ? "로컬 접근 확인" : "Verify local access";
    if (pricingModel === "subscription" && entitlementStatus !== "active_subscription") return language === "ko" ? "접근 상태 확인" : "Verify access";
    if (!installed) return language === "ko" ? "설치" : "Install";
    return language === "ko" ? "읽기 전용 연결" : "Attach read-only";
  }

  function isMainSectionActive(id: MainSectionId) {
    return mainSection === id;
  }

  function startNewConversation() {
    setMainSection("local");
    changeWorkspaceMode("lab");
    changeLayoutMode("split");
    setRightMode("chat");
    setChatInput("");
    setChatMessages([{ role: "assistant", text: EFFECTIVE_INITIAL_ASSISTANT_MESSAGE[language] }]);
  }

  const quickActions = [
    { label: copy.actions.newChat, action: startNewConversation },
    { label: copy.actions.graphExplore, action: () => openMainSection("graph") },
    { label: copy.actions.memorySearch, action: () => {
      openMainSection("local");
      setMemoryQuery("GraphRAG");
      activateSignal(signalTraceForQuery("GraphRAG", visibleGraph3D), 6000);
      focusSearchResult();
    } },
    { label: copy.actions.learningTrigger, action: () => runAction(startLearningDaemon) },
    { label: copy.actions.checkpoint, action: () => runAction(checkpointLearningDaemon) },
  ];

  const graphHubCategories = useMemo(() => {
    const categories = graphHubCatalog
      .map((item) => String(item.category ?? "general").trim())
      .filter(Boolean);
    return ["all", ...Array.from(new Set(categories))];
  }, [graphHubCatalog]);



  function graphHubAccessLabel(item: AnyRecord) {
    const pricingModel = String(item.pricing_model ?? "free");
    if (pricingModel === "one_time") return language === "ko" ? "로컬 접근" : "Local access";
    if (pricingModel === "subscription") return language === "ko" ? "관리형 접근" : "Managed access";
    return language === "ko" ? "포함됨" : "Included";
  }

  function graphHubSafeText(value: unknown) {
    return String(value ?? "")
      .replace(/\bpricing\b/gi, "positioning")
      .replace(/\bprice\b/gi, "access")
      .replace(/\bbilling\b/gi, "access")
      .replace(/\bpayment\b/gi, "access")
      .replace(/\bbuy\b/gi, "verify")
      .replace(/\bpurchase\b/gi, "verify")
      .replace(/\bsubscription\b/gi, "managed access")
      .replace(/구독/g, "접근")
      .replace(/구매/g, "확인");
  }

  const visibleGraphHubCatalog = useMemo(() => {
    const query = graphHubSearch.trim().toLowerCase();
    return graphHubCatalog.filter((item) => {
      const category = String(item.category ?? "general");
      const haystack = [
        item.name,
        item.subtitle,
        item.description,
        item.category,
        ...(Array.isArray(item.tags) ? item.tags : []),
      ].join(" ").toLowerCase();
      return (graphHubCategoryFilter === "all" || category === graphHubCategoryFilter)
        && (!query || haystack.includes(query));
    });
  }, [graphHubCatalog, graphHubCategoryFilter, graphHubSearch]);

  return (
    <main className="atanor-user-shell" data-language={language} data-section={mainSection} data-answering={mainSection === "home" && transcriptOpen} data-presence={transcriptOpen ? "conversation" : "ambient"}>
      <aside className="atanor-user-sidebar">
        <div className="atanor-user-brand">
          <img
            src="/atanor-logo-white-cropped.png"
            alt="ATANOR"
            onError={(event) => {
              event.currentTarget.style.display = "none";
            }}
          />
          <span data-demo-badge={demoView ? "true" : "false"}>{demoView ? "DEMO" : "Ultimate"}</span>
        </div>
        <nav className="atanor-user-nav" aria-label="ATANOR sections">
          {visibleMainNav.map((item) => {
            const Icon = mainNavIcon[item.id];
            return (
              <button key={item.id} data-active={isMainSectionActive(item.id)} onClick={() => openMainSection(item.id)}>
                <span aria-hidden="true"><Icon size={17} strokeWidth={1.8} /></span>
                <strong>{item.label}</strong>
              </button>
            );
          })}
          {labMainNav.length ? <small className="atanor-user-nav-group">{language === "ko" ? "Lab / Developer" : "Lab / Developer"}</small> : null}
          {labMainNav.map((item) => {
            const Icon = mainNavIcon[item.id];
            return (
              <button key={item.id} data-active={isMainSectionActive(item.id)} data-surface={mainSectionSurface[item.id]} onClick={() => openMainSection(item.id)}>
                <span aria-hidden="true"><Icon size={17} strokeWidth={1.8} /></span>
                <strong>{item.label}</strong>
              </button>
            );
          })}
        </nav>
        <div className="atanor-user-connection">
          <span><i data-tone="green" />{copy.localBrain}</span>
          <strong>{localBackendConnected ? copy.connected : language === "ko" ? "대기" : "Fallback"}</strong>
          <span><i data-tone="blue" />{copy.cloudBrain}</span>
          <strong>{workspaceMode === "daemon" ? copy.connected : language === "ko" ? "뷰어" : "Viewer"}</strong>
        </div>
      </aside>

      <section className="atanor-user-main">
        {demoView ? null : (
          <button
            type="button"
            className="atanor-transcript-toggle"
            data-open={transcriptOpen}
            onClick={() => setTranscriptOpen((value) => !value)}
            aria-label={language === "ko"
              ? (transcriptOpen ? "음성 모드로 (대화록 접기)" : "대화 모드로 (대화록 펼치기)")
              : (transcriptOpen ? "Voice mode" : "Conversation mode")}
            title={language === "ko"
              ? (transcriptOpen ? "음성 모드 — 수족관만 두고 말로 대화" : "대화 모드 — 대화록과 화면을 펼치기")
              : (transcriptOpen ? "Voice mode" : "Conversation mode")}
          >
            {transcriptOpen ? <Mic size={16} strokeWidth={1.9} /> : <MessageCircle size={16} strokeWidth={1.9} />}
          </button>
        )}
        {transcriptOpen ? (
          <button
            type="button"
            className="atanor-transcript-backdrop"
            aria-label={language === "ko" ? "대화록 닫기" : "Close transcript"}
            onClick={() => setTranscriptOpen(false)}
          />
        ) : null}
        <aside className="atanor-transcript-drawer" data-open={transcriptOpen} aria-hidden={!transcriptOpen}>
          <div className="atanor-transcript-head">
            <strong>{language === "ko" ? "대화록" : "Transcript"}</strong>
            <button type="button" onClick={() => setTranscriptOpen(false)} aria-label={language === "ko" ? "닫기" : "Close"}>×</button>
          </div>
          <div className="atanor-transcript-body">
            {chatMessages.length === 0 ? (
              <p className="atanor-transcript-empty">{language === "ko" ? "아직 대화가 없어요." : "No conversation yet."}</p>
            ) : (
              chatMessages.map((message, index) => (
                <div key={index} className="atanor-transcript-turn" data-role={message.role}>
                  <span>{message.role === "user" ? (language === "ko" ? "나" : "You") : "ATANOR"}</span>
                  <p>{message.text}</p>
                </div>
              ))
            )}
          </div>
        </aside>
        <header className="atanor-user-topbar">
          <div className="atanor-user-topbar-spacer" aria-hidden="true" />
          <div className="atanor-user-top-actions">
            <span className="atanor-user-clock">{clockNow ? clockNow.toLocaleTimeString(language === "ko" ? "ko-KR" : "en-US") : "--:--:--"}</span>
            <div className="atanor-user-language" aria-label="Language">
              <button data-active={language === "en"} onClick={() => setMainLanguage("en")}>EN</button>
              <button data-active={language === "ko"} onClick={() => setMainLanguage("ko")}>KO</button>
            </div>
            <button
              className="atanor-user-icon-button"
              onClick={() => setThemePref((p) => (p === "auto" ? "light" : p === "light" ? "dark" : "auto"))}
              aria-label={language === "ko" ? "테마 전환" : "Toggle theme"}
              title={
                themePref === "auto"
                  ? (language === "ko" ? "테마: 자동 (온라인=밝게 / 로컬=어둡게)" : "Theme: auto (online=light / local=dark)")
                  : themePref === "light"
                    ? (language === "ko" ? "테마: 밝게 고정" : "Theme: light")
                    : (language === "ko" ? "테마: 어둡게 고정" : "Theme: dark")
              }
            >
              {themePref === "auto" ? <SunMoon size={16} strokeWidth={1.8} /> : themePref === "light" ? <Sun size={16} strokeWidth={1.8} /> : <Moon size={16} strokeWidth={1.8} />}
            </button>
            <span className="atanor-user-settled-badge"><i />{copy.graphSettled}</span>
            <button
              className="atanor-user-icon-button"
              onClick={() => runAction(refreshAll)}
              aria-label={language === "ko" ? "상태 새로고침" : "Refresh status alerts"}
              title={language === "ko" ? "상태 새로고침" : "Refresh status alerts"}
            >
              <Bell size={16} strokeWidth={1.8} />
            </button>
            <button
              className="atanor-user-icon-button"
              data-active={mainSection === "settings"}
              onClick={() => openMainSection("settings")}
              aria-label={language === "ko" ? "설정 열기" : "Open settings"}
              title={language === "ko" ? "설정 열기" : "Open settings"}
            >
              <UserCircle size={18} strokeWidth={1.8} />
            </button>
            <button className="atanor-user-sync-button" onClick={() => runAction(refreshAll)} aria-label={copy.sync}>
              <RefreshCw size={14} strokeWidth={1.8} />
              <span>{copy.sync}</span>
            </button>
          </div>
        </header>

        {engineDown ? (
          <div className="atanor-engine-banner" role="alert">
            <span>
              {language === "ko"
                ? "로컬 엔진에 연결할 수 없어요 — 엔진이 꺼져 있을 수 있습니다. 그래프·채팅·학습 상태가 표시되지 않습니다."
                : "Can't reach the local engine — it may be offline. Graph, chat, and learning status are unavailable."}
            </span>
            <button type="button" onClick={() => setEnginePingNonce((n) => n + 1)}>
              {language === "ko" ? "다시 연결" : "Reconnect"}
            </button>
          </div>
        ) : null}
        {/* "Local engine sync pending" badge removed — it fired on any transient fetch error
            even while fully connected, reading as a broken product (owner: 안 나오게).
            The engineDown banner above already covers the real outage case. */}

        {/* overnight "while you were away" briefing removed per owner — noise (low-signal auto-summaries) */}
        {mainSection === "home" && !demoView ? <DashboardImaginationLayer /> : null}
        {mainSection === "home" ? (
          demoView ? (
            <DemoChat language={language} />
          ) : (
            <AtanorUserStatusCard language={language} onMessageSubmit={handleHologramMessage} />
          )
        ) : null}

        {mainSection === "atlas" ? (
          <section className="atanor-atlas-grid">
            <article className="atanor-atlas-hero">
              <header>
                <div>
                  <span>{language === "ko" ? "Cloud Brain Relay Preview" : "Cloud Brain Relay Preview"}</span>
                  <h2>ATANOR Atlas</h2>
                  <p>
                    {language === "ko"
                      ? "원격 브로커 연결 상태와 익명 지역 릴레이 프리뷰를 개인정보 없이 시각화합니다."
                      : "Privacy-safe visualization of remote broker state and anonymous regional relay preview."}
                  </p>
                </div>
                <strong data-remote={atlasRemoteConnected}>
                  <i />
                  {atlasRemoteConnected ? "REMOTE CONNECTED" : atlasMode.toUpperCase()}
                </strong>
              </header>
              <div
                className="atanor-atlas-stage"
                aria-label={language === "ko" ? "익명 지역 단위 Cloud Brain 동기화 지도" : "Anonymous regional Cloud Brain sync map"}
              >
                <AtlasGlobe3D
                  hub={{
                    lat: Number(atlasHub.lat ?? 37.5665),
                    lng: Number(atlasHub.lng ?? 126.978),
                  }}
                  language={language}
                  remoteConnected={atlasRemoteConnected}
                  nodes={atlasGlobeNodes}
                />
                <div className="atanor-atlas-caption">
                  <strong>{language === "ko" ? "서울 허브 릴레이" : "Seoul Hub Relay"}</strong>
                  <span>
                    {language === "ko"
                      ? "실제 WebGL 지구 · 공용 Fragment 검증 신호는 프리뷰 지역 점으로 표시됩니다. Raw IP, 정확 위치, 기기명, 개인 데이터는 표시하지 않습니다."
                      : "Real WebGL Earth · Public fragment verification signals are shown as preview regional points. No raw IP, exact location, device name, or private data is displayed."}
                  </span>
                </div>
              </div>
            </article>

            {/* Atlas status side rail removed (owner: preview-mode 상태 나열은 사용자 친화적이지
                않음 — 제거). The Earth visual is the Atlas surface; the live cumulative-learning
                view will land here in a follow-up. */}
          </section>
        ) : mainSection === "congress" ? (
          <AtlasCongressPanel language={language} />
        ) : mainSection === "agent-os" ? (
          <AgenticMicroOSPanel language={language} localBackendUrl={localBackendUrl} />
        ) : mainSection === "autonomous" ? (
          <AutonomousAgentPanel language={language} />
        ) : mainSection === "selfhood" ? (
          <SelfhoodRuntimePanel language={language} />
        ) : mainSection === "live-scheduler" ? (
          <LiveSelfhoodSchedulerPanel language={language} />
        ) : mainSection === "memory-approval" ? (
          <MemoryApprovalPanel language={language} />
        ) : mainSection === "graphhub" ? (
          <section className="atanor-graph-hub">
            <header className="atanor-graph-hub-hero">
              <div>
                <h2>Custom Hub</h2>
                <p>{language === "ko"
                  ? "용량에 맞게 능력을 더하세요 — 지식 그래프(Graph), 디바이스 능력(Device), 캐릭터(Ato). 무거운 건 필요할 때만."
                  : "Add abilities to fit your disk — knowledge Graphs, Device abilities, and the Ato character. Heavy ones only when you need them."}</p>
              </div>
              <button className="atanor-graph-hub-refresh" type="button" onClick={() => refreshGraphHub().catch(() => undefined)}>
                {language === "ko" ? "새로고침" : "Refresh"}
              </button>
            </header>

            {/* Device & Ato zones — capacity-aware capability plugins (face recognition, object
                detection, humanoid rig, character). The knowledge-cartridge marketplace below is
                the Graph zone. */}
            <CustomHubDevicePanel language={language} />
            <h3 style={{ margin: "6px 0 12px", fontSize: 12, letterSpacing: "0.08em",
              textTransform: "uppercase", color: "#cdd6e8", display: "flex", alignItems: "center", gap: 7 }}>
              <Package size={14} style={{ color: "#ff8a00" }} /> {language === "ko" ? "그래프 · 지식 카트리지" : "Graph · Knowledge Cartridges"}
            </h3>

            <nav className="atanor-graph-hub-tabs" aria-label="Graph Hub views">
              {[
                ["catalog", language === "ko" ? "Catalog" : "Catalog"],
                ["installed", language === "ko" ? "Installed" : "Installed"],
                ["attachments", language === "ko" ? "Active Attachments" : "Active Attachments"],
                ["export", "Export"],
                ["audit", language === "ko" ? "Audit Log" : "Audit Log"],
              ].map(([id, label]) => (
                <button key={id} type="button" data-active={graphHubTab === id} onClick={() => setGraphHubTab(id as typeof graphHubTab)}>
                  <span>{label}</span>
                </button>
              ))}
            </nav>

            {graphHubTab === "catalog" ? (
              <article className="atanor-graph-hub-toolbar">
                <input
                  value={graphHubSearch}
                  onChange={(event) => setGraphHubSearch(event.currentTarget.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") refreshGraphHub().catch(() => undefined);
                  }}
                  placeholder={language === "ko" ? "카트리지 검색" : "Search cartridges"}
                />
                <div className="atanor-graph-hub-filters">
                  {graphHubCategories.map((filter) => (
                    <button key={filter} data-active={graphHubCategoryFilter === filter} onClick={() => setGraphHubCategoryFilter(filter)}>
                      {filter === "all" ? "All" : filter}
                    </button>
                  ))}
                </div>
                <div className="atanor-graph-hub-filters">
                  {["all", "free", "one_time", "subscription"].map((filter) => (
                    <button key={filter} data-active={graphHubPricingFilter === filter} onClick={() => setGraphHubPricingFilter(filter)}>
                      {filter === "all" ? "All" : filter === "one_time" ? (language === "ko" ? "로컬 접근" : "Local access") : filter === "subscription" ? (language === "ko" ? "관리형 접근" : "Managed access") : (language === "ko" ? "포함됨" : "Included")}
                    </button>
                  ))}
                </div>
              </article>
            ) : null}

            {graphHubError ? <p className="atanor-user-error">{graphHubError}</p> : null}

            {graphHubTab === "catalog" ? (
              <section className="atanor-graph-hub-grid">
              {visibleGraphHubCatalog.map((item) => {
                const attached = graphHubAttachments.some((row) => row.cartridge_id === item.cartridge_id && row.status === "attached");
                const title = String(item.name ?? "Graph Cartridge");
                const initial = title.trim().slice(0, 1).toUpperCase();
                const cartridgeId = String(item.cartridge_id);
                const previewState = graphHubPreviews[cartridgeId];
                const previewNodes = Array.isArray(previewState) && previewState.length ? previewState : null;
                const profile = graphHubProfiles[cartridgeId];
                const synergy = graphHubSynergy[cartridgeId];
                const trial = graphHubTrials[cartridgeId];
                const trialActive = trial && !["detached", "exhausted", "expired", "failed"].includes(String(trial.state));
                return (
                  <article className="atanor-graph-hub-card" key={cartridgeId} data-attached={attached}>
                    <div className="atanor-graph-hub-cover" data-tone={String(item.category ?? "general")} data-graph={(graphHubSnapshots[cartridgeId] || previewNodes) ? "true" : "false"}>
                      {graphHubSnapshots[cartridgeId]
                        ? <img className="atanor-graph-hub-render" src={graphHubSnapshots[cartridgeId]} alt="" loading="lazy" />
                        : previewNodes
                          ? <GraphHubFragmentThumb nodes={previewNodes} />
                          : <span>{initial}</span>}
                      <i />
                    </div>
                    <header>
                      <span>{String(item.category ?? "general")}</span>
                      <strong>{item.verified_author ? (language === "ko" ? "Verified" : "Verified") : (language === "ko" ? "Local" : "Local")}</strong>
                    </header>
                    <h3>{title}</h3>
                    <p>{graphHubSafeText(item.subtitle)}</p>
                    <div className="atanor-graph-hub-badges">
                      <span>{graphHubAccessLabel(item)}</span>
                      {item.installed ? <span>{language === "ko" ? "Installed" : "Installed"}</span> : null}
                    </div>
                    <div className="atanor-graph-hub-card-actions">
                      <button disabled={graphHubRunning === item.cartridge_id} onClick={() => handleGraphHubPrimary(item)}>
                        <span>{graphHubRunning === item.cartridge_id ? (language === "ko" ? "처리 중" : "Working") : graphHubPrimaryLabel(item)}</span>
                      </button>
                      {item.installed ? (
                        <button
                          type="button"
                          onClick={() => runGraphHubAction(`uninstall-${String(item.cartridge_id)}`, `/api/graph-hub/uninstall/${encodeURIComponent(String(item.cartridge_id))}`)}
                        >
                          <span>{language === "ko" ? "설치 해제" : "Uninstall"}</span>
                        </button>
                      ) : null}
                      {item.pricing_model === "subscription" && item.entitlement_status === "active_subscription" ? (
                        <button
                          type="button"
                          onClick={() => runGraphHubAction(`expire-${String(item.cartridge_id)}`, `/api/graph-hub/entitlements/expire/${encodeURIComponent(String(item.cartridge_id))}`)}
                        >
                          <span>{language === "ko" ? "접근 관리" : "Manage access"}</span>
                        </button>
                      ) : null}
                      {item.installed ? (
                        <button type="button" disabled={graphHubRunning === `inspect-${cartridgeId}`} onClick={() => inspectGraphHubCartridge(item)}>
                          <span>{language === "ko" ? "검사" : "Inspect"}</span>
                        </button>
                      ) : null}
                      {item.installed ? (
                        <button type="button" disabled={graphHubRunning === `trial-${cartridgeId}`} onClick={() => startGraphHubTrial(item)}>
                          <span>{language === "ko" ? "샌드박스" : "Sandbox"}</span>
                        </button>
                      ) : null}
                    </div>
                    {(profile || synergy || trial) ? (
                      <section className="atanor-graph-hub-trial-panel" aria-label={language === "ko" ? "카트리지 검사 및 샌드박스" : "Cartridge inspection and sandbox"}>
                        {profile ? (
                          <p>
                            <span>{language === "ko" ? "검사" : "Profile"}</span>
                            <strong>{String(profile.inspection_status ?? "unknown")} · {Math.round(Number(profile.soundness_score ?? 0) * 100)}%</strong>
                          </p>
                        ) : null}
                        {synergy ? (
                          <p>
                            <span>{language === "ko" ? "호환성" : "Synergy"}</span>
                            <strong>{Math.round(Number(synergy.constructive_interference_pct ?? 0))}% · {synergy.safe_to_trial ? "safe" : "review"}</strong>
                          </p>
                        ) : null}
                        {trial ? (
                          <>
                            <p>
                              <span>{language === "ko" ? "샌드박스" : "Sandbox"}</span>
                              <strong>{String(trial.state ?? "active")} · {String(trial.remaining_queries ?? 0)}/5</strong>
                            </p>
                            <p>
                              <span>{language === "ko" ? "Local write" : "Local write"}</span>
                              <strong>{String(trial.local_write ?? false)}</strong>
                            </p>
                            {trialActive ? (
                              <div className="atanor-graph-hub-trial-query">
                                <input
                                  value={graphHubTrialInputs[cartridgeId] ?? ""}
                                  onChange={(event) => setGraphHubTrialInputs((current) => ({ ...current, [cartridgeId]: event.currentTarget.value }))}
                                  placeholder={language === "ko" ? "샌드박스 질문" : "Sandbox query"}
                                />
                                <button type="button" disabled={graphHubRunning === `trial-query-${cartridgeId}`} onClick={() => runGraphHubTrialQuery(item)}>
                                  <span>{language === "ko" ? "질문" : "Ask"}</span>
                                </button>
                              </div>
                            ) : null}
                          </>
                        ) : null}
                      </section>
                    ) : null}
                  </article>
                );
              })}
              {!visibleGraphHubCatalog.length && graphHubLoading
                ? Array.from({ length: 12 }).map((_, index) => (
                    <article className="atanor-graph-hub-card atanor-graph-hub-skeleton" key={`gh-skeleton-${index}`} aria-hidden="true">
                      <div className="atanor-graph-hub-cover atanor-graph-hub-skel-cover" />
                      <div className="atanor-graph-hub-skel-line" style={{ width: "42%" }} />
                      <div className="atanor-graph-hub-skel-line" style={{ width: "82%" }} />
                      <div className="atanor-graph-hub-skel-line" style={{ width: "64%" }} />
                      <div className="atanor-graph-hub-skel-btn" />
                    </article>
                  ))
                : null}
              {!visibleGraphHubCatalog.length && !graphHubLoading ? (
                <article className="atanor-graph-hub-card">
                  <div className="atanor-graph-hub-cover">
                    <span>G</span>
                    <i />
                  </div>
                  <header>
                    <span>EMPTY</span>
                    <strong>Graph Hub</strong>
                  </header>
                  <h3>{language === "ko" ? "검색 결과가 없습니다" : "No cartridges found"}</h3>
                  <p>{language === "ko" ? "검색어나 필터를 조정해보세요." : "Try adjusting your search or filters."}</p>
                </article>
              ) : null}
              </section>
            ) : null}

            {graphHubTab !== "catalog" ? (
              <section className="atanor-graph-hub-lower">
              {graphHubTab === "installed" ? (
              <article>
                <h2>{language === "ko" ? "Installed Graphs" : "Installed Graphs"}</h2>
                {graphHubInstalled.length ? graphHubInstalled.map((item) => (
                  <p key={String(item.cartridge_id)}>
                    <span>{String(item.cartridge_id)}</span>
                    <strong>{String(item.entitlement_status ?? "unknown")}</strong>
                  </p>
                )) : <p>{graphHubLoading ? (language === "ko" ? "불러오는 중…" : "Loading…") : (language === "ko" ? "설치된 Graph Cartridge가 없습니다." : "No installed Graph Cartridges.")}</p>}
              </article>
              ) : null}
              {graphHubTab === "attachments" ? (
              <article>
                <h2>{language === "ko" ? "Active Graph Attachments" : "Active Graph Attachments"}</h2>
                {graphHubAttachments.length ? graphHubAttachments.map((item, index) => (
                  <p key={`${String(item.attachment_id ?? item.cartridge_id)}-${index}`}>
                    <span>{String(item.cartridge_id)}</span>
                    <strong>{String(item.status)} · {String(item.working_memory_nodes ?? 0)}n</strong>
                  </p>
                )) : <p>{language === "ko" ? "활성 연결이 없습니다." : "No active attachments."}</p>}
              </article>
              ) : null}
              {graphHubTab === "export" ? (
              <article>
                <h2>Export</h2>
                <button
                  className="atanor-graph-hub-panel-action"
                  type="button"
                  disabled={graphHubRunning === "export"}
                  onClick={() => runGraphHubAction("export", "/api/graph-hub/export/semantic-cloud", {
                    cartridge_id: "semantic_cloud_kubernetes_demo",
                    name: "Semantic Cloud Kubernetes Demo",
                    description: "A small real proof-store export from the Semantic Cloud Growth Loop.",
                    pricing_model: "free",
                    limit_nodes: 100,
                    limit_edges: 300,
                  })}
                >
                  {language === "ko" ? "Semantic Cloud Demo 내보내기" : "Export Semantic Cloud Demo"}
                </button>
                <button
                  className="atanor-graph-hub-panel-action"
                  type="button"
                  disabled={graphHubRunning === "proof"}
                  onClick={() => runGraphHubAction("proof", "/api/graph-hub/proof")}
                >
                  {language === "ko" ? "Graph Hub 증명" : "Run Proof"}
                </button>
                {graphHubExport ? <p><span>{language === "ko" ? "최근 내보내기" : "Latest export"}</span><strong>{String(graphHubExport.exported_nodes ?? 0)} / {String(graphHubExport.exported_edges ?? 0)}</strong></p> : null}
                {graphHubProof ? <p><span>{language === "ko" ? "Proof" : "Proof"}</span><strong>{graphHubProof.passed ? "PASS" : "FAIL"}</strong></p> : null}
              </article>
              ) : null}
              {graphHubTab === "audit" ? (
              <article>
                <h2>{language === "ko" ? "Audit Log" : "Audit Log"}</h2>
                {graphHubAudit.slice(0, 5).map((event, index) => (
                  <p key={`${String(event.event_id)}-${index}`}>
                    <span>{String(event.event_type)}</span>
                    <strong>{String(event.cartridge_id ?? "Graph Hub")}</strong>
                  </p>
                ))}
              </article>
              ) : null}
              </section>
            ) : null}
          </section>
        ) : mainSection === "settings" ? (
          <section className="atanor-settings-grid">
            <article className="atanor-settings-hero">
              <div>
                <span>SYSTEM SETTINGS</span>
                <h2>{language === "ko" ? "ATANOR 실행 환경" : "ATANOR Runtime Control"}</h2>
                <p>
                  {language === "ko"
                    ? "ATANOR 앱의 언어, 로컬 Companion, 안전 모드, 브레인 라우팅 상태를 한 곳에서 관리합니다."
                    : "Manage language, local Companion, safety mode, and brain routing for the user-facing ATANOR app."}
                </p>
              </div>
              <div className="atanor-settings-metrics">
                <span><small>{language === "ko" ? "로컬 Companion" : "Local Companion"}</small><strong>{localBackendConnected ? copy.connected : language === "ko" ? "대기" : "Fallback"}</strong></span>
                <span><small>{language === "ko" ? "하드웨어 티어" : "Hardware Tier"}</small><strong>{edgeTierLabel}</strong></span>
                <span><small>{language === "ko" ? "학습 런타임" : "Learning Runtime"}</small><strong>{daemonRuntimeText}</strong></span>
                <span><small>{language === "ko" ? "라우팅" : "Routing"}</small><strong>{localAssistRatio}% / {cloudAssistRatio}%</strong></span>
              </div>
            </article>

            <article className="atanor-settings-panel">
              <header>
                <h2>{language === "ko" ? "언어와 표시" : "Language and Display"}</h2>
                <p>{language === "ko" ? "기본 UI 언어를 전환합니다. URL에 lang 파라미터가 있으면 그 값을 우선합니다." : "Switch the UI language. A lang URL parameter takes priority when present."}</p>
              </header>
              <div className="atanor-settings-segment" aria-label="Language">
                <button data-active={language === "en"} onClick={() => setMainLanguage("en")}>English</button>
                <button data-active={language === "ko"} onClick={() => setMainLanguage("ko")}>한국어</button>
              </div>
              <label className="atanor-settings-toggle">
                <span>{language === "ko" ? "웹 검색 보조" : "Web search assist"}</span>
                <input type="checkbox" checked={webSearchEnabled} onChange={(event) => setWebSearchEnabled(event.target.checked)} />
              </label>
            </article>

            <article className="atanor-settings-panel">
              <header>
                <h2>{language === "ko" ? "로컬 Companion" : "Local Companion"}</h2>
                <p>{language === "ko" ? "FastAPI Companion 주소를 지정하고 로컬 그래프와 동기화합니다." : "Point the app to the FastAPI Companion and sync the local graph."}</p>
              </header>
              <label className="atanor-settings-field">
                <span>{language === "ko" ? "API 주소" : "API URL"}</span>
                <input
                  value={localBackendUrl}
                  onChange={(event) => setLocalBackendUrl(event.currentTarget.value)}
                  spellCheck={false}
                />
              </label>
              <div className="atanor-settings-actions">
                <button onClick={() => runAction(() => connectLocalBackend(localBackendUrl))}>{language === "ko" ? "재연결" : "Reconnect"}</button>
                <button onClick={() => {
                  const defaultUrl = "http://127.0.0.1:8502";
                  setLocalBackendUrl(defaultUrl);
                  void runAction(() => connectLocalBackend(defaultUrl));
                }}>{language === "ko" ? "기본값" : "Default"}</button>
                <button onClick={disconnectLocalBackend}>{language === "ko" ? "해제" : "Disconnect"}</button>
              </div>
              <small>{localBackendDisplay}</small>
            </article>

            <article className="atanor-settings-panel">
              <header>
                <h2>{language === "ko" ? "브레인 링크 안전장치" : "Brain Link Safety"}</h2>
                <p>{language === "ko" ? "공용 fragment 작업은 허용하되 개인 Payload Vault와 로컬 데이터는 기본적으로 보호합니다." : "Allow public fragment jobs while keeping private Payload Vault and local data protected by default."}</p>
              </header>
              <label className="atanor-settings-toggle">
                <span>{language === "ko" ? "안전 모드" : "Safe mode"}</span>
                <input type="checkbox" checked={contributionSafeMode} onChange={(event) => setContributionSafeMode(event.target.checked)} />
              </label>
              <label className="atanor-settings-toggle">
                <span>{language === "ko" ? "공용 fragment 작업 허용" : "Allow public fragment jobs"}</span>
                <input type="checkbox" checked={contributionAllowPublic} onChange={(event) => setContributionAllowPublic(event.target.checked)} />
              </label>
              <label className="atanor-settings-toggle">
                <span>{language === "ko" ? "로컬 데이터 공유 금지" : "Local data sharing blocked"}</span>
                <input type="checkbox" checked readOnly disabled />
              </label>
              <label className="atanor-settings-slider">
                <span>CPU {language === "ko" ? "한도" : "limit"} {contributionCpuLimit}%</span>
                <input type="range" min={5} max={80} value={contributionCpuLimit} onChange={(event) => setContributionCpuLimit(Number(event.target.value))} />
              </label>
            </article>

            <article className="atanor-settings-panel atanor-settings-wide">
              <header>
                <h2>{language === "ko" ? "진단과 유지관리" : "Diagnostics and Maintenance"}</h2>
                <p>{language === "ko" ? "현재 세션의 그래프, 학습 데몬, Payload Vault 체크포인트를 수동으로 정리합니다." : "Manually refresh graph state, learning daemon state, and Payload Vault checkpoints."}</p>
              </header>
              <div className="atanor-settings-actions">
                <button onClick={() => runAction(refreshAll)}>{copy.sync}</button>
                <button onClick={() => runAction(startLearningDaemon)}>{copy.actions.learningTrigger}</button>
                <button onClick={() => runAction(checkpointLearningDaemon)}>{copy.actions.checkpoint}</button>
              </div>
              <div className="atanor-settings-status-list">
                <p><span>{language === "ko" ? "브레인 작업" : "Brain task"}</span><strong>{activeTaskLabel}</strong></p>
                <p><span>{language === "ko" ? "데몬 상태" : "Daemon"}</span><strong>{daemonStateText}</strong></p>
                <p><span>{language === "ko" ? "엣지 브로커" : "Edge broker"}</span><strong>{edgeBrokerLabel}</strong></p>
                <p><span>{language === "ko" ? "메모리" : "Memory"}</span><strong>{displayMemoryNodeCount.toLocaleString()} / {displayMemoryEdgeCount.toLocaleString()}</strong></p>
              </div>
            </article>
          </section>
        ) : mainSection === "contribute" ? (
          <section className="atanor-contribution-grid">
            <header className="atanor-brain-link-header">
              <div>
                <h2>Brain Link</h2>
                <p>{language === "ko" ? "설치된 그래프와 공용 Fragment 작업을 현재 브레인 흐름에 안전하게 연결합니다." : "Safely link installed graphs and public fragment work into the current brain flow."}</p>
              </div>
              <div className="atanor-brain-link-status">
                <span><small>{language === "ko" ? "활성 링크" : "Active links"}</small><strong>{graphHubAttachments.length + (contributionIsActive ? 1 : 0)}</strong></span>
                <span><small>{language === "ko" ? "부착 노드" : "Attached nodes"}</small><strong>{graphHubAttachments.reduce((total, item) => total + Number(item.working_memory_nodes ?? 0), 0)}</strong></span>
                <span><small>{language === "ko" ? "읽기 전용" : "Read-only"}</small><strong>ON</strong></span>
                <span><small>Local write</small><strong>{language === "ko" ? "기록 안 함" : "off"}</strong></span>
              </div>
            </header>
            {brainLinkPool ? (
              <article className="atanor-brain-pool">
                <div className="atanor-brain-pool-head">
                  <h3>{language === "ko" ? "함께 계산하는 기기들" : "Devices computing together"}</h3>
                  <span>{language === "ko" ? "실제 P2P 풀 — 연결 상태는 절대 꾸며내지 않습니다" : "Real P2P pool — connection state is never faked"}</span>
                </div>
                <div className="atanor-brain-pool-stats">
                  <span><small>{language === "ko" ? "연결된 기기" : "Devices"}</small><strong><em>{String(brainLinkPool.online_peers ?? 0)}</em>/{String(brainLinkPool.peer_count ?? 0)}</strong></span>
                  <span><small>{language === "ko" ? "남은 작업" : "Work left"}</small><strong>{Number(brainLinkPool.queue_remaining ?? 0).toLocaleString()}</strong></span>
                  <span><small>{language === "ko" ? "처리한 작업" : "Done"}</small><strong>{String(brainLinkPool.batches_completed ?? 0)}</strong></span>
                  <span><small>{language === "ko" ? "함께 쌓은 지식" : "Knowledge built"}</small><strong>{(Number(brainLinkPool.store_concepts_total ?? 0) + Number(brainLinkPool.store_relations_total ?? 0)).toLocaleString()}</strong></span>
                  {brainLinkPool.economy ? (<>
                    <span><small>{language === "ko" ? "소각/발행 (BME)" : "Burned/Minted (BME)"}</small><strong>{Number(brainLinkPool.economy?.equilibrium?.burned ?? 0).toLocaleString()} / {Number(brainLinkPool.economy?.equilibrium?.minted ?? 0).toLocaleString()}</strong></span>
                    <span><small>{language === "ko" ? "균형" : "Equilibrium"}</small><strong>{Number(brainLinkPool.economy?.equilibrium?.equilibrium ?? 0).toLocaleString()}</strong></span>
                  </>) : null}
                </div>
                <ul>
                  {(Array.isArray(brainLinkPool.peers) ? brainLinkPool.peers : []).map((peer: AnyRecord) => (
                    <li key={String(peer.peer_id)}>
                      <span className="atanor-brain-pool-dot" data-online={peer.online ? "true" : "false"} />
                      <strong>{String(peer.label ?? peer.peer_id)}</strong>
                      <span className="atanor-brain-pool-meta">
                        {peer.online ? (language === "ko" ? "지금 참여 중" : "online") : (language === "ko" ? "쉬는 중" : "offline")}
                        {" · "}{language === "ko" ? "작업" : "done"} {String(peer.completed ?? 0)}
                        {" · "}{language === "ko" ? "지식 기여" : "contributed"} {(Number(peer.concepts ?? 0) + Number(peer.relations ?? 0)).toLocaleString()}
                        {brainLinkPool.economy?.peers?.[String(peer.peer_id)] ? (
                          <>{" · "}
                            <span className="atanor-brain-pool-tier">
                              {{ trusted: language === "ko" ? "신뢰" : "trusted", priority: language === "ko" ? "우선" : "priority", economy: language === "ko" ? "일반" : "economy" }[String(brainLinkPool.economy.peers[String(peer.peer_id)].tier)] ?? "일반"}
                            </span>
                            {" · "}{language === "ko" ? "크레딧" : "credits"} {Number(brainLinkPool.economy.peers[String(peer.peer_id)].credits ?? 0).toLocaleString()}
                            {" · "}{language === "ko" ? "평판" : "rep"} {Number(brainLinkPool.economy.peers[String(peer.peer_id)].reputation ?? 0).toFixed(2)}
                          </>
                        ) : null}
                      </span>
                    </li>
                  ))}
                  {(!Array.isArray(brainLinkPool.peers) || brainLinkPool.peers.length === 0) ? (
                    <li className="atanor-brain-pool-empty">{language === "ko" ? "아직 함께 계산하는 다른 기기가 없어요. 다른 PC에서 ATANOR를 켜면 자동으로 연결됩니다." : "No other devices yet — open ATANOR on another PC and it joins automatically."}</li>
                  ) : null}
                </ul>
              </article>
            ) : null}
            <article className="atanor-contribution-hero">
              <div className="atanor-contribution-ring" data-active={contributionIsActive}>
                <svg viewBox="0 0 120 120" aria-hidden="true">
                  <circle cx="60" cy="60" r="48" />
                  <circle cx="60" cy="60" r="48" style={{ strokeDasharray: `${contributionIsActive ? 286 : 72} 302` }} />
                </svg>
                <strong>{contributionStatusText}</strong>
                <span>{contributionIsActive ? (language === "ko" ? "활성" : "Active") : contributionPaused ? (language === "ko" ? "정지" : "Paused") : (language === "ko" ? "안정" : "Stable")}</span>
              </div>
              <div className="atanor-contribution-copy">
                <span>{language === "ko" ? "보호된 링크" : "Protected Link"}</span>
                <h2>{language === "ko" ? "공용 검증 채널이 안정적으로 대기 중입니다." : "Public verification channel is standing by."}</h2>
                <p>{language === "ko" ? "개인 데이터는 장치 안에 남기고, 공개 후보 조각의 신뢰 신호만 확인합니다." : "Private data stays on device; only public candidate trust signals are checked."}</p>
                <div className="atanor-contribution-badges">
                  <span>{language === "ko" ? "개인 금고 보존" : "Private vault sealed"}</span>
                  <span>{language === "ko" ? "공개 범위" : "Public scope"}</span>
                  <span>{language === "ko" ? `크레딧 x${contributionCreditMultiplier}` : `Credit x${contributionCreditMultiplier}`}</span>
                </div>
                <div className="atanor-contribution-actions">
                  <button onClick={() => runAction(enableContribution)}>
                    {contributionEnabled && !contributionPaused ? (language === "ko" ? "브레인 링크 갱신" : "Refresh Brain Link") : (language === "ko" ? "브레인 링크 연결" : "Connect Brain Link")}
                  </button>
                  <button onClick={contributionBlockedBySafety ? () => runAction(refreshAll) : contributionIsActive ? pauseContribution : resumeContribution}>
                    {contributionIsActive
                      ? (language === "ko" ? "일시정지" : "Pause")
                      : contributionBlockedBySafety
                        ? (language === "ko" ? "상태 재확인" : "Recheck")
                        : (language === "ko" ? "재개" : "Resume")}
                  </button>
                </div>
                {resourceStopReason ? (
                  <small className="atanor-contribution-hold">
                    {resourceStopReason} {language === "ko" ? "여유가 생기면 자동으로 다시 시작돼요." : "Sharing resumes automatically."}
                  </small>
                ) : resourceSlowNotice ? (
                  <small className="atanor-contribution-hold" style={{ color: "#8a93a8" }}>{resourceSlowNotice}</small>
                ) : null}
              </div>
              <div className="atanor-contribution-credit-summary">
                <span>{language === "ko" ? "브레인 링크 크레딧" : "Brain Link Credits"}</span>
                <strong>{contributionTotalCredit.toFixed(1)}</strong>
                <small>{language === "ko" ? `오늘 +${contributionTodayCredit.toFixed(1)} · 작업당 ${contributionEstimatedTaskCredit.toFixed(1)}` : `Today +${contributionTodayCredit.toFixed(1)} · ${contributionEstimatedTaskCredit.toFixed(1)} per task`}</small>
                <em>x{contributionCreditMultiplier}</em>
              </div>
              <div className="atanor-contribution-metrics">
                <span><small>CPU</small><strong>{contributionCpuUsage}%</strong></span>
                <span><small>GPU</small><strong>{contributionGpuAvailable ? `${contributionGpuUsage}%` : (language === "ko" ? "미감지" : "n/a")}</strong></span>
                <span><small>RAM</small><strong>{contributionRamGb.toFixed(1)}GB</strong></span>
                <span><small>{language === "ko" ? "네트워크" : "Network"}</small><strong>{contributionNetworkLabel}</strong></span>
              </div>
            </article>

            <aside className="atanor-contribution-side">
              <section>
                <h2>{language === "ko" ? "링크 라우팅" : "Link Routing"}</h2>
                <div className="atanor-routing-donut" style={{ ["--local-share" as string]: `${contributionSharedRatio}%` }}>
                  <strong>{contributionSharedRatio}%</strong>
                  <span>{language === "ko" ? "공용 작업" : "Public jobs"}</span>
                </div>
                <p><span>{language === "ko" ? "로컬 데이터 공유" : "Local data share"}</span><strong>{contributionLocalShareRatio}%</strong></p>
                <p><span>{language === "ko" ? "브로커" : "Broker"}</span><strong>{contributionBrokerState.replace(/_/g, " ")}</strong></p>
                <p><span>{language === "ko" ? "상태" : "State"}</span><strong>{contributionSafeSummary}</strong></p>
              </section>
              <section>
                <h2>{language === "ko" ? "현재 공용 작업" : "Current Public Task"}</h2>
                <div className="atanor-task-orb" />
                <strong>{String(contributionCurrentTask?.task_type ?? "public_fragment_validation").replace(/_/g, " ")}</strong>
                <p>{language === "ko" ? "공개 후보 조각의 중복과 신뢰 신호만 확인합니다." : "Checks only duplicate and trust signals for public candidates."}</p>
                <small>{contributionCurrentTask?.task_id ?? "local-broker"} · {contributionBackendState}</small>
              </section>
            </aside>

            <article className="atanor-contribution-card">
              <header className="atanor-credit-trend-header">
                <div>
                  <h2>{language === "ko" ? "크레딧 플로우" : "Credit Flow"}</h2>
                  <p>{language === "ko" ? "공용 Fragment 작업 보상 추세" : "Public fragment reward trend"}</p>
                </div>
                <strong>{contributionIsActive ? contributionCreditLatest.toFixed(1) : "—"}</strong>
              </header>
              <div className="atanor-credit-chart" data-active={contributionIsActive} data-seismo="true" data-standby={!contributionIsActive}>
                {contributionIsActive ? (
                  <>
                    <SeismographChart value={contributionCreditLatest} color="#ff7a1a" active={contributionIsActive} tickMs={600} />
                    <div className="atanor-credit-chart-axis">
                      <span>{language === "ko" ? "대기" : "Standby"}</span>
                      <span>{language === "ko" ? "실시간" : "Live"}</span>
                    </div>
                  </>
                ) : (
                  <div className="atanor-credit-standby">
                    <span className="atanor-credit-standby-line" aria-hidden="true" />
                    <div>
                      <strong>{language === "ko" ? "연결 대기" : "Standby"}</strong>
                      <p>{language === "ko" ? "Brain Link를 연결하면 크레딧 플로우가 실시간으로 그려집니다." : "Connect Brain Link to draw the live credit flow."}</p>
                    </div>
                  </div>
                )}
              </div>
              <small className="atanor-credit-trend-meta">
                {language === "ko"
                  ? `${edgeTierLabel} · 완료 ${contributionCompletedTasks} · 대기 ${contributionWaitingCredit.toFixed(1)} credit`
                  : `${edgeTierLabel} · ${contributionCompletedTasks} tasks · ${contributionWaitingCredit.toFixed(1)} credit pending`}
              </small>
            </article>

            <article className="atanor-contribution-card">
              <h2>{language === "ko" ? "안전 및 개인정보" : "Safety and Privacy"}</h2>
              <div className="atanor-safety-list">
                <label><span>{language === "ko" ? "개인 데이터 공유 안 함" : "Do not share private data"}</span><input type="checkbox" checked readOnly /></label>
                <label><span>{language === "ko" ? "로컬 브레인 데이터 공유 금지" : "Local Brain sharing blocked"}</span><input type="checkbox" checked readOnly disabled /></label>
                <label><span>{language === "ko" ? "공용 fragment 작업 허용" : "Allow public fragment jobs"}</span><input type="checkbox" checked={contributionAllowPublic} onChange={(event) => setContributionAllowPublic(event.target.checked)} /></label>
                <label><span>{language === "ko" ? "안전 모드" : "Safe mode"}</span><input type="checkbox" checked={contributionSafeMode} onChange={(event) => setContributionSafeMode(event.target.checked)} /></label>
              </div>
            </article>

            <article className="atanor-contribution-wide">
              <details>
                <summary>{language === "ko" ? "자원 설정" : "Resource settings"}</summary>
                <div className="atanor-resource-slider">
                  <span>CPU {language === "ko" ? "한도" : "limit"} {contributionCpuLimit}%</span>
                  <input type="range" min={5} max={80} value={contributionCpuLimit} onChange={(event) => setContributionCpuLimit(Number(event.target.value))} />
                </div>
                <div className="atanor-resource-slider">
                  <span>GPU {language === "ko" ? "한도" : "limit"} {contributionGpuLimitEffective}% · {language === "ko" ? `크레딧 x${contributionCreditMultiplier}` : `credit x${contributionCreditMultiplier}`}</span>
                  <input type="range" min={0} max={95} value={contributionGpuLimit} disabled={!contributionGpuAvailable} onChange={(event) => setContributionGpuLimit(Number(event.target.value))} />
                  {!contributionGpuAvailable ? <small>{language === "ko" ? "GPU 텔레메트리가 연결되면 활성화됩니다." : "Enabled when GPU telemetry is available."}</small> : null}
                </div>
              </details>
              <details>
                <summary>{language === "ko" ? "브레인 링크 작업" : "Brain Link tasks"}</summary>
                <p>Public Fragment verification · Ghost hash dedupe · Source noise check · Public alias review</p>
              </details>
              <details>
                <summary>{language === "ko" ? "실시간 작동 로그" : "Live operation log"}</summary>
                <p>{edgeStatus?.ghost_shell?.logs?.slice?.(-2)?.join(" / ") ?? edgeBrokerLabel}</p>
              </details>
              <details>
                <summary>{language === "ko" ? "크레딧 정책" : "Credit policy"}</summary>
                <p>{language === "ko" ? "현재 제품은 내부 크레딧만 기록합니다. 암호화폐, 전송 가능한 토큰, 금융형 보상은 구현하지 않았습니다." : "This product build records internal credits only. Cryptocurrency, transferable tokens, and financial rewards are not implemented."}</p>
              </details>
            </article>
          </section>
        ) : mainSection === "home" ? null : (
        <>
        <section className="atanor-user-grid">
          {showInlineChatPanel ? (
            <article className={`atanor-user-chat-card atanor-user-ontology-chat-card ${isLocalChatSection ? "atanor-user-local-chat-card" : ""}`}>
              <header>
                <div>
                  <h2>{lowerPanelTitle}</h2>
                </div>
                <button data-active={webSearchEnabled} onClick={() => setWebSearchEnabled((enabled) => !enabled)}>
                  {language === "ko" ? `웹 ${webSearchEnabled ? "켜짐" : "꺼짐"}` : `Web ${webSearchEnabled ? "On" : "Off"}`}
                </button>
              </header>
              {isOntologyChatSection ? (
                <div className="atanor-ontology-guide">
                  <h3>{ontologyGuideTitle.split("\n").map((line) => <span key={line}>{line}</span>)}</h3>
                  <p>{ontologyGuideBody}</p>
                </div>
              ) : (
                <div className="atanor-local-chat-scope">
                  <span>{language === "ko" ? "로컬 전용" : "LOCAL ONLY"}</span>
                  <strong>{language === "ko" ? "로컬 브레인과 Payload Vault 안에서만 답변합니다." : "Answers only from Local Brain and Payload Vault."}</strong>
                </div>
              )}
              <div className="atanor-user-chat-scroll" ref={chatScrollRef}>
                {chatMessages.slice(-5).map((message, index) => (
                  <article key={`${message.role}-${index}`} data-role={message.role}>
                    <span>{message.role === "user" ? "User" : "ATANOR"}</span>
                    <p>{message.text}</p>
                    {message.evidence?.length ? (
                      <details className="atanor-trace-details">
                        <summary>{language === "ko" ? "근거 / Brain path" : "Evidence / Brain path"}</summary>
                        <small>{message.evidence.slice(0, 2).map((doc) => doc.chunk_id ?? doc.doc_id ?? "evidence").join(" · ")}</small>
                      </details>
                    ) : null}
                  </article>
                ))}
              </div>
              <div className="atanor-user-prompt-chips">
                {activePromptChips.map((chip) => (
                  <button key={chip} onClick={() => setChatInput(chip)}>{chip}</button>
                ))}
              </div>
              <div className="atanor-user-composer">
                <textarea
                  value={chatInput}
                  onChange={(event) => setChatInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      sendChat();
                    }
                  }}
                  placeholder={copy.placeholder}
                  aria-label={copy.placeholder}
                />
                <VoiceMicButton language={language} disabled={isGeneratingAnswer}
                  onText={(t) => setChatInput((prev) => (prev ? prev + " " : "") + t)} />
                <button disabled={isGeneratingAnswer} onClick={sendChat}>
                  {isGeneratingAnswer ? copy.generating : copy.send}
                </button>
              </div>
            </article>
          ) : null}

          <article className="atanor-user-graph-card" data-presentation={graphPresentationMode}>
            <div className="atanor-user-graph-meta">
              <div>
                <h2>{presentationCopy.graphTitle}</h2>
              </div>
              <div className="atanor-user-stat-stack">
                {graphHeaderStats.map((item) => (
                  <span key={item.label}>{item.label}<strong>{item.value}</strong></span>
                ))}
              </div>
            </div>
            <div className="atanor-user-graph-stage" data-presentation={graphPresentationMode} data-answering={usesStudioGraph && transcriptOpen}>
              {mainSection === "cloud" ? <LiveLearningPanel view={cloudGraphView} onViewChange={setCloudGraphView} /> : null}
              {synapseTrace && mainSection === "cloud" ? (
                <div style={{ position: "absolute", left: 16, bottom: 16, zIndex: 30, display: "flex", alignItems: "center", gap: 8,
                              background: "rgba(10,11,14,.74)", border: "1px solid #26262c", borderRadius: 10, padding: "8px 12px" }}>
                  <span style={{ fontSize: 10, letterSpacing: 1.2, color: "#8a8a92" }}>시냅스 추적</span>
                  <span style={{ fontSize: 12, color: "#e8e8ec" }}>
                    {synapseTrace.labels.map((label, index) => (
                      <span key={`${label}-${index}`} style={{ opacity: index <= synapseStep ? 1 : 0.35, fontWeight: index === synapseStep ? 700 : 400 }}>
                        {index ? " → " : ""}{label}
                      </span>
                    ))}
                  </span>
                  <button
                    type="button"
                    aria-label="end synapse trace"
                    onClick={() => { setSynapseTrace(null); setSynapseFocus(null); }}
                    style={{ background: "transparent", border: "none", color: "#8a8a92", cursor: "pointer", fontSize: 12, padding: 2 }}
                  >
                    ✕
                  </button>
                </div>
              ) : null}
              {isCloudViewerSection && !visibleGraph3D.nodes.length ? (
                <CloudBrainSphereScene
                  edgeOpacity={graphEdgeOpacity}
                  highEnd={Boolean(benchmark?.hardware_tier === "Tier 1-M" || benchmark?.tier === "Tier 1-M")}
                  onStats={setCloudSphereStats}
                />
              ) : visibleGraph3D.nodes.length ? (
                <Rag3DScene
                  key={usesStudioGraph ? "atanor-home-studio-graph" : `atanor-${mainSection}-${graphPresentationMode}-sphere-graph`}
                  activeEdgeKeys={synapseTrace ? synapseTraceEdgeKeys : showActivity ? activeSignalEdgeKeys : EMPTY_STRING_ARRAY}
                  activeNodeIds={synapseTrace ? synapseTraceNodeIds : showActivity ? activeSignalNodeIds : EMPTY_STRING_ARRAY}
                  showActivity={showActivity}
                  graph={cloudShowsSurface ? surfaceSceneGraph3D : cloudSceneGraph3D}
                  control={rag3dControl}
                  focusNode={synapseFocus}
                  preserveSourceCoordinates={usesStudioGraph || usesSphereGraph}
                  theme="dark"
                  visualState={ragVisualState}
                  fitScale={graphFitScale}
                  showLabels={mainSection !== "local"}
                  edgeOpacity={graphEdgeOpacity}
                  synapsesPerSecond={showActivity && mainSection === "cloud" ? synapseRate : 0}
                  onSelect={(node: Rag3DNode) => setSelectedMemory(node)}
                />
              ) : (
                <div className="atanor-user-empty-graph" data-status={localBackendStatus}>
                  <div className="atanor-empty-loader" aria-hidden="true">
                    <span />
                    <span />
                    <span />
                    <i />
                  </div>
                  <strong>{graphEmptyTitle}</strong>
                  <small>{graphEmptySubtitle}</small>
                  {tabBrainGraphPending ? (
                    <div className="atanor-graph-loading-progress" aria-label={`${graphEmptyTitle} ${graphLoadingPercent}%`}>
                      <span style={{ width: `${graphLoadingPercent}%` }} />
                      <em>{graphLoadingPercent}%</em>
                    </div>
                  ) : null}
                </div>
              )}
              {mainSection !== "local" && mainSection !== "cloud" ? (
                <>
                  <div className="atanor-user-graph-label local">{presentationCopy.localLabel}<span>{presentationCopy.localDetail}</span></div>
                  <div className="atanor-user-graph-label cloud">{presentationCopy.cloudLabel}<span>{presentationCopy.cloudDetail}</span></div>
                </>
              ) : null}
              {mainSection !== "local" && mainSection !== "cloud" ? (
                <div className="atanor-user-graph-mini-legend" aria-label="Graph legend">
                  <span><i data-kind="local" />{presentationCopy.localNode}</span>
                  <span><i data-kind="cloud" />{presentationCopy.cloudNode}</span>
                  <span><i data-kind="fragment" />{presentationCopy.fragmentNode}</span>
                  <span><i data-kind="line" />{copy.strongRelation}</span>
                </div>
              ) : null}
              {mainSection !== "local" && mainSection !== "cloud" ? (
                <div className="atanor-user-graph-hint">{copy.graphHint}</div>
              ) : null}
              <div className="atanor-user-graph-tools">
                {mainSection === "local" || mainSection === "cloud" ? (
                  <label className="atanor-edge-opacity-control">
                    <span>{language === "ko" ? "연결선" : "Lines"}</span>
                    <input
                      aria-label={language === "ko" ? "연결선 선명도" : "Line clarity"}
                      max="0.122"
                      min="0.03"
                      step="0.002"
                      type="range"
                      value={graphEdgeOpacity}
                      onChange={(event) => setGraphEdgeOpacity(Number(event.target.value))}
                    />
                    <strong>{Math.round(((graphEdgeOpacity - 0.03) / 0.092) * 100)}%</strong>
                  </label>
                ) : null}
                {mainSection === "local" ? (
                  <button
                    type="button"
                    onClick={attachCloudContext}
                    disabled={cloudAttachmentRunning}
                    aria-label={language === "ko" ? "Cloud Context 부착" : "Attach Cloud Context"}
                  >
                    {cloudAttachmentRunning
                      ? (language === "ko" ? "부착 중" : "Attaching")
                      : (language === "ko" ? "Cloud 부착" : "Attach Cloud")}
                  </button>
                ) : null}
                {(mainSection === "local" || mainSection === "cloud") && selectedMemory?.id ? (
                  <button
                    type="button"
                    onClick={() => refreshBrainGraphPanels("full")}
                    aria-label={language === "ko" ? "선택 chunk 드러내기" : "Reveal selected chunk"}
                  >
                    {language === "ko" ? "Chunk 보기" : "Reveal chunk"}
                  </button>
                ) : null}
                <button
                  type="button"
                  onClick={() => setShowActivity((v) => !v)}
                  data-active={showActivity ? "on" : "off"}
                  aria-pressed={showActivity}
                  title={language === "ko"
                    ? "새 연결·검증 연출 표시 토글 (끄면 시각만 숨김 · 학습/검증은 계속)"
                    : "Toggle new-connection & verification visuals (hides visuals only; learning/verification keep running)"}
                >
                  {language === "ko"
                    ? (showActivity ? "연출 ON" : "연출 OFF")
                    : (showActivity ? "Activity ON" : "Activity OFF")}
                </button>
                <button onClick={() => zoomGraph(-0.18)} aria-label="Zoom out">-</button>
                <button onClick={() => zoomGraph(0.18)} aria-label="Zoom in">+</button>
                <button onClick={resetGraph} aria-label={language === "ko" ? "그래프 초기화" : "Reset graph"}>
                  {language === "ko" ? "초기화" : "Reset"}
                </button>
              </div>
              {tabBrainGraphPending ? (
                <div className="atanor-graph-sync-progress" aria-label={`${graphEmptyTitle} ${graphLoadingPercent}%`}>
                  <span>{language === "ko" ? "그래프 로딩" : "Graph loading"}</span>
                  <div><i style={{ width: `${graphLoadingPercent}%` }} /></div>
                  <em>{graphLoadingPercent}%</em>
                </div>
              ) : null}
              {mainSection === "local" && (cloudAttachedNodeCount > 0 || Number(graphOverlay.seed_anchor_nodes ?? 0) > 0) ? (
                <div className="atanor-local-overlay-badge">
                  <span>{language === "ko" ? "Working Memory Overlay Active" : "Working Memory Overlay Active"}</span>
                  <strong>{`Cloud attached nodes: ${cloudAttachedNodeCount}`}</strong>
                  <small>{`Seed anchors: ${Number(graphOverlay.seed_anchor_nodes ?? 0)}`}</small>
                  <small>{`Local write: ${Boolean(graphOverlay.writes_to_local_brain) ? (language === "ko" ? "기록함" : "on") : (language === "ko" ? "기록 안 함" : "off")}`}</small>
                  <small>{language === "ko" ? "임시 부착 · Local Brain 저장 안 함" : "Temporary attachment · not saved to Local Brain"}</small>
                  {cortexLastCycle.enabled ? (
                    <small>CORTEX-G2 · {language === "ko" ? "활성" : "active"} {String(cortexLastCycle.activated_nodes ?? 0)} · error {Math.round(Number(cortexLastCycle.prediction_error ?? 0) * 100)}%</small>
                  ) : null}
                  <button type="button" onClick={detachCloudContext} disabled={cloudAttachmentRunning || cloudAttachedNodeCount === 0}>
                    Detach
                  </button>
                </div>
              ) : null}
              <small className="atanor-user-graph-state">{ragVisualState === "completed" ? copy.graphSettled : signalTraceText}</small>
            </div>
            <div className="atanor-user-legend">
              <span><i data-kind="local" />{presentationCopy.localNode}</span>
              <span><i data-kind="cloud" />{presentationCopy.cloudNode}</span>
              <span><i data-kind="fragment" />{presentationCopy.fragmentNode}</span>
              <span><i data-kind="line" />{copy.strongRelation}</span>
              <span><i data-kind="line-weak" />{copy.weakRelation}</span>
            </div>
            {mainSection === "local" ? (
              <section className="atanor-brain-layer-panel">
                <header>
                  <div>
                    <span>LOCAL VIEW</span>
                    <h3>{language === "ko" ? "로컬 브레인 레이어" : "Local Brain Layers"}</h3>
                  </div>
                  <button type="button" onClick={() => refreshBrainGraphPanels("full")}>
                    {language === "ko" ? "레이어 갱신" : "Refresh layers"}
                  </button>
                </header>
                <div className="atanor-brain-layer-summary">
                  <span><small>{language === "ko" ? "표시 노드" : "Rendered nodes"}</small><strong>{tabBrainGraphPending ? "..." : activeBrainRenderedNodes.toLocaleString()}</strong></span>
                  <span><small>{language === "ko" ? "표시 관계" : "Rendered edges"}</small><strong>{tabBrainGraphPending ? "..." : activeBrainRenderedEdges.toLocaleString()}</strong></span>
                  <span><small>Overlay</small><strong>{activeBrainOverlay?.working_memory_active ? "active" : "idle"}</strong></span>
                  <span><small>Local write</small><strong>{Boolean(activeBrainOverlay?.local_brain_write) ? (language === "ko" ? "기록함" : "on") : (language === "ko" ? "기록 안 함" : "off")}</strong></span>
                </div>
                <div className="atanor-brain-layer-list">
                  {activeBrainGraphRows.map((row) => (
                    <button
                      key={row.id}
                      type="button"
                      data-enabled={row.enabled}
                      data-missing={Boolean(row.missingReason)}
                      onClick={() => toggleBrainGraphLayer(activeBrainView, row.id)}
                    >
                      <span>{row.label}</span>
                      <strong>{row.enabled ? (tabBrainGraphPending ? "..." : row.count.toLocaleString()) : "off"}</strong>
                      {row.missingReason ? <small>{row.missingReason}</small> : null}
                    </button>
                  ))}
                </div>
                <p>{language === "ko" ? "Cloud attached 노드는 로컬 브레인 카운트에 포함하지 않습니다." : "Cloud-attached nodes are not counted as Local Brain memory."}</p>
              </section>
            ) : null}
          </article>

          {mainSection === "local" ? (
            <BrainConnectionStatus
              activeBrain={mainSection}
              cloud={{
                candidateAvailable: candidateOverlayAvailable,
                candidateCaseFrames: Number(cloudCandidateStatus?.candidate_case_frames ?? 0),
                concepts: semanticStoreConceptCount,
                evidence: semanticCloudEvidence,
                pending: false,
                relations: semanticStoreRelationCount,
                source: cloudProviderName,
              }}
              labMode={labSurfaceVisible}
              language={language}
              local={{
                initialized: localBrainInitialized,
                nodes: localBrainStatusNodeCount,
                pending: mainSection === "local" && tabBrainGraphPending,
                relations: localBrainStatusRelationCount,
              }}
              localBackendMessage={localBackendDisplay}
              localBackendStatus={localBackendStatus}
              localBackendUrl={localBackendUrl}
            />
          ) : null}

          {showRightRail ? (
          <aside className="atanor-user-right-rail" data-variant={isOntologyChatSection ? "ontology" : isCloudViewerSection ? "cloud" : "default"}>
            {isOntologyChatSection ? (
              <>
                <section className="atanor-user-panel atanor-brain-routing-panel">
                  <h2>{language === "ko" ? "브레인 라우팅" : "Brain Routing"}</h2>
                  <div className="atanor-brain-routing-core" style={{ ["--cloud-share" as string]: `${cloudAssistRatio}%` }}>
                    <strong>{localAssistRatio}%</strong>
                    <span>Local</span>
                    <em>{cloudAssistRatio}% Cloud</em>
                  </div>
                  <p><span>{language === "ko" ? "Working Memory" : "Working Memory"}</span><strong>{continuousLearningActive ? "Active" : "Ready"}</strong></p>
                </section>
                <section className="atanor-user-panel atanor-epistemic-panel">
                  <h2>{language === "ko" ? "인식 상태" : "Epistemic State"}</h2>
                  {epistemicRows.map((row) => (
                    <p key={row.label}>
                      <span>{row.label}</span>
                      <strong data-tone={row.tone}>{row.value}</strong>
                    </p>
                  ))}
                </section>
                <section className="atanor-user-panel atanor-selected-memory-panel">
                  <h2>{language === "ko" ? "선택 메모리" : "Selected Memory"}</h2>
                  <div className="atanor-selected-memory-card">
                    <Network className="atanor-selected-memory-icon" size={22} strokeWidth={1.7} />
                    <div>
                      <strong>{selectedMemoryTitle}</strong>
                      <small>{selectedMemory ? memoryTypeText(String(selectedMemory.type ?? "concept")) : (language === "ko" ? "노드를 선택하세요" : "Select a node")}</small>
                    </div>
                  </div>
                  {selectedMemory ? (
                    <>
                      <p>{selectedMemoryDetail}</p>
                      <small>Type <strong>{String(selectedMemory.type ?? "Concept")}</strong></small>
                    </>
                  ) : null}
                </section>
              </>
            ) : isCloudViewerSection ? (
              <>
                <section className="atanor-user-panel atanor-cloud-viewer-panel">
                  <h2>{language === "ko" ? "Cloud Brain" : "Cloud Brain"}</h2>
                  <span className="atanor-user-readonly-badge">{language === "ko" ? "읽기 전용" : "READ ONLY"}</span>
                  <div className="atanor-user-viewer-grid">
                    {cloudSummaryRows.map((row) => (
                      <span key={row.label}>
                        <small>{row.label}</small>
                        <strong>{row.value}</strong>
                      </span>
                    ))}
                  </div>
                </section>
                {/* Cloud Brain rail simplified (owner: Learn-batch/Refresh/Source/Temporary-Attach/
                    Open-Diagnostics는 사용자 친화적이지 않음 — 제거). Operator diagnostics are
                    dead-gated below (kept in code for lab archaeology, never rendered); the live
                    cumulative-learning surface moves to Atlas in a follow-up. */}
                {false ? (
                  <>
                    <button
                      className="atanor-cloud-diagnostics-toggle"
                      type="button"
                      onClick={() => setCloudDiagnosticsOpen((open) => !open)}
                      aria-expanded={cloudDiagnosticsOpen}
                    >
                      {cloudDiagnosticsOpen
                        ? (language === "ko" ? "진단 닫기" : "Close Diagnostics")
                        : (language === "ko" ? "진단 열기" : "Open Diagnostics")}
                    </button>
                    {cloudDiagnosticsOpen ? (
                      <>
                <section className="atanor-user-panel atanor-cloud-viewer-panel">
                  <h2>{language === "ko" ? "그래프 내부 지표" : "Graph Internals"}</h2>
                  <span className="atanor-user-readonly-badge">RAW</span>
                  <div className="atanor-user-viewer-grid">
                    {cloudTruthRows.map((row) => (
                      <span key={row.label}>
                        <small>{row.label}</small>
                        <strong>{row.value}</strong>
                      </span>
                    ))}
                  </div>
                </section>
                <section className="atanor-user-panel atanor-cloud-viewer-panel">
                  <h2>{language === "ko" ? "Fixture 진단" : "Fixture Diagnostic"}</h2>
                  <span className="atanor-user-readonly-badge">{controlledGrowthProof?.controlled_self_growth ? "PASSED" : "OPTIONAL"}</span>
                  <button
                    className="atanor-proof-action"
                    type="button"
                    onClick={runControlledGrowthProof}
                    disabled={controlledGrowthRunning}
                  >
                    {controlledGrowthRunning
                      ? (language === "ko" ? "검증 중" : "Running")
                      : (language === "ko" ? "fixture 검증" : "Run fixture proof")}
                  </button>
                  <div className="atanor-user-viewer-grid">
                    {controlledGrowthRows.map((row) => (
                      <span key={row.label}>
                        <small>{row.label}</small>
                        <strong>{row.value}</strong>
                      </span>
                    ))}
                  </div>
                  <p>
                    {language === "ko"
                      ? "이 카드는 현재 자가증식 상태가 아니라 제한된 fixture 검증입니다. 실제 성장은 위 Semantic Cloud 수치와 Web Seed 상태를 기준으로 봅니다."
                      : "This card is a bounded fixture check, not the live self-growth state. Use Semantic Cloud counts and Web Seed status for current growth."}
                  </p>
                  {controlledGrowthError ? <p>{controlledGrowthError}</p> : null}
                </section>
                {(() => {
                  // PHFE compare-mode diagnostic: the wave-interference fold runs on every
                  // eligible answer as a HIDDEN TRACE (it never changes the answer) and logs
                  // how well its folded core agrees with the evidence the answer actually
                  // used. This panel surfaces that report for the latest answer.
                  let fold: AnyRecord | null = null;
                  for (let i = chatMessages.length - 1; i >= 0; i -= 1) {
                    const candidate = (chatMessages[i] as AnyRecord)?.diagnostics?.compact_trace?.holographic_fold;
                    if (candidate) { fold = candidate as AnyRecord; break; }
                  }
                  const rows: [string, string][] = fold ? [
                    [language === "ko" ? "일치도 (Jaccard)" : "Agreement (Jaccard)", String(fold.agreement_jaccard ?? "—")],
                    [language === "ko" ? "재현율" : "Recall", String(fold.agreement_recall ?? "—")],
                    [language === "ko" ? "겹친 증거" : "Overlap", String(fold.agreement_overlap ?? "—")],
                    [language === "ko" ? "전역 결맞음" : "Global coherence", typeof fold.folded_global_coherence === "number" ? fold.folded_global_coherence.toFixed(3) : "—"],
                    [language === "ko" ? "접힘 시간" : "Fold time", fold.fold_timing_ms != null ? `${fold.fold_timing_ms}ms` : "—"],
                    [language === "ko" ? "답변 변경" : "Answer changed", fold.answer_changed ? "TRUE" : "false"],
                  ] : [];
                  return (
                    <section className="atanor-user-panel atanor-cloud-viewer-panel" aria-label="PHFE compare mode">
                      <h2>{language === "ko" ? "위상 접힘 (PHFE) 진단" : "Phase Fold (PHFE) Diagnostic"}</h2>
                      <span className="atanor-user-readonly-badge">{fold ? "COMPARE MODE" : (language === "ko" ? "대기" : "IDLE")}</span>
                      {fold ? (
                        <div className="atanor-user-viewer-grid">
                          {rows.map((row) => (
                            <span key={row[0]}><small>{row[0]}</small><strong>{row[1]}</strong></span>
                          ))}
                        </div>
                      ) : (
                        <p>{language === "ko"
                          ? "아직 접힘이 실행된 답변이 없어요. 개념이 매칭되는 질문을 하면 파동 코어와 실제 답변 근거의 일치도가 여기 표시됩니다."
                          : "No folded answer yet. Ask a concept-matching question and this shows how well the wave core agreed with the real answer evidence."}</p>
                      )}
                      <p>
                        {language === "ko"
                          ? "숨은 트레이스 전용입니다 — 파동 코어는 답변을 바꾸지 않으며(compare_mode), 배터리 일치도가 지속적으로 높을 때에만 드라이버 승격을 논의합니다."
                          : "Hidden trace only — the wave core never changes the answer (compare_mode); driver promotion is discussed only if battery agreement stays consistently high."}
                      </p>
                    </section>
                  );
                })()}
                <section className="atanor-user-panel atanor-cloud-viewer-panel">
                  <h2>{language === "ko" ? "Renderer Stress Shell" : "Renderer Stress Shell"}</h2>
                  <span className="atanor-user-readonly-badge">{cloudSphereStats?.actualNodeMode ? "ACTUAL NODES" : "SHELL CHUNKS"}</span>
                  <div className="atanor-user-viewer-grid">
                    {cloudSphereRows.map((row) => (
                      <span key={row.label}>
                        <small>{row.label}</small>
                        <strong>{row.value}</strong>
                      </span>
                    ))}
                  </div>
                  <p>
                    {language === "ko"
                      ? "Cloud Brain 노드는 개별 주소를 유지합니다. ATANOR는 가짜 aggregate 노드로 압축하지 않고, 현재 카메라에 필요한 shell chunk와 zoom 영역만 물질화합니다."
                      : "Cloud Brain nodes remain individually addressable. ATANOR does not compress nodes into fake aggregate nodes; it materializes only camera-visible shell chunks and zoom-focused regions."}
                  </p>
                  <p>
                    {language === "ko"
                      ? "이것은 trillion-scale logical node 전체가 동시에 RAM에 로드되거나 렌더링된다는 뜻이 아닙니다."
                      : "This does not mean all trillion-scale logical nodes are loaded or rendered simultaneously."}
                  </p>
                </section>
                <section className="atanor-user-panel atanor-cloud-viewer-panel">
                  <h2>CORTEX-G2</h2>
                  <span className="atanor-user-readonly-badge">{cortexPanelState}</span>
                  <div className="atanor-user-viewer-grid">
                    {cortexRows.map((row) => (
                      <span key={row.label}>
                        <small>{row.label}</small>
                        <strong>{row.value}</strong>
                      </span>
                    ))}
                  </div>
                  <p>
                    {language === "ko"
                      ? "Seed, Cloud attached, Working Memory 노드를 작은 작업공간으로 활성화하고 예측 오차를 기록합니다. 의식이나 무제한 자기학습을 주장하지 않습니다."
                      : "Activates Seed, Cloud-attached, and Working Memory nodes into a bounded workspace and records prediction error. It does not claim consciousness or unrestricted self-learning."}
                  </p>
                </section>
                <section className="atanor-user-panel atanor-cloud-viewer-panel">
                  <h2>Q-Cortex</h2>
                  <span className="atanor-user-readonly-badge">{qCortexPanelState}</span>
                  <div className="atanor-user-viewer-grid">
                    {qCortexRows.map((row) => (
                      <span key={row.label}>
                        <small>{row.label}</small>
                        <strong>{row.value}</strong>
                      </span>
                    ))}
                  </div>
                  <p>
                    {language === "ko"
                      ? "QUBO/Ising 형식으로 salience, evidence, creative path, planning 선택을 고전적으로 최적화합니다. 실제 양자 하드웨어나 양자 가속을 주장하지 않습니다."
                      : "Optimizes salience, evidence, creative paths, and planning as classical QUBO/Ising-style routing. It does not claim real quantum hardware or quantum speedup."}
                  </p>
                </section>
                {workspaceMode === "lab" ? (
                  <section className="atanor-user-panel atanor-cloud-viewer-panel">
                    <h2>Base Brain Lab</h2>
                    <span className="atanor-user-readonly-badge">{baseBrainPanelState}</span>
                    <div className="atanor-user-viewer-grid">
                      {baseBrainRows.map((row) => (
                        <span key={row.label}>
                          <small>{row.label}</small>
                          <strong>{row.value}</strong>
                        </span>
                      ))}
                    </div>
                    <input
                      className="atanor-base-brain-input"
                      value={baseBrainQuery}
                      onChange={(event) => setBaseBrainQuery(event.target.value)}
                      aria-label="Ask Base Brain without user data"
                    />
                    <button
                      className="atanor-proof-action"
                      type="button"
                      onClick={() => buildBaseBrainPack()}
                      disabled={baseBrainRunning}
                    >
                      {language === "ko" ? "Base Pack 빌드" : "Build Base Pack"}
                    </button>
                    <button
                      className="atanor-proof-action"
                      type="button"
                      onClick={() => askBaseBrain()}
                      disabled={baseBrainRunning || !baseBrainQuery.trim()}
                    >
                      {language === "ko" ? "사용자 데이터 없이 질문" : "Ask without user data"}
                    </button>
                    <button
                      className="atanor-proof-action"
                      type="button"
                      onClick={() => runBaseBrainBenchmark(10)}
                      disabled={baseBrainRunning}
                    >
                      {language === "ko" ? "Zero-user 벤치마크" : "Zero-user benchmark"}
                    </button>
                    {baseBrainBenchmark ? (
                      <div className="atanor-user-viewer-grid">
                        {baseBrainBenchmarkRows.map((row) => (
                          <span key={row.label}>
                            <small>{row.label}</small>
                            <strong>{row.value}</strong>
                          </span>
                        ))}
                      </div>
                    ) : null}
                    {baseBrainAnswer?.answer ? (
                      <div className="atanor-mini-log">
                        <strong>{language === "ko" ? "응답" : "Answer"}</strong>
                        <span>{String(baseBrainAnswer.answer)}</span>
                        <small>
                          {`semantic ${String(baseBrainAnswer.semantic_context_count ?? 0)} / surface ${String(baseBrainAnswer.surface_candidate_count ?? 0)} / LLM ${String(Boolean(baseBrainAnswer.external_llm_used))}`}
                        </small>
                      </div>
                    ) : null}
                    <p>
                      {language === "ko"
                        ? "사용자 문서, 외부 LLM, 외부 sLLM, 웹 호출 없이 Seed/Semantic/Surface Pack만으로 제한된 일반 질문을 검증합니다."
                        : "Verifies limited general answers using only Seed, Semantic, and Surface packs: no user documents, external LLM, external sLLM, or web calls."}
                    </p>
                    {baseBrainError ? <p>{baseBrainError}</p> : null}
                  </section>
                ) : null}
                {workspaceMode === "lab" ? (
                  <section className="atanor-user-panel atanor-cloud-viewer-panel">
                    <h2>Answer Quality Lab</h2>
                    <span className="atanor-user-readonly-badge">{answerQualityPanelState}</span>
                    <button
                      className="atanor-proof-action"
                      type="button"
                      onClick={() => runAnswerQualityLab(8)}
                      disabled={answerQualityRunning || answerRepairRunning}
                    >
                      {answerQualityRunning
                        ? (language === "ko" ? "소형 벤치마크 실행 중" : "Running mini benchmark")
                        : (language === "ko" ? "소형 벤치마크 실행" : "Run mini benchmark")}
                    </button>
                    <button
                      className="atanor-proof-action"
                      type="button"
                      onClick={() => runAnswerRepairComparison(8)}
                      disabled={answerQualityRunning || answerRepairRunning}
                    >
                      {answerRepairRunning
                        ? (language === "ko" ? "수리 비교 실행 중" : "Running repair comparison")
                        : (language === "ko" ? "수리 비교 실행" : "Run Repair Comparison")}
                    </button>
                    <div className="atanor-user-viewer-grid">
                      {answerQualityRows.map((row) => (
                        <span key={row.label}>
                          <small>{row.label}</small>
                          <strong>{row.value}</strong>
                        </span>
                      ))}
                    </div>
                    {answerQualityWorstCases.length ? (
                      <div className="atanor-user-viewer-grid">
                        {answerQualityWorstCases.slice(0, 4).map((item, index) => (
                          <span key={`${item.prompt_id ?? index}-${item.generator ?? "case"}`}>
                            <small>{String(item.generator ?? "case")}</small>
                            <strong>{answerQualityPct(item.overall)}</strong>
                          </span>
                        ))}
                      </div>
                    ) : null}
                    {answerRepairComparison ? (
                      <div className="atanor-user-viewer-grid">
                        {answerRepairRows.map((row) => (
                          <span key={row.label}>
                            <small>{row.label}</small>
                            <strong>{row.value}</strong>
                          </span>
                        ))}
                      </div>
                    ) : null}
                    <p>
                      {language === "ko"
                        ? "로컬 휴리스틱으로 자연도와 trace 숨김을 측정하고, 수리 후보는 검토 가능한 파일로만 남깁니다. 외부 LLM judge와 자동 승격은 없습니다."
                        : "Measures naturalness and trace hygiene locally. Repair candidates stay reviewable; no external LLM judge and no auto-promotion."}
                    </p>
                    {answerQualityError ? <p>{answerQualityError}</p> : null}
                    {answerRepairError ? <p>{answerRepairError}</p> : null}
                  </section>
                ) : null}
                {workspaceMode === "lab" ? (
                  <section className="atanor-user-panel atanor-cloud-viewer-panel">
                    <h2>Surface Repair Review Queue</h2>
                    <span className="atanor-user-readonly-badge">
                      {repairReviewRunning
                        ? (language === "ko" ? "검토 처리 중" : "REVIEWING")
                        : (language === "ko" ? "수동 승인 필요" : "MANUAL REVIEW")}
                    </span>
                    <button
                      className="atanor-proof-action"
                      type="button"
                      onClick={() => generateRepairCandidatesFromFeedback()}
                      disabled={repairReviewRunning || !answerQualityFeedback.length}
                    >
                      {language === "ko" ? "피드백 후보 생성" : "Generate candidates"}
                    </button>
                    <button
                      className="atanor-proof-action"
                      type="button"
                      onClick={() => refreshRepairReviewQueue()}
                      disabled={repairReviewRunning}
                    >
                      {language === "ko" ? "큐 새로고침" : "Refresh queue"}
                    </button>
                    <div className="atanor-user-viewer-grid">
                      {reviewQueueRows.map((row) => (
                        <span key={row.label}>
                          <small>{row.label}</small>
                          <strong>{row.value}</strong>
                        </span>
                      ))}
                    </div>
                    {pendingRepairCandidates.slice(0, 3).map((candidate) => {
                      const proposedRule = (candidate.proposed_rule && typeof candidate.proposed_rule === "object" && !Array.isArray(candidate.proposed_rule))
                        ? candidate.proposed_rule as AnyRecord
                        : {};
                      return (
                        <div className="atanor-mini-log" key={String(candidate.candidate_id)}>
                          <strong>{String(proposedRule.name ?? candidate.candidate_id)}</strong>
                          <small>{String(candidate.severity ?? "medium")} · {String(candidate.source_run_id ?? "manual")}</small>
                          <span>{String(candidate.reason ?? proposedRule.description ?? "")}</span>
                          <button
                            className="atanor-proof-action"
                            type="button"
                            onClick={() => reviewCandidateAction(String(candidate.candidate_id), "approve")}
                            disabled={repairReviewRunning}
                          >
                            {language === "ko" ? "승인" : "Approve"}
                          </button>
                          <button
                            className="atanor-proof-action"
                            type="button"
                            onClick={() => reviewCandidateAction(String(candidate.candidate_id), "reject")}
                            disabled={repairReviewRunning}
                          >
                            {language === "ko" ? "거절" : "Reject"}
                          </button>
                        </div>
                      );
                    })}
                    {productionRepairRules.slice(0, 3).map((rule) => (
                      <div className="atanor-mini-log" key={String(rule.rule_id)}>
                        <strong>{String(rule.name ?? rule.rule_id)}</strong>
                        <small>{rule.enabled ? "enabled" : "disabled"} · usage {String(rule.usage_count ?? 0)}</small>
                        <button
                          className="atanor-proof-action"
                          type="button"
                          onClick={() => rollbackProductionRepairRule(String(rule.rule_id))}
                          disabled={repairReviewRunning || !rule.enabled}
                        >
                          {language === "ko" ? "롤백" : "Rollback"}
                        </button>
                      </div>
                    ))}
                    {repairAuditEvents.slice(0, 3).map((event) => (
                      <p key={String(event.event_id)}>
                        <span>{String(event.event_type)}</span>
                        <strong>{String(event.rule_id ?? event.candidate_id ?? "")}</strong>
                      </p>
                    ))}
                    <p>
                      {language === "ko"
                        ? "후보는 자동으로 운영 규칙이 되지 않습니다. 승인, 거절, 롤백, 사용 기록은 로컬 감사 로그에 남습니다."
                        : "Candidates never become production rules automatically. Approval, rejection, rollback, and usage are written to the local audit log."}
                    </p>
                    {repairReviewError ? <p>{repairReviewError}</p> : null}
                  </section>
                ) : null}
                <section className="atanor-user-panel atanor-user-task">
                  <h2>{copy.activeTask}</h2>
                  <strong>{activeTaskLabel}</strong>
                  <span>{activeTaskRouteText}</span>
                  <div><i style={{ width: `${Math.min(100, activeTaskProgress)}%` }} /></div>
                  <small>{daemonRuntimeText}</small>
                </section>
                <section className="atanor-user-panel">
                  <h2>{copy.systemStatus}</h2>
                  {displayStatusRows.map((row) => (
                    <p key={row.label}>
                      <span><i data-tone={row.tone} />{row.label}</span>
                      <strong>{row.value}</strong>
                    </p>
                  ))}
                </section>
                      </>
                    ) : null}
                  </>
                ) : null}
              </>
            ) : (
              <>
                <section className="atanor-user-panel atanor-cloud-attachment-panel">
                  <h2>{language === "ko" ? "Working Memory Overlay" : "Working Memory Overlay"}</h2>
                  <span className="atanor-user-readonly-badge">{cloudAttachedNodeCount > 0 ? "CLOUD ATTACHED" : "DETACHED"}</span>
                  <div className="atanor-user-viewer-grid">
                    <span>
                      <small>{language === "ko" ? "Cloud nodes" : "Cloud nodes"}</small>
                      <strong>{cloudAttachedNodeCount}</strong>
                    </span>
                    <span>
                      <small>{language === "ko" ? "Cloud edges" : "Cloud edges"}</small>
                      <strong>{cloudAttachedEdgeCount}</strong>
                    </span>
                    <span>
                      <small>{language === "ko" ? "Bundles" : "Bundles"}</small>
                      <strong>{overlayBundleIds.length}</strong>
                    </span>
                    <span>
                      <small>{language === "ko" ? "Local write" : "Local write"}</small>
                      <strong>false</strong>
                    </span>
                  </div>
                  <div className="atanor-proof-actions-row">
                    <button className="atanor-proof-action" type="button" onClick={attachCloudContext} disabled={cloudAttachmentRunning}>
                      {cloudAttachmentRunning ? (language === "ko" ? "연결 중" : "Attaching") : (language === "ko" ? "Cloud Context 붙이기" : "Attach Cloud Context")}
                    </button>
                    <button className="atanor-proof-action" type="button" onClick={detachCloudContext} disabled={cloudAttachmentRunning || cloudAttachedNodeCount === 0}>
                      {language === "ko" ? "Detach" : "Detach"}
                    </button>
                    <button className="atanor-proof-action" type="button" onClick={clearCloudOverlay} disabled={cloudAttachmentRunning || cloudAttachedNodeCount === 0}>
                      {language === "ko" ? "Clear" : "Clear"}
                    </button>
                  </div>
                  <p>
                    {language === "ko"
                      ? "Cloud attached 노드는 임시 Working Memory overlay입니다. Local Brain에 저장되지 않습니다."
                      : "Cloud attached nodes are temporary Working Memory overlays. They are not saved into Local Brain."}
                  </p>
                  {cloudAttachmentError ? <p>{cloudAttachmentError}</p> : null}
                </section>
                <section className="atanor-user-panel">
                  <h2>{copy.systemStatus}</h2>
                  {displayStatusRows.map((row) => (
                    <p key={row.label}>
                      <span><i data-tone={row.tone} />{row.label}</span>
                      <strong>{row.value}</strong>
                    </p>
                  ))}
                </section>
                <section className="atanor-user-panel atanor-user-task">
                  <h2>{copy.activeTask}</h2>
                  <strong>{activeTaskLabel}</strong>
                  <span>{activeTaskRouteText}</span>
                  <div><i style={{ width: `${Math.min(100, activeTaskProgress)}%` }} /></div>
                  <small>{daemonRuntimeText}</small>
                </section>
                <section className="atanor-user-panel atanor-user-actions">
                  <h2>{copy.quickActions}</h2>
                  {quickActions.map((action) => (
                    <button key={action.label} onClick={action.action}>{action.label}<span aria-hidden="true">{">"}</span></button>
                  ))}
                </section>
              </>
            )}
          </aside>
          ) : null}
        </section>

        {showLowerSection ? (
        <section className="atanor-user-lower">
          <article className="atanor-user-chat-card">
            <header>
              <div>
                <h2>{lowerPanelTitle}</h2>
                <p>{lowerPanelSubtitle}</p>
              </div>
              {isCloudViewerSection ? (
                <span className="atanor-user-readonly-badge">{language === "ko" ? "보기 전용" : "READ ONLY"}</span>
              ) : (
                <button data-active={webSearchEnabled} onClick={() => setWebSearchEnabled((enabled) => !enabled)}>
                  {language === "ko" ? `웹 ${webSearchEnabled ? "켜짐" : "꺼짐"}` : `Web ${webSearchEnabled ? "On" : "Off"}`}
                </button>
              )}
            </header>
            {isCloudViewerSection ? (
              <div className="atanor-user-viewer-stack">
                <div className="atanor-user-viewer-grid">
                  {cloudViewerRows.map((row) => (
                    <span key={row.label}>
                      <small>{row.label}</small>
                      <strong>{row.value}</strong>
                    </span>
                  ))}
                </div>
                <div className="atanor-cloud-quick-actions">
                  <button
                    className="atanor-proof-action"
                    type="button"
                    onClick={accelerateSemanticCloudBatch}
                    disabled={semanticGrowthRunning}
                  >
                    {semanticGrowthRunning
                      ? (language === "ko" ? "가속 중" : "Accelerating")
                      : (language === "ko" ? "1000 배치 학습" : "Learn 1000 batch")}
                  </button>
                  <button
                    className="atanor-proof-action"
                    type="button"
                    onClick={refreshSemanticCloud}
                    disabled={semanticGrowthRunning}
                  >
                    {language === "ko" ? "그래프 갱신" : "Refresh graph"}
                  </button>
                </div>
                {semanticGrowthRun &&
                (Number(semanticGrowthRun.concepts_created ?? 0) > 0 ||
                  Number(semanticGrowthRun.relations_created ?? 0) > 0) ? (
                  <small className="atanor-cloud-growth-inline">
                    +{Number(semanticGrowthRun.concepts_created ?? 0).toLocaleString()} concepts / +{Number(semanticGrowthRun.relations_created ?? 0).toLocaleString()} relations
                  </small>
                ) : null}
                {semanticGrowthError ? <small className="atanor-cloud-growth-inline" data-error="true">{semanticGrowthError}</small> : null}
                <p>
                  {language === "ko"
                    ? "Cloud Brain은 현재 클라우드 브레인 후보와 proof store 상태를 관찰하는 읽기 전용 화면입니다. 질문 생성과 로컬 브레인 검색은 로컬 브레인에서만 실행됩니다."
                    : "Cloud Brain is an observation surface for Cloud Brain candidates and edge sync. Answer generation and Local Brain search run only in Local Brain."}
                </p>
              </div>
            ) : (
              <>
                <div className="atanor-user-chat-scroll" ref={chatScrollRef}>
                  {chatMessages.slice(-5).map((message, index) => (
                    <article key={`${message.role}-${index}`} data-role={message.role}>
                      <span>{message.role === "user" ? "User" : "ATANOR"}</span>
                      <p>{message.text}</p>
                      {message.evidence?.length ? (
                        <details className="atanor-trace-details">
                          <summary>{language === "ko" ? "근거 / Brain path" : "Evidence / Brain path"}</summary>
                          <small>{message.evidence.slice(0, 2).map((doc) => doc.chunk_id ?? doc.doc_id ?? "evidence").join(" · ")}</small>
                        </details>
                      ) : null}
                    </article>
                  ))}
                </div>
                <div className="atanor-user-composer">
                  <textarea
                    value={chatInput}
                    onChange={(event) => setChatInput(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault();
                        sendChat();
                      }
                    }}
                    placeholder={copy.placeholder}
                    aria-label={copy.placeholder}
                  />
                  <VoiceMicButton language={language} disabled={isGeneratingAnswer}
                    onText={(t) => setChatInput((prev) => (prev ? prev + " " : "") + t)} />
                  <button disabled={isGeneratingAnswer} onClick={sendChat}>
                    {isGeneratingAnswer ? copy.generating : copy.send}
                  </button>
                </div>
              </>
            )}
          </article>

          <article className="atanor-user-activity">
            <header>
              <h2>{copy.recentActivity}</h2>
              <span>{localBackendConnected ? "stream connected" : "local companion pending"}</span>
            </header>
            <div>
              {recentCards.map((card) => (
                <section key={card.title}>
                  <time>{card.time}</time>
                  <strong>{card.title}</strong>
                  <span>{card.value}</span>
                </section>
              ))}
            </div>
          </article>
        </section>
        ) : null}
        </>
        )}
      </section>
      <TauriUpdatePrompt />
    </main>
  );

}
