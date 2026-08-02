import { NextResponse } from "next/server";
import { demoGraphRAGQuery } from "../../_alphaDemo";
import { proxyJson } from "../../_backend";
import { isFreshSearchQuery, isKnowledgeLookupQuery, searchWeb, webResultsToEvidence } from "../../_webSearch";

function isLegacySurfaceResult(body: any) {
  const result = body?.result ?? {};
  return (
    result.method === "atanor-native-web-search-rag-v1"
    || result.method === "atanor-native-graphrag-utterance-v1"
    || result.method === "atanor-native-no-node-utterance-v1"
    || result.method === "atanor-conversation-router-v1"
    || result.method === "atanor-graph-inspection-v1"
    || result.method === "atanor-graph-legend-v1"
    || result.answer_engine?.mode === "native-web-search-grounded-alpha"
    || result.answer_engine?.mode === "native-next-thought-alpha"
    || result.answer_engine?.mode === "native-no-node-sentence-alpha"
    || result.answer_engine?.mode === "conversation-surface-no-retrieval-alpha"
    || result.answer_engine?.mode === "graph-inspection-control-alpha"
    || result.answer_engine?.mode === "graph-legend-control-alpha"
    || ["greeting", "thanks", "conversation", "inspection"].includes(String(result.answer_kind ?? ""))
  );
}

function normalizeQuery(query: string) {
  return query.trim().toLowerCase().replace(/[\s!.?,;:()[\]{}"'`~\u3002\uff01\uff1f]+/g, "");
}

function isLowInformationConversationQuery(query: string) {
  const compact = normalizeQuery(query);
  if (!compact) return true;
  const exactGreetings = new Set([
    "hi",
    "hello",
    "hey",
    "yo",
    "thanks",
    "thankyou",
    "\uc548\ub155",
    "\uc548\ub155\ud558\uc138\uc694",
    "\ud558\uc774",
    "\uace0\ub9c8\uc6cc",
    "\uac10\uc0ac",
    "\uac10\uc0ac\ud569\ub2c8\ub2e4",
  ]);
  if (exactGreetings.has(compact)) return true;
  const tokens = query.toLowerCase().match(/[a-z0-9\uac00-\ud7a3_-]+/g) ?? [];
  return tokens.length <= 2 && tokens.some((token) => exactGreetings.has(normalizeQuery(token)));
}

export async function POST(request: Request) {
  const body = await request.text();
  let query = "GraphRAG evidence";
  let webSearch = false;
  let webSearchProvider: string | null = null;
  let brainMode = "unified";
  let locale: string | null = null;
  let includeTrace = true;
  try {
    const parsed = JSON.parse(body || "{}");
    query = parsed.query ?? query;
    webSearch = Boolean(parsed.web_search ?? false);
    webSearchProvider = parsed.web_search_provider ?? null;
    const requestedBrainMode = String(parsed.brain_mode ?? "");
    brainMode = requestedBrainMode === "dual"
      ? "unified"
      : ["local", "cloud", "unified"].includes(requestedBrainMode)
        ? requestedBrainMode
        : "unified";
    locale = typeof parsed.locale === "string" ? parsed.locale : null;
    includeTrace = parsed.include_trace !== false;
  } catch {
    // Fall through to deterministic demo with the default query.
  }
  if (isLowInformationConversationQuery(query)) {
    webSearch = false;
  } else if (brainMode === "local") {
    webSearch = false;
  } else if (brainMode === "cloud") {
    webSearch = true;
  } else {
    webSearch = webSearch || isFreshSearchQuery(query) || isKnowledgeLookupQuery(query);
  }

  try {
    const proxied = await proxyJson("/api/graphrag/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, web_search: webSearch, web_search_provider: webSearchProvider, brain_mode: brainMode, locale, include_trace: includeTrace }),
    });
    if (proxied?.body?.result?.answer && !isLegacySurfaceResult(proxied.body) && (!webSearch || proxied.body.result.web_search)) {
      return NextResponse.json(proxied.body, { status: proxied.status });
    }
  } catch {
    // Fall through to deterministic demo.
  }
  if (webSearch) {
    const webSearchPayload = await searchWeb(query, 5, webSearchProvider);
    return NextResponse.json(demoGraphRAGQuery(query, webResultsToEvidence(webSearchPayload.results), webSearchPayload));
  }
  return NextResponse.json(demoGraphRAGQuery(query));
}
