"""Fresh-process worker for the preregistered Pattern #5 capability run.

The controller owns labels and scoring.  This worker sees only opaque case
identifiers plus the web rows needed by the production answer surface.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import socket
import sys
import types
import urllib.request
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
CANDIDATE_PATH = REPO / "apps" / "api" / "app" / "services" / "web_search.py"
OFF_COMMIT = "bc5cccde42080a784f490ebbb53414cf7ec45131"
ON_COMMIT = "e94d1c1e934554fad7ed4cb54a0d0fcdccb6ff0a"
OFF_GIT_BLOB_SHA256 = (
    "cca015ab8e4f39bbdff60c7533b68cd992941e93fd7fee219a53d6a89c75ef8d"
)
OFF_PREREG_CRLF_SHA256 = (
    "3e18f1461b046bd642102e328d61ca50782ec3eff219c1876b7716881d4dfda2"
)
ON_GIT_BLOB_SHA256 = (
    "c9385021fb047a05ff0156849a631274885785bae1a8de53c32850095c19a386"
)
REFERENT_RESONANCE_SHA256 = (
    "86b0d8aebb0ef96db3050d14e6576e4136030db9d32ea94eb1d6de1f217bee3b"
)
REQUEST_SCHEMA = "atanor.pattern-05-web-authority-worker-request.v1"
RESULT_SCHEMA = "atanor.pattern-05-web-authority-worker-result.v1"
_REQUEST_FIELDS = frozenset(
    {"schema_version", "block_id", "condition", "order", "items"}
)
_ITEM_FIELDS = frozenset(
    {"opaque_item_id", "query", "language", "row"}
)


class WorkerContractError(RuntimeError):
    """Raised when a sealed worker input or candidate identity drifts."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _strict_object(payload: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkerContractError(f"{label} is not strict UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise WorkerContractError(f"{label} must be an object")
    return value


def _source_for(condition: str, root: Path) -> tuple[bytes, str]:
    roots = {
        "OFF": (OFF_COMMIT, OFF_GIT_BLOB_SHA256),
        "ON": (ON_COMMIT, ON_GIT_BLOB_SHA256),
    }
    try:
        _commit, expected_sha256 = roots[condition]
    except KeyError as exc:
        raise WorkerContractError("condition must be OFF or ON") from exc
    try:
        source = (
            root / "apps" / "api" / "app" / "services" / "web_search.py"
        ).read_bytes()
    except OSError as exc:
        raise WorkerContractError(f"{condition} isolated candidate is unavailable") from exc
    if _sha256(source) != expected_sha256:
        raise WorkerContractError(f"{condition} candidate git blob digest drift")
    if (
        condition == "OFF"
        and _sha256(source.replace(b"\n", b"\r\n"))
        != OFF_PREREG_CRLF_SHA256
    ):
        raise WorkerContractError("OFF candidate no longer matches preregistration")
    return source, expected_sha256


def _prepare_isolated_runtime(root: Path) -> dict[str, int]:
    try:
        resolved_root = root.resolve(strict=True)
    except OSError as exc:
        raise WorkerContractError("isolated root does not exist") from exc
    required = (
        resolved_root / "apps" / "api" / "app" / "services" / "web_search.py",
        resolved_root / "packages" / "cgsr" / "cgsr" / "referent_resonance.py",
    )
    if not all(path.is_file() for path in required):
        raise WorkerContractError("isolated root is incomplete")
    repo_root = REPO.resolve()
    retained: list[str] = []
    for value in sys.path:
        if not value:
            continue
        try:
            Path(value).resolve().relative_to(repo_root)
        except ValueError:
            retained.append(value)
        except OSError:
            continue
    sys.path[:] = [
        str(resolved_root / "apps" / "api"),
        str(resolved_root),
        *retained,
    ]
    os.chdir(resolved_root)
    sensitive_exact = {
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "BRAVE_API_KEY",
        "SERPER_API_KEY",
        "TAVILY_API_KEY",
        "FIRECRAWL_API_KEY",
        "WEB_SEARCH_PROVIDER",
        "WEB_SEARCH_API_KEY",
    }
    for key in list(os.environ):
        upper = key.upper()
        if (
            upper in sensitive_exact
            or upper.startswith("ATANOR_")
            or upper.startswith("WEB_SEARCH_")
            or upper.endswith("_API_KEY")
            or upper.endswith("_AUTH_TOKEN")
        ):
            os.environ.pop(key, None)

    network = {"attempt_count": 0}

    def _network_denied(*_args: Any, **_kwargs: Any) -> Any:
        network["attempt_count"] += 1
        raise WorkerContractError("network access is prohibited in Pattern #5 evaluation")

    urllib.request.urlopen = _network_denied
    socket.create_connection = _network_denied
    socket.socket.connect = _network_denied
    return network


def _load_candidate(condition: str, root: Path) -> tuple[types.ModuleType, str]:
    source, source_sha256 = _source_for(condition, root)
    module = types.ModuleType(f"_atanor_pattern05_{condition.lower()}")
    module.__file__ = str(
        root / "apps" / "api" / "app" / "services" / "web_search.py"
    )
    module.__package__ = "app.services"
    sys.modules[module.__name__] = module
    try:
        exec(
            compile(source.decode("utf-8"), module.__file__, "exec"),
            module.__dict__,
        )
    except Exception as exc:
        sys.modules.pop(module.__name__, None)
        raise WorkerContractError(
            f"{condition} candidate failed to load: {type(exc).__name__}: {exc}"
        ) from exc
    if not callable(getattr(module, "compose_web_answer", None)):
        raise WorkerContractError(f"{condition} candidate lacks compose_web_answer")
    return module, source_sha256


