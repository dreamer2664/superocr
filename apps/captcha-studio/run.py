#!/usr/bin/env python3
"""CAPTCHA Studio launcher: unzip -> `python3 run.py` -> browser opens.

- Picks a free port starting at 8433 (if busy, scans upward).
- Starts the server as a supervised child process (watchdog: restarts on
  crash, up to 5 times; Ctrl-C stops everything).
- Opens the app in the default browser once the server answers.
"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

APP = Path(__file__).resolve().parent
BASE_PORT = 8433
MAX_PORT_SCAN = 20
MAX_RESTARTS = 5


def free_port() -> int:
    for p in range(BASE_PORT, BASE_PORT + MAX_PORT_SCAN):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise SystemExit(f"no free port in {BASE_PORT}..{BASE_PORT + MAX_PORT_SCAN}")


def wait_healthy(port: int, timeout: float = 10.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/api/config", timeout=1.5) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.25)
    return False


def main() -> int:
    # dependency check with a human-readable message first
    try:
        import numpy, PIL  # noqa: F401
    except ImportError as e:
        print("CAPTCHA Studio needs python3 with numpy and Pillow installed:")
        print("    python3 -m pip install numpy Pillow")
        print(f"(missing: {e.name})")
        return 1

    port = free_port()
    url = f"http://127.0.0.1:{port}/"
    print(f"CAPTCHA Studio -> {url}  (Ctrl-C to quit)")
    restarts = 0
    first = True
    while True:
        child = subprocess.Popen(
            [sys.executable, str(APP / "server.py"), "--host", "127.0.0.1",
             "--port", str(port)],
            cwd=str(APP))
        if first:
            first = False
            if wait_healthy(port):
                print("server healthy — opening the app in your browser")
                try:
                    webbrowser.open(url)
                except Exception:
                    print(f"could not auto-open a browser; visit {url} manually")
            else:
                print(f"server did not answer on {url} yet — check the child log")
        rc = child.wait()
        if rc == 0:
            return 0  # normal exit
        restarts += 1
        if restarts > MAX_RESTARTS:
            print(f"server crashed {MAX_RESTARTS} times; giving up")
            return 2
        print(f"server exited with code {rc}; watchdog restart "
              f"{restarts}/{MAX_RESTARTS} in 1s...")
        time.sleep(1.0)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nbye")
        sys.exit(0)
