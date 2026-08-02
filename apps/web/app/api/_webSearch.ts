export type WebSearchResult = {
  id: string;
  title: string;
  url: string;
  snippet: string;
  provider: string;
  source_type: string;
  license_status: string;
  search_score?: number;
};

export const defaultWebSearchQuery = "GraphRAG neuromorphic continual learning low power AI architecture";

const staticResults: WebSearchResult[] = [
  {
    id: "web-static-001",
    title: "Microsoft GraphRAG",
    url: "https://github.com/microsoft/graphrag",
    snippet: "Microsoft GraphRAG provides graph-based retrieval augmented generation with indexing and query workflows.",
    provider: "static",
    source_type: "repository_or_docs",
    license_status: "reference_only",
  },
  {
    id: "web-static-002",
    title: "Grounding with Bing Search tools with the agents API",
    url: "https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/bing-tools",
    snippet: "Microsoft Foundry agents can use Grounding with Bing Search to incorporate real-time public web data and cite sources.",
    provider: "static",
    source_type: "official_docs",
    license_status: "reference_only",
  },
  {
    id: "web-static-003",
    title: "Bing Search APIs retiring on August 11, 2025",
    url: "https://learn.microsoft.com/en-us/lifecycle/announcements/bing-search-api-retirement",
    snippet: "Microsoft says Bing Search APIs retire on August 11, 2025 and recommends Grounding with Bing Search as part of Azure AI Agents.",
    provider: "static",
    source_type: "official_docs",
    license_status: "reference_only",
  },
  {
    id: "web-static-004",
    title: "MiroFish",
    url: "https://github.com/666ghj/MiroFish",
    snippet: "MiroFish demonstrates a console-style graph growth interface useful as a UI reference for ATANOR BakeBoard.",
    provider: "static",
    source_type: "repository_or_docs",
    license_status: "reference_only",
  },
];

const freshSearchPattern = /(\uC624\uB298|\uD604\uC7AC|\uCD5C\uC2E0|\uBC29\uAE08|\uC2E4\uC2DC\uAC04|\uC18D\uBCF4|\uB274\uC2A4|\uB0A0\uC528|\uC8FC\uAC00|\uD658\uC728|today|latest|recent|current|breaking|news|weather|stock|price)/i;
const knowledgeLookupPattern = /(\uB204\uAD6C|\uB204\uAD6C\uC57C|\uBB50\uC57C|\uBB34\uC5C7|\uC815\uC758|\uC54C\uB824\uC918|\uC124\uBA85|who is|what is|tell me about|define|explain)/i;

export function isFreshSearchQuery(query: string) {
  return freshSearchPattern.test(query);
}

export function isKnowledgeLookupQuery(query: string) {
  return knowledgeLookupPattern.test(query);
}

function selectedProvider(provider?: string | null) {
  return (provider || process.env.WEB_SEARCH_PROVIDER || "static").trim().toLowerCase();
}

function isConfigured(provider: string) {
  if (provider === "brave") return Boolean(process.env.BRAVE_SEARCH_API_KEY);
  if (provider === "serper") return Boolean(process.env.SERPER_API_KEY);
  if (provider === "tavily") return Boolean(process.env.TAVILY_API_KEY);
  if (["microsoft-grounding", "grounding-with-bing", "bing-grounding"].includes(provider)) {
    return Boolean(process.env.FOUNDRY_PROJECT_ENDPOINT && process.env.BING_PROJECT_CONNECTION_ID);
  }
  return provider === "static";
}

export function webSearchProviderStatus(provider?: string | null) {
  const selected = selectedProvider(provider);
  return {
    selected_provider: selected,
    configured: isConfigured(selected),
    raw_result_providers: {
      brave: Boolean(process.env.BRAVE_SEARCH_API_KEY),
      serper: Boolean(process.env.SERPER_API_KEY),
      tavily: Boolean(process.env.TAVILY_API_KEY),
      wikipedia: true,
      static: true,
    },
    microsoft_grounding_with_bing: {
      configured: isConfigured("microsoft-grounding"),
      mode: "foundry_agent_tool",
      native_homage_default: false,
      reason: "Grounding with Bing is an Azure Foundry Agent tool that returns model responses with citations, not raw searchable chunks for ATANOR native synthesis.",
      required_env: [
        "FOUNDRY_PROJECT_ENDPOINT",
        "FOUNDRY_MODEL_DEPLOYMENT_NAME",
        "BING_PROJECT_CONNECTION_ID",
        "AGENT_TOKEN or Azure credential",
      ],
    },
  };
}

function staticSearch(query: string, count: number): WebSearchResult[] {
  const terms = query.toLowerCase().split(/\s+/).filter((term) => term.length > 1);
  return staticResults
    .map((result) => {
      const haystack = `${result.title} ${result.snippet} ${result.url}`.toLowerCase();
      const searchScore = terms.filter((term) => haystack.includes(term)).length;
      return { ...result, search_score: searchScore };
    })
    .sort((left, right) => (right.search_score ?? 0) - (left.search_score ?? 0) || left.id.localeCompare(right.id))
    .slice(0, Math.max(1, Math.min(count, 10)));
}

