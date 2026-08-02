"""Strict command-line gate for the checked-in architecture registry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .registry import RegistryValidationError, format_summary, load_and_validate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--catalog",
        type=Path,
        default=None,
        help="Catalog path (defaults to data/architecture/catalog/organ_registry_v1.json)",
    )
    parser.add_argument("--json", action="store_true", help="Emit a JSON status record")
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[2]
    catalog_path = args.catalog or (
        repo / "data" / "architecture" / "catalog" / "organ_registry_v1.json"
    )
    try:
        catalog = load_and_validate(
            catalog_path,
            package_root=repo / "packages",
            repo_root=repo,
        )
    except RegistryValidationError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        else:
            print(f"organ registry invalid:\n{exc}")
        return 2

    if args.json:
        print(json.dumps({"ok": True, "organ_count": len(catalog["organs"])}, indent=2))
    else:
        print(format_summary(catalog))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
