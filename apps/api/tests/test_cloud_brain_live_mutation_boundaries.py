"""Static contracts for live mutation routes that must fail before work begins.

Importing ``cloud_brain`` starts a large application dependency surface.  These
tests deliberately inspect the checked-in source instead: the safety property
is that the route helpers are literal refusal leaves, with no call expression
that could build or install a candidate before returning.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
SOURCE_PATH = REPO / "apps" / "api" / "app" / "routers" / "cloud_brain.py"


def _source_and_tree() -> tuple[str, ast.Module]:
    source = SOURCE_PATH.read_text(encoding="utf-8")
    return source, ast.parse(source, filename=str(SOURCE_PATH))


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    matches = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    assert len(matches) == 1
    return matches[0]


def _return_dict(function: ast.FunctionDef) -> ast.Dict:
    returns = [node for node in function.body if isinstance(node, ast.Return)]
    assert len(returns) == 1
    value = returns[0].value
    assert isinstance(value, ast.Dict)
    return value


def _literal_fields(mapping: ast.Dict, *, omit: set[str] | None = None) -> dict[str, object]:
    omitted = omit or set()
    result: dict[str, object] = {}
    for key_node, value_node in zip(mapping.keys, mapping.values, strict=True):
        key = ast.literal_eval(key_node)
        if key not in omitted:
            result[key] = ast.literal_eval(value_node)
    return result


def _meaningful_body(function: ast.FunctionDef) -> list[ast.stmt]:
    body = list(function.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body.pop(0)
    return body


def _call_name(call: ast.Call) -> str:
    def expression_name(expression: ast.expr) -> str:
        if isinstance(expression, ast.Name):
            return expression.id
        if isinstance(expression, ast.Attribute):
            return f"{expression_name(expression.value)}.{expression.attr}"
        return "<dynamic>"

    return expression_name(call.func)


def _try_containing(source: str, function: ast.FunctionDef, marker: str) -> ast.Try:
    matches = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Try)
        and marker in (ast.get_source_segment(source, node) or "")
    ]
    assert len(matches) == 1
    return matches[0]


def test_answer_pack_promotion_is_a_call_free_refusal_leaf() -> None:
    source, tree = _source_and_tree()
    function = _function(tree, "_maybe_promote_pack")
    result = _literal_fields(_return_dict(function), omit={"force_requested"})

    assert [type(node) for node in _meaningful_body(function)] == [ast.Return]
    assert not any(
        isinstance(
            node,
            (
                ast.Call,
                ast.Import,
                ast.ImportFrom,
                ast.Global,
                ast.Nonlocal,
                ast.Delete,
                ast.With,
                ast.Try,
                ast.Raise,
                ast.AugAssign,
                ast.AnnAssign,
            ),
        )
        for node in ast.walk(function)
    )
    assert result["promoted"] is False
    assert result["applied"] is False
    assert result["reason"] == "signed_answer_pack_promotion_not_wired"
    assert result["required_evidence"] == [
        "candidate_source_digest",
        "external_evaluator_receipt",
        "operator_signature",
        "canary_and_rollback",
    ]
    assert 'os.getenv("ATANOR_PROMOTE_EVERY", "0")' in source
    assert "promote_graph_to_pack" not in source


def test_live_derivation_is_a_call_free_precompute_refusal_leaf() -> None:
    _, tree = _source_and_tree()
    function = _function(tree, "_run_derivation")
    result = _literal_fields(_return_dict(function))

    assert [type(node) for node in _meaningful_body(function)] == [ast.Assign, ast.Return]
    assert not any(
        isinstance(
            node,
            (
                ast.Call,
                ast.Import,
                ast.ImportFrom,
                ast.Global,
                ast.Nonlocal,
                ast.Delete,
                ast.With,
                ast.Try,
                ast.Raise,
                ast.AugAssign,
                ast.AnnAssign,
            ),
        )
        for node in ast.walk(function)
    )
    assert result == {
        "derived": 0,
        "applied": False,
        "computed": False,
        "error": "signed_graph_mutation_batch_required",
        "required_stage": "proposed",
    }


def test_public_promotion_route_has_no_alternate_install_path() -> None:
    _, tree = _source_and_tree()
    route = _function(tree, "cloud_brain_promote_pack")
    body = _meaningful_body(route)

    assert len(body) == 1 and isinstance(body[0], ast.Return)
    returned = body[0].value
    assert isinstance(returned, ast.Call)
    assert _call_name(returned) == "_maybe_promote_pack"
    assert returned.args == []
    assert len(returned.keywords) == 1
    assert returned.keywords[0].arg == "force"
    assert isinstance(returned.keywords[0].value, ast.Constant)
    assert returned.keywords[0].value.value is True


def test_continuous_worker_promotion_and_derivation_refuse_before_heavy_work() -> None:
    source, tree = _source_and_tree()
    worker = _function(tree, "_continuous_worker")
    promotion = _try_containing(source, worker, "ATANOR_PROMOTE_EVERY")
    derivation = _try_containing(source, worker, "ATANOR_DERIVE_EVERY")

    promotion_calls = [_call_name(node) for node in ast.walk(promotion) if isinstance(node, ast.Call)]
    derivation_calls = [_call_name(node) for node in ast.walk(derivation) if isinstance(node, ast.Call)]
    assert set(promotion_calls) <= {
        "int",
        "os.getenv",
        "_CONT.get",
        "_maybe_promote_pack",
        "type",
    }
    assert set(derivation_calls) <= {
        "int",
        "os.getenv",
        "_CONT.get",
        "_run_derivation",
        "_dres.get",
        "_time.time",
        "type",
    }
    assert promotion_calls.count("_maybe_promote_pack") == 1
    assert derivation_calls.count("_run_derivation") == 1
    assert not any(
        isinstance(node, (ast.Import, ast.ImportFrom)) for node in ast.walk(derivation)
    )

    promotion_source = ast.get_source_segment(source, promotion) or ""
    derivation_source = ast.get_source_segment(source, derivation) or ""
    assert 'os.getenv("ATANOR_PROMOTE_EVERY", "0")' in promotion_source
    assert 'os.getenv("ATANOR_DERIVE_EVERY", "0")' in derivation_source
    for forbidden in (
        "promote_graph_to_pack",
        "pack_builder",
        "derivation_accelerator",
        "derive_transitive_closure",
        "TripleStore",
        "answer_bridge",
        "_astore",
        "len(",
    ):
        assert forbidden not in promotion_source
        assert forbidden not in derivation_source
