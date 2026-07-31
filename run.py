from __future__ import annotations

import argparse
import threading
import webbrowser

from app.config import load_config
from app.main import run


def open_churchboard(page: str) -> None:
    config = load_config()
    path = "/" + str(page or "admin").lstrip("/")
    webbrowser.open(f"http://127.0.0.1:{config.port}{path}")


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
    if not arguments.background:
        threading.Timer(1.25, open_churchboard, args=(arguments.page,)).start()
    run()
