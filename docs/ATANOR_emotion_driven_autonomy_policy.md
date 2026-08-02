# ATANOR Emotion-driven Autonomy Policy v1

Status: proof-only.

Emotion-driven Autonomy Policy v1 maps ATANOR's bounded local Neural Emotion Engine state into suggested operating controls. It does not claim real emotion, consciousness, AGI, or operator authority.

## What It Can Suggest

- Web explorer budget multiplier, max pages delta, and runtime delta.
- Review strictness and skill draft threshold.
- SPLATRA archetype switch rate and particle budget hint.
- ASM-v0 brevity and caution bias.
- Voice fallback emphasis when audio is unavailable.
- Agent loop throttle, rest suggestion, and review request suggestion.

## Non-Negotiable Limits

- It never changes autonomy tier automatically.
- It never bypasses Permission Gate.
- It never writes Local Brain.
- It never mutates production Cloud Brain stores.
- It never promotes candidates.
- It never commits, pushes, or executes unrestricted host actions.
- It never uses external LLM/sLLM APIs.

The policy output is a suggestion surface only. Existing gates remain authoritative.

## Runtime Interpretation

Curiosity can raise exploration budget. Caution and unsafe-request context raise review strictness. Fatigue and repeated failures reduce loop budget and can request rest. Voice unavailability only increases fallback emphasis; it never claims that audio is available.

## API Surface

- `GET /api/neural-emotion/policy/current`
- `POST /api/neural-emotion/policy/evaluate`
- `POST /api/neural-emotion/policy/apply-preview`

`apply-preview` never applies mutations. It returns the proposed controls plus explicit invariants such as `mutation_performed=false`, `permission_gate_bypass=false`, and `autonomy_tier_auto_changed=false`.

## Product Visibility

Lab mode can show raw policy internals for inspection. Product mode receives a small public summary and hides raw vectors, thresholds, and control internals.
