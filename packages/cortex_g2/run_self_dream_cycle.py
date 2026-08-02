from __future__ import annotations

import argparse
import json

from .dream_loop import run_self_dream_cycle


def main() -> None:
    parser = argparse.ArgumentParser(description="Run bounded CORTEX-G2 self-dream cycle.")
    parser.add_argument("--max-questions", type=int, default=10)
    args = parser.parse_args()
    print(json.dumps(run_self_dream_cycle(max_questions=args.max_questions), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
