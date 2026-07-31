from __future__ import annotations

import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from app.macos import install_and_start_launch_agent, is_installed_macos_app, launch_agent_payload


class MacOSInstallerTests(unittest.TestCase):
    def test_applications_bundle_is_recognized(self) -> None:
        executable = Path("/Applications/ChurchBoard.app/Contents/MacOS/ChurchBoard")
        self.assertTrue(is_installed_macos_app(executable))
        self.assertFalse(is_installed_macos_app(Path("/Volumes/ChurchBoard/ChurchBoard.app/Contents/MacOS/ChurchBoard")))

    def test_launch_agent_points_to_installed_app_and_user_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            executable = Path("/Applications/ChurchBoard.app/Contents/MacOS/ChurchBoard")
            payload = launch_agent_payload(executable, home)
            self.assertEqual(payload["ProgramArguments"], [str(executable), "--background"])
            self.assertEqual(payload["EnvironmentVariables"], {"CHURCHBOARD_DATA_DIR": str(home / ".churchboard")})
            self.assertEqual(payload["StandardErrorPath"], str(home / "Library" / "Logs" / "ChurchBoard.error.log"))
            self.assertTrue(payload["RunAtLoad"])
            self.assertFalse(payload["KeepAlive"])
            self.assertEqual(payload["ProcessType"], "Interactive")

    def test_first_launch_writes_and_bootstraps_launch_agent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            executable = Path("/Applications/ChurchBoard.app/Contents/MacOS/ChurchBoard")
            completed = SimpleNamespace(returncode=0)
            with (
                patch("app.macos.sys.platform", "darwin"),
                patch.object(__import__("sys"), "frozen", True, create=True),
                patch("app.macos.is_installed_macos_app", return_value=True),
                patch("app.macos.subprocess.run", return_value=completed) as run_command,
            ):
                self.assertTrue(install_and_start_launch_agent(executable, home))

            plist_path = home / "Library" / "LaunchAgents" / "org.churchboard.app.plist"
            self.assertTrue(plist_path.is_file())
            self.assertEqual(plist_path.stat().st_mode & 0o777, 0o644)
            commands = [call.args[0] for call in run_command.call_args_list]
            self.assertEqual(commands[0][:2], ["/bin/launchctl", "bootout"])
            self.assertEqual(commands[1][:2], ["/bin/launchctl", "bootstrap"])
            self.assertEqual(commands[2][:2], ["/bin/launchctl", "enable"])
            self.assertEqual(commands[3][:2], ["/bin/launchctl", "kickstart"])


if __name__ == "__main__":
    unittest.main()
