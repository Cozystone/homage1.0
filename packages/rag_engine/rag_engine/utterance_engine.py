from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any


def _runtime_utterance_limit(default: int = 56) -> tuple[int, str]:
    try:
        from neuro_efficiency import get_runtime_config  # type: ignore

        config = get_runtime_config()
        return int(config.utterance_max_tokens), config.inference_mode
    except Exception:
        return default, "fallback"


def _tokens(text: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    for char in text.lower():
        if char.isalnum() or char in {"-", "_"}:
            current.append(char)
        elif current:
            token = "".join(current).strip("-_")
            if token:
                tokens.append(token)
            current = []
    if current:
        token = "".join(current).strip("-_")
        if token:
            tokens.append(token)
    return [token for token in tokens if len(token) > 1 or token.isdigit()]


def _infer_intent(query: str) -> str:
    normalized = query.lower()
    if re.search(r"(why|cause|reason)", normalized):
        return "explain_cause"
    if re.search(r"(how|process|flow|step)", normalized):
        return "explain_process"
    if re.search(r"(versus|vs|compare)", normalized):
        return "compare"
    if re.search(r"(who|what|define)", normalized):
        return "define"
    return "answer_grounded"


def _node_label(node: dict[str, Any]) -> str:
    return str(node.get("label") or node.get("id") or "").strip()


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _particle_trim(token: str) -> str:
    return re.sub(r"(?|????媛|??瑜??먭쾶|?먯꽌|?쇰줈|濡??|怨???留???$", "", token)


def _seed_tokens(query: str, active_concepts: list[str]) -> list[str]:
    raw = _tokens(" ".join([query, *active_concepts]))
    seeds: list[str] = []
    for token in raw:
        trimmed = _particle_trim(token)
        if trimmed and trimmed not in seeds:
            seeds.append(trimmed)
    return seeds[:8]


def _build_transition_graph(texts: list[str]) -> tuple[dict[str, Counter[str]], Counter[str], dict[str, Counter[str]]]:
    transitions: dict[str, Counter[str]] = defaultdict(Counter)
    frequencies: Counter[str] = Counter()
    cooccurs: dict[str, Counter[str]] = defaultdict(Counter)

    for text in texts:
        tokens = _tokens(text)
        if not tokens:
            continue
        frequencies.update(tokens)
        for left, right in zip(tokens, tokens[1:]):
            transitions[left][right] += 1
        window = 6
        for index, token in enumerate(tokens):
            for neighbor in tokens[index + 1 : index + window]:
                if neighbor != token:
                    cooccurs[token][neighbor] += 1
                    cooccurs[neighbor][token] += 0.35
    return transitions, frequencies, cooccurs


def _choose_start(seeds: list[str], frequencies: Counter[str], transitions: dict[str, Counter[str]]) -> str | None:
    candidates = []
    for seed in seeds:
        if seed in transitions or seed in frequencies:
            candidates.append(seed)
    if candidates:
        candidates.sort(key=lambda token: (len(transitions.get(token, {})), frequencies[token]), reverse=True)
        return candidates[0]
    if frequencies:
        return frequencies.most_common(1)[0][0]
    return None


def _predict_tokens(
    query: str,
    evidence_docs: list[dict[str, Any]],
    active_concepts: list[str],
    graph_paths: list[list[str]],
    max_tokens: int | None = None,
) -> tuple[list[str], dict[str, Any]]:
    max_tokens, inference_mode = _runtime_utterance_limit(56 if max_tokens is None else max_tokens)
    texts = [_clean_text(doc.get("snippet") or doc.get("text")) for doc in evidence_docs]
    texts.extend(" ".join(path) for path in graph_paths if path)
    if active_concepts:
        texts.append(" ".join(active_concepts))
    transitions, frequencies, cooccurs = _build_transition_graph(texts)
    seeds = _seed_tokens(query, active_concepts)
    current = _choose_start(seeds, frequencies, transitions)
    if not current:
        return [], {
            "seeds": seeds,
            "token_count": 0,
            "edge_count": 0,
            "reason": "no_tokens",
        }

    generated = [current]
    used_edges: list[dict[str, Any]] = []
    used_edge_keys: set[tuple[str, str]] = set()
    recent: Counter[str] = Counter({current: 1})
    seed_set = set(seeds)

    for step in range(max_tokens - 1):
        options = Counter(transitions.get(current, {}))
        for neighbor, weight in cooccurs.get(current, {}).items():
            options[neighbor] += weight * 0.18
        if not options:
            bridge = _choose_start(seeds, frequencies, transitions)
            if not bridge or bridge == current:
                break
            options[bridge] += 0.35

        scored: list[tuple[float, str]] = []
        for token, weight in options.items():
            repetition_penalty = 1.0 / (1.0 + recent[token] * 1.8)
            edge_reuse_penalty = 0.15 if (current, token) in used_edge_keys else 1.0
            seed_bonus = 0.45 if token in seed_set else 0.0
            rarity = 1.0 / math.sqrt(max(1, frequencies[token]))
            score = float(weight) * repetition_penalty * edge_reuse_penalty + seed_bonus + rarity * 0.08
            scored.append((score, token))
        scored.sort(key=lambda item: (-item[0], item[1]))
        next_token = scored[0][1]
        generated.append(next_token)
        used_edge_keys.add((current, next_token))
        used_edges.append({"source": current, "target": next_token, "score": round(scored[0][0], 4), "step": step + 1})
        recent[next_token] += 1
        if recent[next_token] > 4 and step > 8:
            break
        current = next_token

    diagnostics = {
        "seeds": seeds,
        "token_count": sum(frequencies.values()),
        "unique_tokens": len(frequencies),
        "edge_count": sum(len(targets) for targets in transitions.values()),
        "graph_path_count": len(graph_paths),
        "graph_units": ["token_transition", "window_cooccurrence", "ontology_path"],
        "inference_mode": inference_mode,
        "max_tokens": max_tokens,
        "used_edges": used_edges[:24],
    }
    return generated, diagnostics


def _diagnostic_no_evidence(query: str, active_concepts: list[str], intent: str) -> str:
    clean_query = re.sub(r"\s+", " ", query.strip())
    return (
        "NO_EVIDENCE\n"
        f"query={clean_query}\n"
        f"intent={intent}\n"
        f"active_concepts={active_concepts[:6]}\n"
        "graph_token_prediction=not_enough_edges"
    )


def build_native_utterance(
    query: str,
    evidence_docs: list[dict[str, Any]],
    matched_nodes: list[dict[str, Any]],
    graph_paths: list[list[str]],
) -> dict[str, Any]:
    """Generate by graph-token prediction, not by an external LLM.

    Evidence snippets are treated as training samples for a small ontology-style
    token transition graph. The answer is the deterministic walk produced by
    that graph. If the graph is weak, the output should look weak.
    """

    intent = _infer_intent(query)
    active_concepts = [_node_label(node) for node in matched_nodes if _node_label(node)]
    if not active_concepts:
        active_concepts = [term for term, _ in Counter(_tokens(query)).most_common(4)]
    active_concepts = active_concepts[:6]

    if evidence_docs:
        predicted_tokens, diagnostics = _predict_tokens(query, evidence_docs, active_concepts, graph_paths)
        answer = " ".join(predicted_tokens) if predicted_tokens else _diagnostic_no_evidence(query, active_concepts, intent)
        answer_kind = "graph_token_prediction" if predicted_tokens else "no_evidence"
        mode = "ontology-graph-token-prediction-alpha" if predicted_tokens else "no-evidence-diagnostic-alpha"
    else:
        diagnostics = {"seeds": _seed_tokens(query, active_concepts), "token_count": 0, "edge_count": 0}
        answer = _diagnostic_no_evidence(query, active_concepts, intent)
        answer_kind = "no_evidence"
        mode = "no-evidence-diagnostic-alpha"

    return {
        "answer": answer,
        "pmv": {
            "intent": intent,
            "topic": active_concepts[0] if active_concepts else query,
            "stance": "experimental_generation_not_authoritative",
            "audience_level": "research",
            "answer_goal": "predict token sequence from ontology/token graph connectivity",
            "required_evidence": True,
            "style": "raw_graph_token_prediction",
        },
        "claim_plan": [],
        "active_concepts": active_concepts,
        "answer_kind": answer_kind,
        "answer_engine": {
            "name": "ATANOR Graph Token Predictor",
            "mode": mode,
            "external_llm": False,
            "homage_core": "homage-core-30m-scaffold",
            "prediction_basis": "ontology_token_transition_graph",
            "surface_generation": "graph_walk",
            "template_free_surface": True,
            "stages": [
                "tokenize_evidence",
                "build_transition_edges",
                "score_connected_tokens",
                "predict_next_token_sequence",
            ],
            "diagnostics": diagnostics,
        },
    }
