from __future__ import annotations

import argparse
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

from app.config import load_config
import uvicorn

from app.main import app, run
from app.macos import install_and_start_launch_agent


def open_churchboard(page: str) -> None:
    config = load_config()
    path = "/" + str(page or "admin").lstrip("/")
    webbrowser.open(f"http://127.0.0.1:{config.port}{path}")


def churchboard_is_running() -> bool:
    config = load_config()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{config.port}/api/app-info", timeout=0.75) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


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


def run_with_desktop_tray() -> None:
    from app.tray import DesktopTray

    config = load_config()
    server = uvicorn.Server(uvicorn.Config(app, host=config.host, port=config.port, reload=False))
    tray = DesktopTray(config.port, config.data_file, lambda: setattr(server, "should_exit", True))
    app.state.desktop_quit = tray.quit
    server_thread = threading.Thread(target=server.run, name="ChurchBoard server", daemon=True)
    server_thread.start()
    try:
        tray.run()
    finally:
        server.should_exit = True
        server_thread.join(timeout=10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ChurchBoard production dashboard")
    parser.add_argument(
        "--background",
        action="store_true",
        help="start the server without opening a browser (used by OS startup services)",
    )
    parser.add_argument(
        "--page",
        default="desktop",
        help="page to open when starting interactively (default: desktop)",
    )
    parser.add_argument("--no-tray", action="store_true", help="run without a menu-bar or system-tray icon")
    arguments = parser.parse_args()
    if churchboard_is_running():
        if not arguments.background:
            open_churchboard(arguments.page)
        raise SystemExit(0)
    if not arguments.background and install_and_start_launch_agent():
        open_churchboard_when_ready(arguments.page)
        raise SystemExit(0)
    if not arguments.background:
        threading.Timer(1.25, open_churchboard, args=(arguments.page,)).start()
    if sys.platform in {"darwin", "win32"} and not arguments.no_tray:
        run_with_desktop_tray()
    else:
        run()
