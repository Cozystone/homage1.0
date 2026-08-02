type AnyRecord = Record<string, unknown>;

type SeedViewer = AnyRecord & {
  nodes: AnyRecord[];
  edges: AnyRecord[];
  filters?: AnyRecord;
};

const bundledViewerExport: SeedViewer = {
  schema: "atanor.seed-research.viewer-fallback.v1",
  mode: "seed_research_viewer",
  read_only: true,
  not_local_brain: true,
  run_id: "bundled_seed_fallback_v1",
  badge: "BUNDLED SEED",
  concept_count: 6,
  relation_count: 7,
  filters: {
    relation_types: ["supports", "requires", "distinguishes", "grounds"],
    trust_states: ["seed_anchor"],
  },
  metrics: {
    external_llm_used: false,
    external_sllm_used: false,
    local_brain_write: false,
    generated_export: false,
  },
  nodes: [
    {
      id: "seed.core.evidence",
      label: "Evidence",
      labels: { ko: "근거", en: "Evidence" },
      aliases: { ko: ["증거", "근거 문서"], en: ["grounding", "source evidence"] },
      trust_state: "seed_anchor",
      confidence: 0.92,
    },
    {
      id: "seed.core.claim",
      label: "Claim",
      labels: { ko: "주장", en: "Claim" },
      aliases: { ko: ["답변 후보", "설명 문장"], en: ["answer claim", "assertion"] },
      trust_state: "seed_anchor",
      confidence: 0.88,
    },
    {
      id: "seed.core.verification",
      label: "Verification",
      labels: { ko: "검증", en: "Verification" },
      aliases: { ko: ["확인", "대조"], en: ["checking", "validation"] },
      trust_state: "seed_anchor",
      confidence: 0.9,
    },
    {
      id: "seed.core.local_brain",
      label: "Local Brain",
      labels: { ko: "로컬 브레인", en: "Local Brain" },
      aliases: { ko: ["개인 메모리", "로컬 메모리"], en: ["private memory", "local memory"] },
      trust_state: "seed_anchor",
      confidence: 0.86,
    },
    {
      id: "seed.core.cloud_brain",
      label: "Cloud Brain",
      labels: { ko: "클라우드 브레인", en: "Cloud Brain" },
      aliases: { ko: ["공용 지식", "공용 그래프"], en: ["public graph", "semantic cloud"] },
      trust_state: "seed_anchor",
      confidence: 0.84,
    },
    {
      id: "seed.core.uncertainty",
      label: "Uncertainty",
      labels: { ko: "불확실성", en: "Uncertainty" },
      aliases: { ko: ["근거 부족", "모름"], en: ["unknown", "insufficient evidence"] },
      trust_state: "seed_anchor",
      confidence: 0.87,
    },
  ],
  edges: [
    { id: "seed.edge.evidence.grounds.claim", source: "seed.core.evidence", relation: "grounds", target: "seed.core.claim", trust_state: "seed_anchor", confidence: 0.92 },
    { id: "seed.edge.verification.requires.evidence", source: "seed.core.verification", relation: "requires", target: "seed.core.evidence", trust_state: "seed_anchor", confidence: 0.9 },
    { id: "seed.edge.claim.requires.verification", source: "seed.core.claim", relation: "requires", target: "seed.core.verification", trust_state: "seed_anchor", confidence: 0.89 },
    { id: "seed.edge.local.distinguishes.cloud", source: "seed.core.local_brain", relation: "distinguishes", target: "seed.core.cloud_brain", trust_state: "seed_anchor", confidence: 0.86 },
    { id: "seed.edge.cloud.supports.evidence", source: "seed.core.cloud_brain", relation: "supports", target: "seed.core.evidence", trust_state: "seed_anchor", confidence: 0.82 },
    { id: "seed.edge.uncertainty.requires.evidence", source: "seed.core.uncertainty", relation: "requires", target: "seed.core.evidence", trust_state: "seed_anchor", confidence: 0.87 },
    { id: "seed.edge.verification.supports.uncertainty", source: "seed.core.verification", relation: "supports", target: "seed.core.uncertainty", trust_state: "seed_anchor", confidence: 0.8 },
  ],
};

function textMatches(node: AnyRecord, search: string) {
  if (!search) return true;
  const labels = typeof node.labels === "object" && node.labels ? node.labels as AnyRecord : {};
  const aliases = typeof node.aliases === "object" && node.aliases ? node.aliases as AnyRecord : {};
  const values = [
    node.label,
    labels.ko,
    labels.en,
    ...Object.values(aliases).flatMap((value) => Array.isArray(value) ? value : []),
  ];
  const needle = search.toLocaleLowerCase();
  return values.some((value) => String(value ?? "").toLocaleLowerCase().includes(needle));
}

