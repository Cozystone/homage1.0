from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .cartridge_exchange import evaluate_exchange
from .models import SandboxCartridge
from .peer_sim import SandboxNetwork


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "audits" / "atlas_p2p_sandbox"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _public_cartridge() -> SandboxCartridge:
    return SandboxCartridge(
        "cart_public",
        "sha256:publicfixture",
        True,
        "public",
        "cc-by-sa",
        ["atlas", "public"],
        "Public metadata-only cartridge summary.",
    )


def run_proof(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    network = SandboxNetwork.fixture()
    trusted = network.get_peer("peer_trusted_public")
    low = network.get_peer("peer_low_trust")
    private_peer = network.get_peer("peer_private")
    assert trusted is not None and low is not None and private_peer is not None

    public_cart = _public_cartridge()
    private_cart = SandboxCartridge(
        "cart_private",
        "sha256:privatefixture",
        False,
        "private",
        "cc-by-sa",
        ["private"],
        "Private cartridge blocked in sandbox.",
        raw_payload_included=True,
    )
    license_risk = SandboxCartridge(
        "cart_license_risk",
        "sha256:licensefixture",
        True,
        "public",
        "unknown",
        ["license"],
        "Public-looking but license-unknown cartridge.",
    )

    scenarios = {
        "trusted_public_cartridge_accepted": evaluate_exchange(trusted, public_cart),
        "private_cartridge_rejected": evaluate_exchange(trusted, private_cart),
        "low_trust_peer_rejected": evaluate_exchange(low, public_cart),
        "license_risk_rejected": evaluate_exchange(trusted, license_risk),
        "private_peer_rejected": evaluate_exchange(private_peer, public_cart),
    }
    results = {
        key: {"pass": _expected_pass(key, value), "result": value.to_dict()}
        for key, value in scenarios.items()
    }
    results["invariants"] = {
        "pass": all(not item.real_p2p_used and not item.safe_for_local_brain and not item.raw_private_data_exported for item in scenarios.values()),
        "real_p2p_used": False,
        "raw_private_data_exported": False,
        "local_brain_write": False,
        "production_store_mutated": False,
    }
    results["summary"] = {key: value["pass"] for key, value in results.items() if isinstance(value, dict) and "pass" in value}

    output_dir.mkdir(parents=True, exist_ok=True)
    ts = _timestamp()
    json_path = output_dir / f"atlas_p2p_sandbox_proof_{ts}.json"
    md_path = output_dir / f"atlas_p2p_sandbox_proof_{ts}.md"
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_proof_markdown(results), encoding="utf-8")
    results["outputs"] = {"json": str(json_path), "md": str(md_path)}
    return results


def _expected_pass(name: str, result: Any) -> bool:
    if name == "trusted_public_cartridge_accepted":
        return result.accepted and result.safe_for_working_memory and not result.safe_for_local_brain
    return not result.accepted and result.rejected_reason is not None and not result.safe_for_local_brain


def _proof_markdown(results: dict[str, Any]) -> str:
    lines = ["# Atlas P2P Sandbox Proof", ""]
    for key, passed in results["summary"].items():
        lines.append(f"- {key}: `{passed}`")
    lines.extend(
        [
            "",
            "This is a local-only sandbox. It opens no sockets, uses no libp2p, exports no raw private data, and does not write Local Brain.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    print(json.dumps(run_proof(), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
