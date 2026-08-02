# ATANOR Open-Web Explorer Loop v1

Status: proof-only bounded open-web exploration.

The Hermes-style explorer can now operate without a fixed domain allowlist. It
may discover public links and draft Cloud Brain candidates, but every action is
bounded by URL safety policy, rate budgets, and proof-only mutation gates.

## Allowed

- Public `http` and `https` pages.
- Bounded HTML GETs.
- Dynamic link discovery.
- Local deterministic title/excerpt/hash/summary/claim/tag extraction.
- Cloud Brain candidate drafts through Brain Access Road.
- SkillDraft creation with `promotion_required=true`.

## Denied

- `localhost`, `.local`, private IPs, link-local, multicast, and reserved IPs.
- `file://`, `chrome://`, and other private schemes.
- Login, sign-in, account, auth, token, secret, upload, payment, billing,
  checkout, cart, and admin paths.
- Download-like URLs and model/audio/binary artifacts.
- Forms, uploads, purchases, account creation, comments, emails, or downloads.
- Local Brain direct writes.
- Production `verified_store_v0` mutation.
- Candidate promotion.
- Auto commit or push.
- External LLM or sLLM calls.

## Default Budgets

- `max_pages=300`
- `max_depth=3`
- `max_runtime_sec=21600`
- `max_bytes_per_page=250000`
- `per_domain_delay_sec=3`
- `max_pages_per_domain=50`
- `max_candidate_drafts=200`
- `max_skill_drafts=50`

The CLI defaults to a fixture proof path unless `--open-web --live-web` is
explicitly passed. This prevents accidental long crawling during tests.

## API

- `GET /api/agentic-os/web-explorer/open/status`
- `POST /api/agentic-os/web-explorer/open/run`
- `GET /api/agentic-os/web-explorer/open/runs/{run_id}`

## Candidate Draft Fields

Each useful page produces draft-only records with:

- `source_url`
- `title`
- `content_hash`
- `excerpt`
- `summary`
- `claims`
- `confidence`
- `tags`
- `candidate_status=draft`

No production write or promotion is performed.

## Current Limitations

- Robots.txt handling is not yet a full production crawler implementation.
- Live-web mode is intentionally opt-in and should be run only with explicit
  operator approval.
- Page parsing is simple HTML text extraction, not semantic understanding.
- Autonomous reporting is trigger-based, not mandatory.
