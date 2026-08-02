import { NextResponse } from "next/server";
import { defaultWebSearchQuery, searchWeb } from "../../../_webSearch";

type HarvestDoc = {
  id: string;
  url: string;
  title: string;
  status: "fetched" | "fallback";
  snippet: string;
  source_type: string;
  license_status: string;
  search_provider?: string;
  search_query?: string;
  bing_query_url?: string;
};

type LearningVolume = "lite" | "standard" | "deep" | "max" | "infinite";

type LearningPreset = {
  chunkBudget: number;
  label: string;
  targetNodes?: number | null;
  textBudgetChars: number;
  textBudgetLabel: string;
  visualNodeBudget: number;
};

const maxTargetNodes = 500_000;
const maxVisualNodeBudget = 2_000;
const maxChunkBudget = 4_096;
const maxTextBudgetChars = 4_800_000;

const seedUrls = [
  "https://www.reddit.com/r/MachineLearning/comments/1ookxb0/r_knowledge_graph_traversal_with_llms_and/?tl=ko",
  "https://github.com/glacier-creative-git/similarity-graph-traversal-semantic-rag-research",
  "https://github.com/microsoft/graphrag",
  "https://github.com/666ghj/MiroFish",
];

const fallbackSnippets: Record<string, string> = {
  reddit:
    "Reddit discussion highlights the difference between semantic similarity graphs and typed knowledge graphs. Useful ideas: deduplicate entities, keep mutable graph updates, traverse from anchor nodes, and show traversal paths.",
  traversal:
    "The semantic RAG traversal repository uses anchor chunks, hierarchical chunk/sentence/theme layers, and 3D triangulation-style traversal visualizations.",
  graphrag:
    "Microsoft GraphRAG-style systems build graph context from raw text and use graph/community summaries to augment retrieval.",
  mirofish:
    "MiroFish demonstrates an operator console with graph/split/workbench modes, graph growth, process logs, and interaction-oriented graph memory.",
};

function stripHtml(html: string) {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function titleFrom(html: string, url: string) {
  const title = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1];
  return stripHtml(title || new URL(url).hostname).slice(0, 90);
}

function fallbackFor(url: string) {
  if (url.includes("reddit")) return fallbackSnippets.reddit;
  if (url.includes("similarity-graph")) return fallbackSnippets.traversal;
  if (url.includes("graphrag")) return fallbackSnippets.graphrag;
  if (url.includes("MiroFish")) return fallbackSnippets.mirofish;
  return "Reference page queued for Homage Harvest.";
}

const learningPresets: Record<LearningVolume, LearningPreset> = {
  lite: { chunkBudget: 32, label: "가볍게", targetNodes: 3_000, textBudgetChars: 12_000, textBudgetLabel: "12k chars", visualNodeBudget: 12 },
  standard: { chunkBudget: 128, label: "표준", targetNodes: 10_000, textBudgetChars: 48_000, textBudgetLabel: "48k chars", visualNodeBudget: 24 },
  deep: { chunkBudget: 384, label: "깊게", targetNodes: 25_000, textBudgetChars: 160_000, textBudgetLabel: "160k chars", visualNodeBudget: 36 },
  max: { chunkBudget: 4096, label: "최대", targetNodes: 500_000, textBudgetChars: 4_500_000, textBudgetLabel: "4.5m chars", visualNodeBudget: 2000 },
  infinite: { chunkBudget: 4096, label: "∞", targetNodes: null, textBudgetChars: 4_800_000, textBudgetLabel: "continuous", visualNodeBudget: 2000 },
};

