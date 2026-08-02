// Static fallback mirror of the backend plugin catalogue so the Plugin Kit UI
// renders even when the engine (:8502) is briefly unavailable. The live list
// (enabled flags + grant states) comes from the backend whenever it answers.

export const PC_CONTROL_PHRASE = "ATANOR PC 제어 허용";

export const CAPABILITIES: Record<string, { risk: string; label: string; label_en: string }> = {
  "read:graph": { risk: "safe", label: "그래프·지표 읽기", label_en: "Read graph & metrics" },
  "collect:sentences": { risk: "safe", label: "문장 수집(학습 코퍼스 추가)", label_en: "Collect sentences" },
  "net:fetch": { risk: "sensitive", label: "공개 웹 페이지 가져오기", label_en: "Fetch public web pages" },
  "fs:read": { risk: "sensitive", label: "지정한 로컬 파일 읽기", label_en: "Read a chosen local file" },
  "clipboard:read": { risk: "sensitive", label: "클립보드 텍스트 읽기", label_en: "Read clipboard text" },
  "pc:control": { risk: "dangerous", label: "PC 제어(읽기전용·허용목록)", label_en: "Control the PC (read-only)" },
};

type Def = {
  id: string; name: string; marketplace: string; version: string; kind: string;
  icon: string; description: string; default_enabled: boolean;
  capabilities: string[];
  composer: { slash: string; label: string; placeholder: string; field: string | null };
};

export const PLUGIN_DEFS: Def[] = [
  { id: "manual-paste@atanor-core", name: "붙여넣기 수집", marketplace: "atanor-core", version: "0.1.0", kind: "source", icon: "clipboard-paste", default_enabled: true, capabilities: ["collect:sentences"], description: "채팅바에 붙여넣은 텍스트를 문장으로 쪼개 학습 코퍼스에 추가합니다.", composer: { slash: "/paste", label: "붙여넣기", placeholder: "수집할 텍스트를 붙여넣기…", field: "text" } },
  { id: "chat-utterances@atanor-core", name: "대화 발화 수집", marketplace: "atanor-core", version: "0.1.0", kind: "source", icon: "message-square", default_enabled: true, capabilities: ["collect:sentences"], description: "내 대화 턴(로컬)을 발화 코퍼스로 모읍니다. 외부 전송 없음.", composer: { slash: "/chat", label: "대화수집", placeholder: "수집할 대화 텍스트…", field: "text" } },
  { id: "web-article@atanor-web", name: "공개 웹문서", marketplace: "atanor-web", version: "0.1.0", kind: "source", icon: "globe", default_enabled: true, capabilities: ["net:fetch", "collect:sentences"], description: "공개 웹페이지(위키 등 공식 문서)의 본문 문장을 가져옵니다. 인증/비공개 페이지 불가.", composer: { slash: "/url", label: "웹문서", placeholder: "https:// 공개 문서 URL", field: "url" } },
  { id: "rss-feed@atanor-web", name: "RSS/뉴스 피드", marketplace: "atanor-web", version: "0.1.0", kind: "source", icon: "rss", default_enabled: true, capabilities: ["net:fetch", "collect:sentences"], description: "공개 RSS/Atom 피드의 제목·요약을 다양한 구어/문어 발화로 수집합니다.", composer: { slash: "/rss", label: "RSS", placeholder: "공개 RSS/Atom 피드 URL", field: "url" } },
  { id: "wikipedia-stream@atanor-web", name: "위키백과 스트림", marketplace: "atanor-web", version: "0.1.0", kind: "source", icon: "book-open", default_enabled: true, capabilities: ["net:fetch", "collect:sentences"], description: "위키백과 임의 문서의 공식 문장을 스트리밍 수집합니다(공개 API).", composer: { slash: "/wiki", label: "위키", placeholder: "lang: en 또는 ko", field: "lang" } },
  { id: "file-import@atanor-local", name: "로컬 파일 가져오기", marketplace: "atanor-local", version: "0.1.0", kind: "source", icon: "file-text", default_enabled: false, capabilities: ["fs:read", "collect:sentences"], description: "내가 지정한 .txt/.md/.jsonl/.csv 파일의 문장을 가져옵니다.", composer: { slash: "/file", label: "파일", placeholder: "로컬 파일 경로", field: "path" } },
  { id: "clipboard-harvester@atanor-local", name: "클립보드 수집", marketplace: "atanor-local", version: "0.1.0", kind: "source", icon: "clipboard", default_enabled: false, capabilities: ["clipboard:read", "collect:sentences"], description: "클립보드의 텍스트(은어·구어 등 다양한 발화)를 수집합니다. 민감 권한.", composer: { slash: "/clip", label: "클립보드", placeholder: "복사 후 실행", field: null } },
  { id: "pc-bridge@atanor-labs", name: "PC 브리지(실험)", marketplace: "atanor-labs", version: "0.1.0", kind: "tool", icon: "monitor", default_enabled: false, capabilities: ["pc:control"], description: "읽기전용·허용목록 PC 동작(디렉터리 목록, 클립보드). 위험 권한 — 승인 문구 필요.", composer: { slash: "/pc", label: "PC", placeholder: "action: list_directory / clipboard_read", field: "path" } },
];

const RISK_RANK: Record<string, number> = { safe: 0, sensitive: 1, dangerous: 2 };

export function fallbackList() {
  const plugins = PLUGIN_DEFS.map((p) => {
    const caps = p.capabilities.map((c) => ({
      id: c, risk: CAPABILITIES[c]?.risk ?? "safe",
      label: CAPABILITIES[c]?.label ?? c, label_en: CAPABILITIES[c]?.label_en ?? c,
      state: CAPABILITIES[c]?.risk === "safe" ? "granted" : "denied",
    }));
    const maxRank = Math.max(0, ...p.capabilities.map((c) => RISK_RANK[CAPABILITIES[c]?.risk ?? "safe"] ?? 0));
    const max_risk = Object.keys(RISK_RANK).find((k) => RISK_RANK[k] === maxRank) ?? "safe";
    return {
      id: p.id, name: p.name, marketplace: p.marketplace, version: p.version, kind: p.kind,
      icon: p.icon, description: p.description, composer: p.composer, max_risk,
      enabled: p.default_enabled, capabilities: caps,
      ready: caps.every((c) => c.state === "granted"),
    };
  });
  return {
    plugins,
    marketplaces: Array.from(new Set(PLUGIN_DEFS.map((p) => p.marketplace))).sort(),
    capabilities: CAPABILITIES,
    pc_control_phrase: PC_CONTROL_PHRASE,
    offline: true,
  };
}
