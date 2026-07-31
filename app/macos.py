from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path


LAUNCH_AGENT_LABEL = "org.churchboard.app"


def is_installed_macos_app(executable: Path | None = None) -> bool:
    """Return whether ChurchBoard is running from the system Applications folder."""
    candidate = (executable or Path(sys.executable)).resolve()
    return str(candidate).startswith("/Applications/ChurchBoard.app/Contents/MacOS/")


def launch_agent_payload(executable: Path, home: Path) -> dict[str, object]:
    data_dir = home / ".churchboard"
    log_dir = home / "Library" / "Logs"
    app_bundle = executable.parents[2]
    return {
        "Label": LAUNCH_AGENT_LABEL,
        # Launch the bundle through LaunchServices so macOS registers a real
        # GUI application with a Dock icon. -n ensures the bootstrap instance
        # can hand off to a separate background instance on first launch.
        "ProgramArguments": [
            "/usr/bin/open", "-n", str(app_bundle), "--args", "--background", "--launchservices",
        ],
        "EnvironmentVariables": {"CHURCHBOARD_DATA_DIR": str(data_dir)},
        "RunAtLoad": True,
        "KeepAlive": False,
        "ProcessType": "Interactive",
        "StandardOutPath": str(log_dir / "ChurchBoard.log"),
        "StandardErrorPath": str(log_dir / "ChurchBoard.error.log"),
    }


def install_and_start_launch_agent(
    executable: Path | None = None,
    home: Path | None = None,
) -> bool:
    """Install the current-user LaunchAgent and start the background server."""
    executable = (executable or Path(sys.executable)).resolve()
    home = (home or Path.home()).resolve()
    if sys.platform != "darwin" or not getattr(sys, "frozen", False):
        return False
    if not is_installed_macos_app(executable):
        return False

    launch_agents = home / "Library" / "LaunchAgents"
    log_dir = home / "Library" / "Logs"
    data_dir = home / ".churchboard"
    launch_agents.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    plist_path = launch_agents / f"{LAUNCH_AGENT_LABEL}.plist"
    temporary_path = plist_path.with_suffix(".plist.tmp")
    with temporary_path.open("wb") as handle:
        plistlib.dump(launch_agent_payload(executable, home), handle, sort_keys=False)
    os.chmod(temporary_path, 0o644)
    temporary_path.replace(plist_path)

    domain = f"gui/{os.getuid()}"
    subprocess.run(
        ["/bin/launchctl", "bootout", f"{domain}/{LAUNCH_AGENT_LABEL}"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    result = subprocess.run(
        ["/bin/launchctl", "bootstrap", domain, str(plist_path)],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode == 0:
        subprocess.run(
            ["/bin/launchctl", "enable", f"{domain}/{LAUNCH_AGENT_LABEL}"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return result.returncode == 0
