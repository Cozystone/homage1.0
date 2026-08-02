# Web Search Connectors

ATANOR uses web search as a Harvest evidence source, not as an external answer
LLM. Search results are converted into evidence snippets and then read by the
native ATANOR GraphRAG/Utterance flow.

## Provider Modes

- `static`: deterministic fallback; no key required.
- `brave`: raw web result provider, requires `BRAVE_SEARCH_API_KEY`.
- `serper`: raw web result provider, requires `SERPER_API_KEY`.
- `tavily`: raw web result provider, requires `TAVILY_API_KEY`.
- `microsoft-grounding`: metadata/status only in native ATANOR mode.

## Microsoft Grounding With Bing

Microsoft's current recommendation is Grounding with Bing Search through Azure
AI Foundry Agents. The older Bing Search APIs are retired as of August 11,
2025. Grounding with Bing works as an agent tool: it performs query formulation,
search execution, synthesis, and citation output inside the Foundry Agent run.

That is useful for a future optional Foundry-agent mode, but it is not the
default ATANOR native path because ATANOR currently avoids external LLM answer
generation and wants raw evidence chunks for its own RAG/ontology pipeline.

Expected environment variables for a future Foundry mode:

- `FOUNDRY_PROJECT_ENDPOINT`
- `FOUNDRY_MODEL_DEPLOYMENT_NAME`
- `BING_PROJECT_CONNECTION_ID`
- `AGENT_TOKEN` or Azure credentials

## Implemented API Surface

- `GET /api/harvest/web-search/status`
- `POST /api/harvest/web-search`
- `POST /api/factory/build/start` accepts `web_search`, `search_query`, and
  `web_search_provider`.
- `POST /api/graphrag/query` accepts `web_search` and `web_search_provider`.

## Safety Notes

- Search APIs are optional and disabled unless env vars are configured.
- The static fallback is deterministic and does not call the network.
- ATANOR records URLs and snippets as reference-only evidence.
- The app does not perform unrestricted crawling; Build Start samples a bounded
  search/reference set.
