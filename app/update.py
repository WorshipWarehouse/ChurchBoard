from __future__ import annotations

import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx

from app.version import __version__


REPOSITORY = "WorshipWarehouse/ChurchBoard"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
RELEASES_URL = f"https://github.com/{REPOSITORY}/releases/latest"


def _headers(download: bool = False) -> dict[str, str]:
    headers = {
        "Accept": "application/octet-stream" if download else "application/vnd.github+json",
        "User-Agent": f"ChurchBoard/{__version__}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.getenv("CHURCHBOARD_GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def version_key(value: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", value or "")
    return tuple(int(number) for number in numbers[:4]) or (0,)


def platform_asset(assets: list[dict[str, Any]]) -> dict[str, Any] | None:
    system = platform.system().lower()
    machine = platform.machine().lower()
    names: list[str]
    if system == "darwin":
        architecture = "arm64" if machine in {"arm64", "aarch64"} else "x86_64"
        names = [f"macOS-{architecture}.dmg"]
    elif system == "windows":
        names = ["Windows-x64-Setup.exe"]
    elif system == "linux":
        architecture = "arm64" if machine in {"arm64", "aarch64"} else "amd64"
        archive_architecture = "aarch64" if architecture == "arm64" else "x86_64"
        names = [f"Linux-{architecture}.deb", f"Linux-{archive_architecture}.tar.gz"]
    else:
        return None
    for suffix in names:
        match = next((asset for asset in assets if str(asset.get("name", "")).endswith(suffix)), None)
        if match:
            return match
    return None


async def update_status() -> dict[str, Any]:
    base = {
        "current_version": __version__,
        "available": False,
        "release_url": RELEASES_URL,
        "can_install": False,
    }
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            response = await client.get(LATEST_RELEASE_API, headers=_headers())
        if response.status_code in {401, 403, 404}:
            return {
                **base,
                "requires_auth": True,
                "message": "Sign in to GitHub to view private ChurchBoard updates.",
            }
        response.raise_for_status()
        release = response.json()
    except Exception as exc:
        return {**base, "message": f"Could not check GitHub right now: {exc}"}

    latest = str(release.get("tag_name") or "").lstrip("v")
    asset = platform_asset(list(release.get("assets") or []))
    available = version_key(latest) > version_key(__version__)
    return {
        **base,
        "latest_version": latest or None,
        "available": available,
        "can_install": bool(available and asset),
        "asset_name": asset.get("name") if asset else None,
        "release_url": release.get("html_url") or RELEASES_URL,
        "message": (
            f"ChurchBoard {latest} is ready to install."
            if available and asset
            else "You have the latest version of ChurchBoard."
            if latest and not available
            else "A release is available, but there is no installer for this computer."
        ),
        "_asset": asset,
    }


def _downloads_directory() -> Path:
    downloads = Path.home() / "Downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    return downloads


def launch_installer(path: Path) -> None:
    if sys.platform == "darwin":
        subprocess.Popen(["/usr/bin/open", str(path)])
    elif sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(path)])


async def download_update() -> dict[str, Any]:
    status = await update_status()
    asset = status.pop("_asset", None)
    if not status.get("available"):
        return status
    if not asset:
        return {**status, "can_install": False}

    destination = _downloads_directory() / str(asset["name"])
    download_url = asset.get("url") or asset.get("browser_download_url")
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=180) as client:
            async with client.stream("GET", download_url, headers=_headers(download=True)) as response:
                response.raise_for_status()
                with destination.open("wb") as handle:
                    async for chunk in response.aiter_bytes():
                        handle.write(chunk)
        launch_installer(destination)
    except Exception as exc:
        destination.unlink(missing_ok=True)
        return {**status, "installed": False, "message": f"Could not download the update: {exc}"}

    guidance = (
        "The new disk image is open. Quit ChurchBoard, then drag the new app to Applications."
        if sys.platform == "darwin"
        else "The ChurchBoard installer is open. Follow its prompts to finish updating."
    )
    return {**status, "installed": True, "download_path": str(destination), "message": guidance}
