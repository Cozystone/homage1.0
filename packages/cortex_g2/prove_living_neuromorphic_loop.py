from __future__ import annotations

import json

from .proof import write_living_neuromorphic_loop_proof


def main() -> None:
    result = write_living_neuromorphic_loop_proof()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