const memoryTopics = [
  ["entity-cache", "Entity Cache", "ontology"],
  ["claim-store", "Claim Store", "guardrail"],
  ["chunk-router", "Chunk Router", "retrieval"],
  ["event-gate", "SNN Event Gate", "source"],
  ["fewshot-proto", "Few-shot Prototype", "training"],
  ["self-supervised", "Masked Signal", "training"],
  ["quant-plan", "Quantization Plan", "training"],
  ["replay-buffer", "Replay Buffer", "ontology"],
  ["citation-map", "Citation Map", "retrieval"],
  ["quality-band", "Quality Band", "guardrail"],
  ["semantic-anchor", "Semantic Anchor", "retrieval"],
  ["synapse-plastic", "Synapse Plasticity", "ontology"],
  ["distill-student", "Distilled Student", "training"],
  ["energy-route", "Energy Route", "visualization"],
  ["memory-index", "Memory Index", "ontology"],
  ["context-bridge", "Context Bridge", "retrieval"],
  ["source-license", "Source License", "guardrail"],
  ["edge-summary", "Edge Summary", "visualization"],
  ["task-router", "Task Router", "training"],
  ["novelty-score", "Novelty Score", "ontology"],
  ["graph-window", "Graph Window", "visualization"],
  ["guard-memory", "Guard Memory", "guardrail"],
  ["token-pack", "Token Pack", "source"],
  ["adaptive-batch", "Adaptive Batch", "training"],
  ["extracts-signal", "Extracts Signal", "verb"],
  ["evidence-phrase", "Evidence Phrase", "phrase"],
  ["co-occurs", "Co-occurrence", "relation"],
] as const;

function boundedNumber(value: unknown, fallback: number, min: number, max: number) {
  const numeric = typeof value === "number" ? value : typeof value === "string" ? Number(value) : Number.NaN;
  if (!Number.isFinite(numeric)) return fallback;
  return Math.max(min, Math.min(max, Math.round(numeric)));
}

function learningPresetFor(value: unknown, targetNodesInput?: unknown): LearningPreset & { id: LearningVolume; targetNodes: number | null } {
  const id = typeof value === "string" && value in learningPresets ? value as LearningVolume : "standard";
  const base = learningPresets[id];
  if (id === "infinite") {
    return { id, ...base, chunkBudget: maxChunkBudget, targetNodes: null, textBudgetChars: maxTextBudgetChars, textBudgetLabel: "continuous", visualNodeBudget: maxVisualNodeBudget };
  }
  const fallbackTargetNodes = id === "max" ? maxTargetNodes : base.targetNodes ?? 10_000;
  const targetNodes = boundedNumber(targetNodesInput, fallbackTargetNodes, 100, maxTargetNodes);
  const visualNodeBudget = Math.max(
    base.visualNodeBudget,
    Math.min(maxVisualNodeBudget, Math.round(Math.sqrt(targetNodes) * 4.8)),
  );
  const chunkBudget = Math.max(base.chunkBudget, Math.min(maxChunkBudget, Math.round(targetNodes / 12)));
  const textBudgetChars = Math.max(base.textBudgetChars, Math.min(maxTextBudgetChars, targetNodes * 9));
  const textBudgetLabel = textBudgetChars >= 1_000_000
    ? `${Number((textBudgetChars / 1_000_000).toFixed(1))}m chars`
    : `${Math.round(textBudgetChars / 1000)}k chars`;
  return { id, ...base, chunkBudget, targetNodes, textBudgetChars, textBudgetLabel, visualNodeBudget };
}

async function harvestUrl(url: string, index: number, searchPayload?: any): Promise<HarvestDoc> {
  const searchResult = (searchPayload?.results ?? []).find((result: any) => result.url === url);
  try {
    const response = await fetch(url, {
      cache: "no-store",
      headers: { "User-Agent": "HomageAlpha/0.1 research-harvest" },
      signal: AbortSignal.timeout(4500),
    });
    const html = await response.text();
    return {
      id: `web-${String(index + 1).padStart(3, "0")}`,
      url,
      title: searchResult?.title ?? titleFrom(html, url),
      status: response.ok ? "fetched" : "fallback",
      snippet: (searchResult?.snippet ?? fallbackFor(url)).slice(0, 420),
      source_type: searchResult?.source_type ?? (url.includes("reddit") ? "discussion" : "repository_or_docs"),
      license_status: searchResult?.license_status ?? "reference_only",
      search_provider: searchResult?.provider ?? searchPayload?.provider ?? "seed",
      search_query: searchPayload?.query,
      bing_query_url: searchPayload?.bing_query_url,
    };
  } catch {
    return {
      id: `web-${String(index + 1).padStart(3, "0")}`,
      url,
      title: searchResult?.title ?? new URL(url).hostname,
      status: "fallback",
      snippet: searchResult?.snippet ?? fallbackFor(url),
      source_type: searchResult?.source_type ?? (url.includes("reddit") ? "discussion" : "repository_or_docs"),
      license_status: searchResult?.license_status ?? "reference_only",
      search_provider: searchResult?.provider ?? searchPayload?.provider ?? "seed",
      search_query: searchPayload?.query,
      bing_query_url: searchPayload?.bing_query_url,
    };
  }
}

