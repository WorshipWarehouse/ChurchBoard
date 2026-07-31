from __future__ import annotations

import logging
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import uvicorn

from run import (
    _is_churchboard_process,
    _listener_pids,
    compatible_desktop_is_running,
    desktop_log_config,
)


class DesktopStartupTests(unittest.TestCase):
    def test_uvicorn_logging_does_not_require_a_console_stream(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.object(sys, "stderr", None):
            data_file = Path(directory) / "churchboard.json"
            config = uvicorn.Config(
                "app.main:app",
                host="127.0.0.1",
                port=8040,
                access_log=False,
                log_config=desktop_log_config(data_file),
            )
            self.assertEqual(config.port, 8040)
            self.assertTrue((Path(directory) / "ChurchBoard.log").is_file())
        logging.shutdown()

    def test_only_current_tray_version_is_reused(self) -> None:
        with patch("run.running_churchboard_info", return_value={
            "version": "0.1.5", "desktop_tray": True,
        }):
            self.assertFalse(compatible_desktop_is_running())
        with patch("run.running_churchboard_info", return_value={
            "version": __import__("app.version", fromlist=["__version__"]).__version__,
            "desktop_tray": True,
        }), patch("run.sys.platform", "win32"):
            self.assertTrue(compatible_desktop_is_running())

    def test_macos_requires_launchservices_instance(self) -> None:
        current = __import__("app.version", fromlist=["__version__"]).__version__
        with patch("run.sys.platform", "darwin"), patch(
            "run.running_churchboard_info",
            return_value={"version": current, "desktop_tray": True, "macos_launchservices": False},
        ):
            self.assertFalse(compatible_desktop_is_running())
        with patch("run.sys.platform", "darwin"), patch(
            "run.running_churchboard_info",
            return_value={"version": current, "desktop_tray": True, "macos_launchservices": True},
        ):
            self.assertTrue(compatible_desktop_is_running())

    def test_windows_listener_and_process_name_are_verified(self) -> None:
        netstat = Mock(stdout=(
            "  TCP    0.0.0.0:8040     0.0.0.0:0       LISTENING       321\n"
            "  TCP    127.0.0.1:1234   127.0.0.1:8040  ESTABLISHED     999\n"
        ))
        tasklist = Mock(stdout='"ChurchBoard.exe","321","Console","1","10,000 K"\n')
        with patch("run.sys.platform", "win32"), patch("run._run_hidden", side_effect=[netstat, tasklist]):
            self.assertEqual(_listener_pids(8040), {321})
            self.assertTrue(_is_churchboard_process(321))


if __name__ == "__main__":
    unittest.main()
