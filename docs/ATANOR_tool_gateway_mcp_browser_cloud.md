# ATANOR Tool Gateway: MCP, Browser, API, Cloud

The Tool Gateway is Hermes-inspired but ATANOR-native. V0 uses mocked connectors
to prove schema and safety.

## Browser

Browser read is allowlisted. No credentialed private pages, form submission,
downloads, or side effects are enabled in v0.

## External API

External API read is allowlisted and rejects private payloads. External LLM,
sLLM, and TTS APIs are not part of the core path.

## MCP

MCP calls require a descriptor allowlist and capability token. Unknown tools and
tool-poisoning surfaces are rejected. Local Brain raw payloads are stripped or
rejected.

## Cloud

Cloud verified reads and candidate drafts are routed through Brain Access Road.
Production mutation and candidate promotion remain blocked.
