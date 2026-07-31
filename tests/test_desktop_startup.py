from __future__ import annotations

import logging
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import uvicorn

from run import desktop_log_config


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


if __name__ == "__main__":
    unittest.main()
