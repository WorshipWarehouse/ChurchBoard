from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.tray import DesktopTray


class TrayTests(unittest.TestCase):
    def test_dashboard_menu_actions_open_the_selected_board(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tray = DesktopTray(8040, Path(directory) / "churchboard.json", lambda: None)
            items = tray._boards_menu()
            self.assertGreaterEqual(len(items), 1)
            with patch.object(tray, "open_path") as open_path:
                items[0]._action(None, items[0])
            open_path.assert_called_once_with("display/main")


if __name__ == "__main__":
    unittest.main()
