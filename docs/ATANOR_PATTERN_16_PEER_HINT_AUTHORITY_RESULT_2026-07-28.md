# Pattern #16 — Unsigned peer hints used by the network resolver

## Outcome

- Outcome: `fixed`
- Mechanism: `GREEN`
- Capability: `NOT_MEASURED` — this closes an authority boundary; it does not
  establish answer-quality lift.

## 0-stage prior-attempt audit

`git stash list`, `git branch --list`, and `git log --all --grep` searches for
`#16`, `hybrid_network`, `unsigned peer hints`, `resolve-only`, and `peer hint`
found no prior RED/WIP remediation. The existing stash does not contain the
target paths, and path history contains only the original hybrid-network
features.

## Revalidated path and invariant

`HybridNetworkManager.resolve_cloud_knowledge()` accepted a discovered
`PeerHint`, fetched a `GraphFragmentEnvelope`, and persisted it into the
resolver response after only the envelope's caller-recomputable SHA-256 check
when no signing key was configured. Even with a configured signing key, the
signed envelope's `source_peer_id` and `concept_ids` were not bound back to
the hint used for routing. A hint plus matching unsigned fragment could
therefore mint fragment authority, and a forged hint could relabel a
legitimately signed fragment.

The invariant is: a peer hint is a routing proposal only. A fragment returned
by the public resolver is accepted only when an independently configured
verifier authenticates the envelope and the authenticated peer and concept
are bound to the proposed route.

## Pre-fix reproduction

`python -m pytest -q apps/api/tests/test_hybrid_network_manager.py -k "unsigned_peer_hint or authority_and_hint or relabelled"`

Result before fix: `2 failed, 1 passed`. A matching unsigned hint/fragment pair
was returned as `completed`, and a forged peer hint successfully relabelled a
signed fragment from a different peer. The legitimate signed and bound control
already passed.

## Minimal fix

- The resolve path now fails closed when no fragment signature verifier is
  configured.
- This intentionally changes the default resolver from accepting unsigned
  fixtures to disabling remote-fragment adoption. The public status surface
  now reports `remote_fragment_adoption_enabled=false` and
  `disabled_missing_signature_verifier` instead of presenting that default as
  usable.
- The existing envelope signature verifier remains the independent authority;
  caller-recomputable SHA-256 is integrity metadata only.
- After signature verification, `source_peer_id` must match the hint's
  `peer_id`, and the signed `concept_ids` must contain the hint's
  `concept_id`.
- Existing legitimate resolver tests now use explicitly signed fixtures. The
  direct envelope parsing API remains unchanged. A legitimate remote-fragment
  control requires an operator-provided `ATANOR_FRAGMENT_SIGNING_KEY` (legacy
  alias `HOMAGE_FRAGMENT_SIGNING_KEY`); the secret itself is never exposed by
  status.

Changed files:

- `apps/api/app/services/hybrid_network_manager.py`
- `apps/api/app/services/network_config.py`
- `apps/api/tests/test_hybrid_network_manager.py`
- `docs/ATANOR_PATTERN_16_PEER_HINT_AUTHORITY_RESULT_2026-07-28.md`

## Verification

- Forged caller, signed legitimate control, peer-binding attack, and existing
  resolver regressions:
  `python -m pytest -q apps/api/tests/test_hybrid_network_manager.py`
  — `11 passed`. The adversarial controls separately seal unsigned authority,
  signed-peer relabelling, and signed-concept retargeting.
- Syntax/buildability:
  `python -m compileall -q apps/api/app/services/hybrid_network_manager.py apps/api/tests/test_hybrid_network_manager.py`
  — passed.
- Patch hygiene:
  `git diff --check -- apps/api/app/services/hybrid_network_manager.py apps/api/tests/test_hybrid_network_manager.py docs/ATANOR_PATTERN_16_PEER_HINT_AUTHORITY_RESULT_2026-07-28.md`
  — passed apart from any repository line-ending warning.

The original issue no longer reproduces. A forged matching unsigned
hint/fragment pair yields a degraded result with zero fragments; a signed
fragment offered under another peer's hint is rejected; and a correctly
signed, peer-bound, concept-bound fragment is still accepted.

The shipped default is deliberately fail-closed: without a configured
verifier, discovery and transport attempts may still be diagnostic, but no
remote fragment can be adopted. This is a production-OFF state rather than a
capability-ready network path.

## Remaining boundary

This result makes the `/api/network/resolve` adoption boundary fail closed.
Peer hints remain discovery metadata and can still influence which transport
endpoint is attempted before the returned payload is rejected. Endpoint
allowlisting/SSRF policy and peer-specific asymmetric key distribution are
separate boundaries and were not expanded into this finding.

Actual WAN exposure remains deployment-dependent. Production defaults remain
OFF/local-first, and this change does not enable server signaling or payload
fallback that was previously disabled.