def _validate_request(value: dict[str, Any]) -> None:
    if frozenset(value) != _REQUEST_FIELDS:
        raise WorkerContractError("worker request fields mismatch")
    if value.get("schema_version") != REQUEST_SCHEMA:
        raise WorkerContractError("worker request schema mismatch")
    if value.get("condition") not in {"OFF", "ON"}:
        raise WorkerContractError("worker request condition invalid")
    if value.get("order") not in {"forward", "reverse"}:
        raise WorkerContractError("worker request order invalid")
    if not isinstance(value.get("block_id"), str) or not value["block_id"]:
        raise WorkerContractError("worker request block_id invalid")
    items = value.get("items")
    if not isinstance(items, list) or not items:
        raise WorkerContractError("worker request items invalid")
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or frozenset(item) != _ITEM_FIELDS:
            raise WorkerContractError("worker item fields mismatch")
        opaque = item.get("opaque_item_id")
        if (
            not isinstance(opaque, str)
            or len(opaque) != 64
            or any(ch not in "0123456789abcdef" for ch in opaque)
            or opaque in seen
        ):
            raise WorkerContractError("worker opaque item identity invalid")
        if (
            not isinstance(item.get("query"), str)
            or not item["query"].strip()
            or item.get("language") not in {"en", "ko"}
            or not isinstance(item.get("row"), dict)
        ):
            raise WorkerContractError("worker item payload invalid")
        seen.add(opaque)


def _repo_module_receipt(root: Path) -> list[dict[str, str]]:
    isolated_root = root.resolve(strict=True)
    current_repo = REPO.resolve()
    receipts: list[dict[str, str]] = []
    for module_name, module in sorted(sys.modules.items()):
        origin = getattr(module, "__file__", None)
        if not isinstance(origin, str):
            continue
        try:
            path = Path(origin).resolve(strict=True)
        except OSError:
            continue
        try:
            relative = path.relative_to(isolated_root).as_posix()
        except ValueError:
            try:
                current_relative = path.relative_to(current_repo).as_posix()
            except ValueError:
                continue
            if module_name == "__main__" and current_relative == (
                "scripts/pattern_05_web_authority_capability_worker.py"
            ):
                continue
            raise WorkerContractError(
                f"repo-local module escaped isolated root: {module_name}"
            )
        if path.suffix not in {".py", ".pyc"}:
            continue
        source_path = path
        if path.suffix == ".pyc":
            try:
                candidate = Path(importlib.util.source_from_cache(str(path)))
            except ValueError:
                candidate = path
            if candidate.is_file():
                source_path = candidate
                relative = source_path.relative_to(isolated_root).as_posix()
        receipts.append(
            {
                "module": module_name,
                "relative_path": relative,
                "raw_sha256": _sha256(source_path.read_bytes()),
            }
        )
    if not any(
        receipt["relative_path"]
        == "packages/cgsr/cgsr/referent_resonance.py"
        and receipt["raw_sha256"] == REFERENT_RESONANCE_SHA256
        for receipt in receipts
    ):
        raise WorkerContractError("referent_resonance identity drift")
    return receipts


def evaluate(request: dict[str, Any], root: Path) -> dict[str, Any]:
    _validate_request(request)
    condition = str(request["condition"])
    network = _prepare_isolated_runtime(root)
    module, source_sha256 = _load_candidate(condition, root)
    hedge_en = str(getattr(module, "_WEB_HEDGE_EN", ""))
    hedge_ko = str(getattr(module, "_WEB_HEDGE_KO", ""))
    rows: list[dict[str, Any]] = []
    for item in request["items"]:
        error = None
        result: dict[str, Any] | None = None
        try:
            candidate = module.compose_web_answer(
                item["query"],
                [dict(item["row"])],
                language=item["language"],
            )
            if candidate is not None and not isinstance(candidate, dict):
                raise WorkerContractError("compose_web_answer returned a non-object")
            result = candidate
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[-1000:]
        verification = (
            result.get("verification")
            if isinstance(result, dict) and isinstance(result.get("verification"), dict)
            else {}
        )
        answer = str((result or {}).get("answer") or "")
        hedge = hedge_ko if item["language"] == "ko" else hedge_en
        rows.append(
            {
                "opaque_item_id": item["opaque_item_id"],
                "condition": condition,
                "answer": answer,
                "answer_sha256": _sha256(answer.encode("utf-8")),
                "answer_nonempty": bool(answer.strip()),
                "authoritative": verification.get("authoritative") is True,
                "tier": str(verification.get("tier") or ""),
                "answer_kind": str((result or {}).get("answer_kind") or ""),
                "hedged": bool(hedge) and answer.startswith(hedge),
                "n_sources": int(verification.get("n_sources") or 0),
                "error": error,
            }
        )
    return {
        "schema_version": RESULT_SCHEMA,
        "block_id": request["block_id"],
        "condition": condition,
        "order": request["order"],
        "candidate_source_sha256": source_sha256,
        "repo_module_receipts": _repo_module_receipt(root),
        "network_policy": "denied",
        "network_attempt_count": network["attempt_count"],
        "environment_policy": "provider_and_api_credentials_removed",
        "items": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        request = _strict_object(sys.stdin.buffer.read(), "worker request")
        result = evaluate(request, args.root)
        sys.stdout.write(
            json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        )
        return 0
    except Exception as exc:
        sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
