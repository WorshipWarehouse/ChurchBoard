from __future__ import annotations

import argparse
import threading
import time
import urllib.error
import urllib.request
import webbrowser

from app.config import load_config
from app.main import run
from app.macos import install_and_start_launch_agent


def open_churchboard(page: str) -> None:
    config = load_config()
    path = "/" + str(page or "admin").lstrip("/")
    webbrowser.open(f"http://127.0.0.1:{config.port}{path}")


def open_churchboard_when_ready(page: str, timeout: float = 20.0) -> None:
    config = load_config()
    deadline = time.monotonic() + timeout
    health_url = f"http://127.0.0.1:{config.port}/api/app-info"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=0.75) as response:
                if response.status == 200:
                    open_churchboard(page)
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.25)
    open_churchboard(page)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ChurchBoard production dashboard")
    parser.add_argument(
        "--background",
        action="store_true",
        help="start the server without opening a browser (used by OS startup services)",
    )
    parser.add_argument(
        "--page",
        default="admin",
        help="page to open when starting interactively (default: admin)",
    )
    arguments = parser.parse_args()
    if not arguments.background and install_and_start_launch_agent():
        open_churchboard_when_ready(arguments.page)
        raise SystemExit(0)
    if not arguments.background:
        threading.Timer(1.25, open_churchboard, args=(arguments.page,)).start()
    run()
