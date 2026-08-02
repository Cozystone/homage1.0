from __future__ import annotations

import argparse
import os
import sys

import uvicorn

from app.services.desktop_paths import configure_desktop_data_dir


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ATANOR FastAPI desktop sidecar")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--log-level", default=os.getenv("ATANOR_LOG_LEVEL", os.getenv("HOMAGE_LOG_LEVEL", "info")))
    parser.add_argument("--operator", action="store_true", help="Start the local operator brain daemon automatically.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    data_dir = configure_desktop_data_dir(args.data_dir, chdir=True)
    os.environ["ATANOR_DESKTOP_SIDECAR"] = "1"
    os.environ["HOMAGE_DESKTOP_SIDECAR"] = "1"
    if args.operator:
        os.environ["ATANOR_OPERATOR"] = "1"
        os.environ["ATANOR_AUTO_START_DAEMON"] = "1"
        os.environ["ATANOR_AUTOSTART_DAEMON"] = "1"
        os.environ["HOMAGE_OPERATOR"] = "1"
        os.environ["HOMAGE_AUTO_START_DAEMON"] = "1"
    print(f"ATANOR_API_READY port={args.port} data_dir={data_dir}", flush=True)
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
