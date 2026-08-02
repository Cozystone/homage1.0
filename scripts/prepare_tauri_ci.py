from __future__ import annotations

import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "src-tauri" / "tauri.conf.json"


def main() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    has_signing_key = bool(os.getenv("TAURI_SIGNING_PRIVATE_KEY"))
    if not has_signing_key:
        bundle = config.setdefault("bundle", {})
        bundle["createUpdaterArtifacts"] = False
        CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(
            "TAURI_SIGNING_PRIVATE_KEY is not set; disabled updater artifact generation "
            "but kept updater runtime config so the desktop app can initialize."
        )
    else:
        print("TAURI_SIGNING_PRIVATE_KEY is set; updater artifact generation remains enabled.")


if __name__ == "__main__":
    main()