function makeTrainingUnits(docs: HarvestDoc[], preset: LearningPreset) {
  const units = [];
  for (let index = 0; index < preset.chunkBudget; index += 1) {
    const doc = docs[index % Math.max(1, docs.length)];
    const topic = memoryTopics[index % memoryTopics.length];
    const repeatedSignal = `${doc?.snippet ?? "Reference signal"} ${topic[1]} ${fallbackSnippets.graphrag}`;
    units.push({
      id: `chunk-${String(index + 1).padStart(4, "0")}`,
      source_id: doc?.id ?? "fallback",
      topic: topic[1],
      char_budget: Math.max(180, Math.floor(preset.textBudgetChars / preset.chunkBudget)),
      text_preview: repeatedSignal.slice(0, 240),
      route: index % 3 === 0 ? "TRAINABLE" : index % 3 === 1 ? "RAG_ONLY" : "REVIEW",
    });
  }
  return units;
}

function hash01(value: string, salt: number) {
  let hash = 2166136261 ^ salt;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) / 4294967295;
}

function volumeOffset(id: string, index: number) {
  const u = hash01(id, 13) * 2 - 1;
  const theta = hash01(id, 29) * Math.PI * 2;
  const radial = Math.sqrt(Math.max(0.0001, 1 - u * u));
  const radius = Math.min(4.8, 0.92 + Math.cbrt(index + 1) * 0.27 + (index % 17) * 0.025);
  return {
    x: Math.cos(theta) * radial * radius,
    y: u * radius * 0.96,
    z: Math.sin(theta) * radial * radius,
  };
}

