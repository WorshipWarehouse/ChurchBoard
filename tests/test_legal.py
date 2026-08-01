from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


class LegalPackagingTests(unittest.TestCase):
    def test_dependency_license_collector_only_copies_notice_files(self):
        spec = importlib.util.spec_from_file_location(
            "churchboard_collect_licenses",
            PROJECT / "packaging" / "collect_licenses.py",
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "third-party"
            packages = module.collect(output)
            self.assertTrue(packages)
            self.assertTrue((output / "README.md").is_file())
            self.assertTrue(any(path.name == "PACKAGE.txt" for path in output.rglob("PACKAGE.txt")))
            forbidden = {".py", ".pyc", ".so", ".dylib", ".dll", ".exe"}
            self.assertFalse([path for path in output.rglob("*") if path.is_file() and path.suffix.casefold() in forbidden])
