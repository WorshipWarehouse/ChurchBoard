from __future__ import annotations

import unittest
from unittest.mock import patch

from app.update import platform_asset, version_key


class UpdateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assets = [
            {"name": "ChurchBoard-0.2.0-macOS-arm64.dmg"},
            {"name": "ChurchBoard-0.2.0-macOS-x86_64.dmg"},
            {"name": "ChurchBoard-0.2.0-Windows-x64-Setup.exe"},
            {"name": "ChurchBoard-0.2.0-Linux-amd64.deb"},
            {"name": "ChurchBoard-0.2.0-Linux-x86_64.tar.gz"},
        ]

    def test_version_comparison_key(self) -> None:
        self.assertGreater(version_key("v0.1.10"), version_key("0.1.9"))
        self.assertEqual(version_key("0.1.2"), (0, 1, 2))

    def test_selects_apple_silicon_installer(self) -> None:
        with patch("app.update.platform.system", return_value="Darwin"), patch("app.update.platform.machine", return_value="arm64"):
            self.assertEqual(platform_asset(self.assets)["name"], "ChurchBoard-0.2.0-macOS-arm64.dmg")

    def test_selects_windows_installer(self) -> None:
        with patch("app.update.platform.system", return_value="Windows"), patch("app.update.platform.machine", return_value="AMD64"):
            self.assertEqual(platform_asset(self.assets)["name"], "ChurchBoard-0.2.0-Windows-x64-Setup.exe")

    def test_selects_linux_package(self) -> None:
        with patch("app.update.platform.system", return_value="Linux"), patch("app.update.platform.machine", return_value="x86_64"):
            self.assertEqual(platform_asset(self.assets)["name"], "ChurchBoard-0.2.0-Linux-amd64.deb")


if __name__ == "__main__":
    unittest.main()
