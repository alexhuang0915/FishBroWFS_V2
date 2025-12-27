#!/usr/bin/env python3
"""
Control API Server Entrypoint.

Zero‑Violation Split‑Brain Architecture: UI HTTP Client + Control API Authority.
This is the standalone entrypoint for the Control API server (FastAPI + Uvicorn).
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Ensure the module can be imported
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from control.api import app


def parse_args() -> argparse.Namespace:
    """Parse command‑line arguments."""
    parser = argparse.ArgumentParser(
        description="FishBroWFS V2 Control API Server",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--host",
        default=os.getenv("CONTROL_API_HOST", "127.0.0.1"),
        help="Host to bind the server",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("CONTROL_API_PORT", "8000")),
        help="Port to bind the server",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        default=False,
        help="Enable auto‑reload (development only)",
    )
    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error", "critical"],
        default="info",
        help="Logging level",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of worker processes (Uvicorn workers)",
    )
    return parser.parse_args()


def main() -> None:
    """Main entrypoint."""
    args = parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Import uvicorn only when needed (avoid extra dependency for CLI)
    try:
        import uvicorn
    except ImportError:
        print("ERROR: uvicorn is required to run the Control API server.", file=sys.stderr)
        print("Install with: pip install uvicorn[standard]", file=sys.stderr)
        sys.exit(1)

    # Log startup info
    logging.info(
        "Starting Control API server on %s:%d (reload=%s, workers=%d)",
        args.host, args.port, args.reload, args.workers,
    )
    logging.info("Service identity endpoint: http://%s:%d/__identity", args.host, args.port)
    logging.info("Health endpoint: http://%s:%d/health", args.host, args.port)
    logging.info("OpenAPI docs: http://%s:%d/docs", args.host, args.port)

    # Run the server
    uvicorn.run(
        "control.api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()