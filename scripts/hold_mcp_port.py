#!/usr/bin/env python3
"""Hold localhost:8765 so WriterAgent MCP start can fail with a port-in-use dialog.

Usage:
  python scripts/hold_mcp_port.py
  python scripts/hold_mcp_port.py --port 8765

Ctrl+C to release the port.
"""

from __future__ import annotations

import argparse
import socket
import time


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="localhost", help="Bind host (default: localhost)")
    parser.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765)")
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.host, args.port))
    sock.listen(1)
    print(f"Holding {args.host}:{args.port} — start MCP in LibreOffice, then Ctrl+C here to release.")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\nReleasing port.")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
