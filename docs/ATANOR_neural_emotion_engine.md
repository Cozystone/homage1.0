# ATANOR Neural Emotion Engine v0

Status: proof-only local state-control layer.

Neural Emotion Engine v0 gives ATANOR a deterministic vector that can shape surface behavior without claiming real emotion, consciousness, or AGI completion. It does not generate answers. It does not call an LLM or sLLM. It does not write Local Brain, mutate `verified_store_v0`, promote candidates, execute shell commands, or change autonomy tiers.

## State Vector

The engine tracks six bounded dimensions:

- `valence`: negative to positive bias, range `-1..1`
- `arousal`: calm to activated bias, range `-1..1`
- `curiosity`: exploration pressure, range `0..1`
- `caution`: safety and review pressure, range `0..1`
- `fatigue`: rest pressure, range `0..1`
- `speaking_energy`: active speech visualization pressure, range `0..1`

Events such as `greeting`, `unsafe_request`, `novelty_found`, `tool_failure`, `approval_granted`, `resting`, and `speaking_start` apply small deterministic deltas. Decay returns the vector toward the personality baseline.

## Safety Contract

Every snapshot carries these invariants:

- `external_llm=false`
- `external_sllm=false`
- `real_emotion_claim=false`
- `consciousness_claim=false`
- `local_brain_write=false`
- `production_store_mutated=false`
- `candidate_promotion=false`
- `unrestricted_shell=false`
- `arbitrary_js_eval=false`
- `auto_commit=false`
- `auto_push=false`
- `proof_only=true`

The engine is allowed to influence style controls only. It is not allowed to bypass permission gates or perform mutation.

## Proof Scenarios

`python -m packages.neural_emotion.proof` checks:

- greeting raises valence
- unsafe request raises caution and arousal
- novelty raises curiosity
- repeated failure raises fatigue and caution
- decay moves state toward baseline
- surface controls are bounded
- SPLATRA controls are bounded
- voice controls are bounded
- agentic controls never bypass permission gates
- no real emotion or consciousness claim appears in safety flags

The proof runner writes JSON under `data/neural_emotion/proofs/`. Those files are runtime proof artifacts and must not be staged.