export async function loadBundledSeedViewer() {
  return JSON.parse(JSON.stringify(bundledViewerExport)) as SeedViewer;
}

export function filterSeedViewer(viewer: SeedViewer, search: string, relationType: string, trustState: string) {
  let nodes = viewer.nodes.filter(
    (node) => textMatches(node, search) && (trustState === "all" || node.trust_state === trustState),
  );
  const nodeIds = new Set(nodes.map((node) => node.id));
  const edges = viewer.edges.filter(
    (edge) =>
      nodeIds.has(edge.source) &&
      nodeIds.has(edge.target) &&
      (relationType === "all" || edge.relation === relationType) &&
      (trustState === "all" || edge.trust_state === trustState),
  );
  if (relationType !== "all") {
    const visibleIds = new Set(edges.flatMap((edge) => [edge.source, edge.target]));
    nodes = nodes.filter((node) => visibleIds.has(node.id));
  }
  return {
    ...viewer,
    nodes,
    edges,
    visible_concept_count: nodes.length,
    visible_relation_count: edges.length,
    query: { search, relation_type: relationType, trust_state: trustState },
    local_brain_isolation: {
      reads_local_brain: false,
      writes_local_brain: false,
      source: "bundled_seed_fallback",
    },
  };
}

const tokenize = (text: string) => text.toLocaleLowerCase().match(/[0-9a-z_\-\uac00-\ud7a3]+/g) ?? [];

function nodeTerms(node: AnyRecord) {
  const labels = typeof node.labels === "object" && node.labels ? node.labels as AnyRecord : {};
  const aliases = typeof node.aliases === "object" && node.aliases ? node.aliases as AnyRecord : {};
  return [
    node.id,
    node.label,
    labels.ko,
    labels.en,
    ...Object.values(aliases).flatMap((value) => Array.isArray(value) ? value : []),
  ].map((value) => String(value ?? "").toLocaleLowerCase()).filter(Boolean);
}

export async function bundledRuntimeTrace(query: string) {
  const viewer = await loadBundledSeedViewer();
  const queryTokens = new Set(tokenize(query));
  const queryText = tokenize(query).join(" ");
  const matched = viewer.nodes
    .filter((node) =>
      nodeTerms(node).some((term) => {
        const termTokens = tokenize(term);
        return queryText.includes(term) || termTokens.some((token) => queryTokens.has(token));
      }),
    )
    .map((node) => ({
      concept_id: node.id,
      label: node.label ?? node.id,
      aliases_matched: [],
      match_reason: "bundled_seed",
      confidence: node.confidence ?? 0.72,
    }));
  const matchedIds = new Set(matched.map((node) => node.concept_id));
  for (const edge of viewer.edges) {
    if (matchedIds.size === 0 || matchedIds.size > 8) break;
    const source = String(edge.source ?? "");
    const target = String(edge.target ?? "");
    const related = matchedIds.has(source) && !matchedIds.has(target) ? target : matchedIds.has(target) && !matchedIds.has(source) ? source : "";
    if (!related) continue;
    const node = viewer.nodes.find((candidate) => candidate.id === related);
    if (!node) continue;
    matchedIds.add(related);
    matched.push({
      concept_id: related,
      label: node.label ?? related,
      aliases_matched: [],
      match_reason: "relation_context",
      confidence: edge.confidence ?? 0.6,
    });
  }
  const matchedEdges = viewer.edges
    .filter((edge) => matchedIds.has(edge.source) && matchedIds.has(edge.target))
    .map((edge) => ({ source: edge.source, relation: edge.relation, target: edge.target, confidence: edge.confidence ?? 0 }));
  return {
    query,
    local_graph_state: {
      local_brain_initialized: false,
      local_total_nodes: 0,
      local_total_edges: 0,
      local_evidence_sufficient: false,
      seed_written_to_local_brain: false,
      seed_counted_as_learned_memory: false,
    },
    seed_anchor_trace: {
      seed_anchor_ready: true,
      seed_used: matched.length > 0,
      matched_seed_concepts: matched.slice(0, 12),
      matched_seed_edges: matchedEdges.slice(0, 18),
      anchor_role: "bundled_seed_retrieval_verification_alignment",
      final_answer_generation_claimed: false,
      external_llm_used: false,
      external_sllm_used: false,
      rule_based_answer_engine: false,
    },
    cloud_alignment_trace: {
      cloud_checked: false,
      candidate_fragments_checked: 0,
      fragments_aligned_to_seed: 0,
      alignment_ready: true,
      aligned_fragment_ids: [],
    },
    runtime_claim: "Bundled Seed fallback is a read-only retrieval/verification anchor only.",
  };
}