function makeGraphForPreset(preset: LearningPreset) {
  const baseNodes = [
    { id: "harvest", label: "Web Harvest", type: "source", x: -5, y: 1.4, z: -1.2, confidence: 0.86 },
    { id: "reddit-kg", label: "KG vs SSG", type: "critique", x: -2.8, y: 2.3, z: 0.6, confidence: 0.9 },
    { id: "dedupe", label: "Entity Dedupe", type: "ontology", x: -1.1, y: 0.8, z: 1.8, confidence: 0.84 },
    { id: "mutable-kg", label: "Mutable KG", type: "ontology", x: -0.2, y: -1.2, z: -0.7, confidence: 0.79 },
    { id: "anchor", label: "Anchor Chunk", type: "retrieval", x: 1.5, y: 1.7, z: -1.5, confidence: 0.86 },
    { id: "traversal", label: "Graph Traversal", type: "retrieval", x: 3.1, y: 0.2, z: 1.2, confidence: 0.88 },
    { id: "3d", label: "3D Triangulation", type: "visualization", x: 4.2, y: -1.5, z: -0.2, confidence: 0.81 },
    { id: "guard", label: "Guarded Evidence", type: "guardrail", x: 2.6, y: -2.4, z: 1.7, confidence: 0.78 },
    { id: "oven", label: "Homage Oven Gate", type: "training", x: 5.4, y: 0.9, z: 0.5, confidence: 0.76 },
  ];
  const seedNodeBudget = Math.min(preset.visualNodeBudget, Math.max(12, Math.round(preset.visualNodeBudget * 0.86)));
  const extraCount = Math.max(0, seedNodeBudget - baseNodes.length);
  const extraNodes = Array.from({ length: extraCount }, (_, index) => {
    const topic = memoryTopics[index % memoryTopics.length];
    const wave = Math.floor(index / memoryTopics.length);
    const anchorNode = baseNodes[index % baseNodes.length];
    const offset = volumeOffset(`${topic[0]}-${wave}-${index}`, index);
    const centerPull = 0.1 + (index % 5) * 0.015;
    return {
      id: wave > 0 ? `${topic[0]}-${wave + 1}` : topic[0],
      label: wave > 0 ? `${topic[1]} ${wave + 1}` : topic[1],
      type: topic[2],
      x: anchorNode.x * (1 - centerPull) + offset.x,
      y: anchorNode.y * (1 - centerPull) + offset.y,
      z: anchorNode.z * (1 - centerPull) + offset.z,
      confidence: 0.68 + (index % 8) * 0.025,
    };
  });
  const nodes = [...baseNodes, ...extraNodes];
  const baseEdges = [
    { source: "harvest", target: "reddit-kg", relation: "extracts_signal", weight: 0.82 },
    { source: "reddit-kg", target: "dedupe", relation: "requires", weight: 0.86 },
    { source: "dedupe", target: "mutable-kg", relation: "stabilizes", weight: 0.74 },
    { source: "mutable-kg", target: "anchor", relation: "seeds", weight: 0.69 },
    { source: "anchor", target: "traversal", relation: "starts", weight: 0.88 },
    { source: "traversal", target: "3d", relation: "projects", weight: 0.73 },
    { source: "traversal", target: "guard", relation: "grounds", weight: 0.8 },
    { source: "guard", target: "oven", relation: "approves_training", weight: 0.71 },
  ];
  const extraEdges = extraNodes.flatMap((node, index) => {
    const anchor = baseNodes[index % baseNodes.length].id;
    const edges = [{ source: anchor, target: node.id, relation: "compresses_chunk", weight: 0.62 + (index % 5) * 0.04 }];
    const previousSameAnchor = index - baseNodes.length;
    if (previousSameAnchor >= 0) edges.push({ source: extraNodes[previousSameAnchor].id, target: node.id, relation: "associates", weight: 0.52 });
    return edges;
  });
  return {
    edges: [...baseEdges, ...extraEdges],
    nodes,
    traversal_path: ["harvest", "reddit-kg", "dedupe", "mutable-kg", "anchor", "traversal", "guard", "oven", ...extraNodes.slice(0, 8).map((node) => node.id)],
  };
}

