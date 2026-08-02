from __future__ import annotations

import json

from .cloud_node_attachment import cleanup_expired_bundles


def main() -> None:
    print(json.dumps(cleanup_expired_bundles(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