function normalizeLookupQuery(query: string) {
  const cleaned = query
    .replace(/[?!.,]/g, " ")
    .replace(/(\uB204\uAD6C\uC57C|\uB204\uAD6C\uB2C8|\uB204\uAD6C|\uBB50\uC57C|\uBB34\uC5C7\uC774\uC57C|\uBB34\uC5C7|\uC54C\uB824\uC918|\uC124\uBA85\uD574\uC918|\uC18C\uAC1C\uD574\uC918|\uC815\uC758|who is|what is|tell me about|define|explain)/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
  const tokens = cleaned.split(/\s+/).filter(Boolean);
  const trimmedTokens = tokens.map((token) => token.replace(/[\uC740\uB294\uC774\uAC00\uC744\uB97C]$/u, ""));
  return trimmedTokens.join(" ").trim() || query.trim();
}

function stripTags(value: string) {
  const decoded = value
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&nbsp;/g, " ");
  return decoded
    .replace(/<[^>]+>/g, " ")
    .replace(/&quot;/g, "\"")
    .replace(/&amp;/g, "&")
    .replace(/&nbsp;/g, " ")
    .replace(/&#39;/g, "'")
    .replace(/&[a-zA-Z#0-9]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

async function wikipediaSearch(query: string, count: number): Promise<WebSearchResult[]> {
  const lookup = normalizeLookupQuery(query);
  const apiUrl = `https://ko.wikipedia.org/w/api.php?action=query&list=search&format=json&utf8=1&srlimit=${count}&srsearch=${encodeURIComponent(lookup)}`;
  const response = await fetch(apiUrl, {
    cache: "no-store",
    headers: { "User-Agent": "ATANORAlpha/0.1 web-search" },
    signal: AbortSignal.timeout(5000),
  });
  if (!response.ok) throw new Error(`Wikipedia search returned ${response.status}`);
  const body = await response.json();
  const searchItems = (body.query?.search ?? []).slice(0, count);
  const results: WebSearchResult[] = [];

  for (const [index, item] of searchItems.entries()) {
    const title = stripTags(item.title ?? lookup);
    const pageUrl = `https://ko.wikipedia.org/wiki/${encodeURIComponent(title.replace(/\s+/g, "_"))}`;
    let snippet = stripTags(item.snippet ?? "");
    let url = pageUrl;
    if (index < 2) {
      try {
        const summaryResponse = await fetch(`https://ko.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(title.replace(/\s+/g, "_"))}`, {
          cache: "no-store",
          headers: { "User-Agent": "ATANORAlpha/0.1 web-search" },
          signal: AbortSignal.timeout(5000),
        });
        if (summaryResponse.ok) {
          const summary = await summaryResponse.json();
          snippet = stripTags(summary.extract ?? snippet);
          url = summary.content_urls?.desktop?.page ?? pageUrl;
        }
      } catch {
        // Search snippets are still usable if summary lookup fails.
      }
    }
    if (title && snippet) {
      results.push({
        id: `wikipedia-${index + 1}`,
        title,
        url,
        snippet,
        provider: "wikipedia",
        source_type: "encyclopedia_search",
        license_status: "reference_only",
        search_score: count - index,
      });
    }
  }

  return results;
}

async function newsRssSearch(query: string, count: number): Promise<WebSearchResult[]> {
  const rssUrl = `https://news.google.com/rss/search?q=${encodeURIComponent(query)}&hl=ko&gl=KR&ceid=KR:ko`;
  const response = await fetch(rssUrl, {
    cache: "no-store",
    headers: { "User-Agent": "ATANORAlpha/0.1 web-search" },
    signal: AbortSignal.timeout(5000),
  });
  if (!response.ok) throw new Error(`News RSS returned ${response.status}`);
  const xml = await response.text();
  const items = [...xml.matchAll(/<item>([\s\S]*?)<\/item>/g)].slice(0, count);
  return items.map((match, index) => {
    const item = match[1];
    const title = stripTags(item.match(/<title>([\s\S]*?)<\/title>/)?.[1] ?? "News result");
    const url = stripTags(item.match(/<link>([\s\S]*?)<\/link>/)?.[1] ?? "");
    const pubDate = stripTags(item.match(/<pubDate>([\s\S]*?)<\/pubDate>/)?.[1] ?? "");
    const description = stripTags(item.match(/<description>([\s\S]*?)<\/description>/)?.[1] ?? "");
    return {
      id: `news-rss-${index + 1}`,
      title,
      url,
      snippet: pubDate ? `${pubDate} - ${description}` : description,
      provider: "news-rss",
      source_type: "news_search",
      license_status: "reference_only",
      search_score: count - index,
    };
  }).filter((item) => item.url);
}

async function braveSearch(query: string, count: number): Promise<WebSearchResult[]> {
  const response = await fetch(`https://api.search.brave.com/res/v1/web/search?q=${encodeURIComponent(query)}&count=${count}`, {
    cache: "no-store",
    headers: {
      Accept: "application/json",
      "X-Subscription-Token": process.env.BRAVE_SEARCH_API_KEY ?? "",
    },
  });
  if (!response.ok) throw new Error(`Brave Search returned ${response.status}`);
  const body = await response.json();
  return (body.web?.results ?? []).slice(0, count).map((item: any, index: number) => ({
    id: `brave-${index + 1}`,
    title: item.title ?? item.url ?? "Brave result",
    url: item.url,
    snippet: item.description ?? "",
    provider: "brave",
    source_type: "web_search",
    license_status: "reference_only",
    search_score: count - index,
  }));
}

async function serperSearch(query: string, count: number): Promise<WebSearchResult[]> {
  const response = await fetch("https://google.serper.dev/search", {
    method: "POST",
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      "X-API-KEY": process.env.SERPER_API_KEY ?? "",
    },
    body: JSON.stringify({ q: query, num: count }),
  });
  if (!response.ok) throw new Error(`Serper returned ${response.status}`);
  const body = await response.json();
  return (body.organic ?? []).slice(0, count).map((item: any, index: number) => ({
    id: `serper-${index + 1}`,
    title: item.title ?? item.link ?? "Serper result",
    url: item.link,
    snippet: item.snippet ?? "",
    provider: "serper",
    source_type: "web_search",
    license_status: "reference_only",
    search_score: count - index,
  }));
}

async function tavilySearch(query: string, count: number): Promise<WebSearchResult[]> {
  const response = await fetch("https://api.tavily.com/search", {
    method: "POST",
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      api_key: process.env.TAVILY_API_KEY,
      query,
      max_results: count,
      search_depth: "basic",
      include_answer: false,
    }),
  });
  if (!response.ok) throw new Error(`Tavily returned ${response.status}`);
  const body = await response.json();
  return (body.results ?? []).slice(0, count).map((item: any, index: number) => ({
    id: `tavily-${index + 1}`,
    title: item.title ?? item.url ?? "Tavily result",
    url: item.url,
    snippet: item.content ?? "",
    provider: "tavily",
    source_type: "web_search",
    license_status: "reference_only",
    search_score: item.score ?? count - index,
  }));
}

export async function searchWeb(query?: string | null, count = 5, provider?: string | null) {
  const cleanQuery = (query || defaultWebSearchQuery).trim() || defaultWebSearchQuery;
  const boundedCount = Math.max(1, Math.min(count, 10));
  const selected = selectedProvider(provider);
  const bingQueryUrl = `https://www.bing.com/search?q=${encodeURIComponent(cleanQuery)}`;

  if (["microsoft-grounding", "grounding-with-bing", "bing-grounding"].includes(selected)) {
    return {
      provider: "microsoft-grounding",
      query: cleanQuery,
      results: [] as WebSearchResult[],
      configured: isConfigured("microsoft-grounding"),
      bing_query_url: bingQueryUrl,
      status: "metadata_only",
      message: "Grounding with Bing is configured through Azure Foundry Agents and does not expose raw result chunks to this native ATANOR harvest path.",
      provider_status: webSearchProviderStatus(selected),
    };
  }

  try {
    const results =
      isFreshSearchQuery(cleanQuery) && (!isConfigured(selected) || selected === "static")
        ? await newsRssSearch(cleanQuery, boundedCount)
        : isKnowledgeLookupQuery(cleanQuery) && (!isConfigured(selected) || selected === "static")
        ? await wikipediaSearch(cleanQuery, boundedCount)
        : selected === "brave" && isConfigured(selected)
        ? await braveSearch(cleanQuery, boundedCount)
        : selected === "serper" && isConfigured(selected)
        ? await serperSearch(cleanQuery, boundedCount)
        : selected === "tavily" && isConfigured(selected)
        ? await tavilySearch(cleanQuery, boundedCount)
        : staticSearch(cleanQuery, boundedCount);
    return {
      provider: results[0]?.provider ?? (isConfigured(selected) ? selected : "static"),
      query: cleanQuery,
      results,
      configured: isConfigured(selected) || ["news-rss", "wikipedia"].includes(results[0]?.provider ?? ""),
      bing_query_url: bingQueryUrl,
      status: selected === "static" || isConfigured(selected) ? "ok" : "fallback_static",
      provider_status: webSearchProviderStatus(selected),
    };
  } catch (error) {
    return {
      provider: "static",
      query: cleanQuery,
      results: staticSearch(cleanQuery, boundedCount),
      configured: false,
      bing_query_url: bingQueryUrl,
      status: "provider_error_fallback_static",
      error: error instanceof Error ? error.message : "web search failed",
      provider_status: webSearchProviderStatus(selected),
    };
  }
}

export function webResultsToEvidence(results: WebSearchResult[]) {
  return results.map((result, index) => ({
    doc_id: result.id,
    chunk_id: `${result.id}#search`,
    path: result.url,
    url: result.url,
    score: Number((0.72 + Math.min(index + 1, 5) * 0.03).toFixed(3)),
    snippet: result.snippet,
    title: result.title,
    retrieval_signals: { web_search: 1, provider: result.provider },
  }));
}
