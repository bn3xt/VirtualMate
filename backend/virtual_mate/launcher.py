from __future__ import annotations

import os
import socket
import threading
import time
import webbrowser

import uvicorn

from virtual_mate.app import app


def _available_port(preferred: int) -> int:
    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("No local port is available for VirtualMate")


def _open_when_ready(port: int) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                webbrowser.open(f"http://127.0.0.1:{port}/")
                return
        except OSError:
            time.sleep(0.15)


def main() -> None:
    preferred = int(os.environ.get("VSA_PORT", "8765"))
    port = _available_port(preferred)
    if os.environ.get("VSA_OPEN_BROWSER", "1") != "0":
        threading.Thread(target=_open_when_ready, args=(port,), daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=port, reload=False, access_log=False)


if __name__ == "__main__":
    main()