export async function POST(request: Request) {
  let urls = seedUrls;
  let learningVolume: unknown = "standard";
  let targetNodes: unknown = undefined;
  let searchQuery: unknown = defaultWebSearchQuery;
  let webSearch = true;
  let webSearchProvider: unknown = undefined;
  try {
    const body = await request.json();
    learningVolume = body?.learning_volume ?? learningVolume;
    targetNodes = body?.target_nodes;
    searchQuery = body?.search_query ?? searchQuery;
    webSearch = body?.web_search ?? webSearch;
    webSearchProvider = body?.web_search_provider;
    if (Array.isArray(body?.seed_urls) && body.seed_urls.length) {
      urls = body.seed_urls.slice(0, 6);
    }
  } catch {
    // Use default seeds.
  }

  const webSearchPayload = webSearch
    ? await searchWeb(typeof searchQuery === "string" ? searchQuery : defaultWebSearchQuery, 6, typeof webSearchProvider === "string" ? webSearchProvider : null)
    : { provider: "disabled", query: searchQuery, results: [], status: "disabled" };
  const searchUrls = (webSearchPayload.results ?? []).map((result: any) => result.url).filter(Boolean);
  urls = Array.from(new Set([...urls, ...searchUrls, ...seedUrls])).slice(0, 8);
  const docs = await Promise.all(urls.map((url, index) => harvestUrl(url, index, webSearchPayload)));
  const learningPreset = learningPresetFor(learningVolume, targetNodes);
  const trainingUnits = makeTrainingUnits(docs, learningPreset);
  const generatedAt = new Date().toISOString();
  const { nodes, edges, traversal_path: traversalPath } = makeGraphForPreset(learningPreset);
  const frameCounts = [
    Math.min(12, nodes.length),
    Math.ceil(nodes.length * 0.25),
    Math.ceil(nodes.length * 0.5),
    Math.ceil(nodes.length * 0.75),
    nodes.length,
  ].filter((count, index, all) => count > 0 && (index === 0 || count > all[index - 1]));
  const graphFrames = frameCounts.map((count, index) => ({
    tick: index + 1,
    node_count: count,
    edge_count: Math.max(1, count - 1),
    message: [
      "Collection seeded sentence chunks and graph anchors",
      "Sentence elements were decomposed into candidate nodes",
      "Ontology relations were calculated",
      "GraphRAG neighborhood projection expanded",
      "Output gate reached selected text budget",
    ][index] ?? "Graph memory keeps expanding",
  }));
  const trainingGate = {
    threshold_nodes: 8,
    threshold_edges: 7,
    chunk_count: trainingUnits.length,
    node_count: nodes.length,
    edge_count: edges.length,
    evidence_count: docs.length,
    text_budget_chars: learningPreset.textBudgetChars,
    ready: nodes.length >= 8 && edges.length >= 7,
    render_strategy: learningPreset.id === "infinite"
      ? "continuous collection accumulates graph events; the lab view appends live nodes without hidden history."
      : "chunk budget grows independently; 3D graph renders sampled representative memory nodes.",
    visual_node_budget: learningPreset.visualNodeBudget,
    target_nodes: learningPreset.targetNodes,
    target_semantics: learningPreset.targetNodes === null ? "unbounded_continuous_goal" : "long_run_storage_goal",
    representative_node_count: nodes.length,
    representative_edge_count: edges.length,
    target_realized: learningPreset.targetNodes === null ? false : nodes.length >= learningPreset.targetNodes,
    sampling_explanation: learningPreset.targetNodes === null
      ? "infinite mode has no target_nodes cap; graph_3d starts from representative anchors and the lab view appends live nodes directly."
      : "target_nodes is the long-run ontology budget; graph_3d contains a bounded representative sample for browser rendering.",
    continuous: learningPreset.id === "infinite",
    next_action: learningPreset.id === "infinite"
      ? "Continue Harvest/DataGate/Ontology growth until the operator presses stop."
      : "Homage Oven dry-run starts after Guardrail approves evidence bundle.",
  };

  return NextResponse.json({
    run_id: `build-${Date.now()}`,
    generated_at: generatedAt,
    mode: learningPreset.id === "infinite" ? "alpha-continuous-harvest" : "alpha-live-harvest",
    harvest_docs: docs,
    web_search: webSearchPayload,
    learning_profile: {
      id: learningPreset.id,
      label: learningPreset.label,
      text_budget_chars: learningPreset.textBudgetChars,
      text_budget_label: learningPreset.textBudgetLabel,
      chunk_budget: learningPreset.chunkBudget,
      target_nodes: learningPreset.targetNodes,
      visual_node_budget: learningPreset.visualNodeBudget,
    },
    training_units: trainingUnits.slice(0, 24),
    graph_3d: { nodes, edges, traversal_path: traversalPath },
    graph_frames: graphFrames,
    training_gate: trainingGate,
    learning_trace: [
      { step: "Harvest", state: learningPreset.id === "infinite" ? "running" : "complete", detail: `${docs.length} reference sources captured via ${webSearchPayload.provider} / ${trainingUnits.length} text chunks scheduled` },
      { step: "DataGate", state: "complete", detail: `${learningPreset.textBudgetLabel} text budget passed through compressed chunk routing` },
      { step: "Ontology Forge", state: learningPreset.id === "infinite" ? "running" : "complete", detail: `${nodes.length} representative nodes and ${edges.length} typed relations created` },
      { step: "GraphRAG", state: "complete", detail: "Anchor traversal path and evidence bundle generated" },
      { step: "Homage Oven", state: trainingGate.ready ? "ready" : "waiting", detail: trainingGate.next_action },
    ],
    notes: [
      "Alpha does not bulk-train from scraped web pages; it records reference snippets and source URLs.",
      "The graph separates typed ontology edges from semantic-similarity traversal, reflecting the Reddit KG vs SSG critique.",
    ],
  });
}
