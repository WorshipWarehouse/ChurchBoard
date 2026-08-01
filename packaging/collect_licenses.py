"""Collect license files for the exact Python distributions in a release build."""

from __future__ import annotations

import importlib.metadata
import re
import shutil
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT / "build" / "legal" / "third-party"
LICENSE_NAMES = re.compile(r"^(license|licence|copying|notice)([._-].*)?$", re.IGNORECASE)


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._+-]+", "-", value).strip("-") or "unknown"


def collect(output: Path = OUTPUT) -> list[str]:
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    packages: list[str] = []
    for distribution in sorted(importlib.metadata.distributions(), key=lambda item: (item.metadata.get("Name") or "").casefold()):
        name = distribution.metadata.get("Name") or "unknown"
        version = distribution.version
        destination = output / f"{safe_name(name)}-{safe_name(version)}"
        copied = 0
        for entry in distribution.files or []:
            parts = [part.casefold() for part in Path(str(entry)).parts]
            filename = Path(str(entry)).name
            in_distribution_metadata = any(part.endswith(".dist-info") for part in parts)
            if not in_distribution_metadata or ("licenses" not in parts and not LICENSE_NAMES.match(filename)):
                continue
            source = Path(distribution.locate_file(entry))
            if not source.is_file():
                continue
            destination.mkdir(parents=True, exist_ok=True)
            target = destination / safe_name("-".join(Path(str(entry)).parts[-3:]))
            shutil.copy2(source, target)
            copied += 1
        expression = distribution.metadata.get("License-Expression") or distribution.metadata.get("License") or "See bundled notice"
        if copied:
            (destination / "PACKAGE.txt").write_text(
                f"Name: {name}\nVersion: {version}\nLicense: {expression}\n",
                encoding="utf-8",
            )
            packages.append(f"- {name} {version} — {expression}")
    (output / "README.md").write_text(
        "# Collected dependency licenses\n\nGenerated from the release build environment.\n\n" + "\n".join(packages) + "\n",
        encoding="utf-8",
    )
    return packages


if __name__ == "__main__":
    collected = collect()
    print(f"Collected license notices for {len(collected)} distributions in {OUTPUT}")
