from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


if getattr(sys, "frozen", False):
    ROOT_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    DATA_DIR = Path(os.getenv("CHURCHBOARD_DATA_DIR", Path.home() / ".churchboard"))
else:
    ROOT_DIR = Path(__file__).resolve().parents[1]
    DATA_DIR = Path(os.getenv("CHURCHBOARD_DATA_DIR", ROOT_DIR / "data"))


@dataclass(frozen=True)
class AppConfig:
    host: str
    port: int
    data_file: Path


def load_config() -> AppConfig:
    return AppConfig(
        host=os.getenv("CHURCHBOARD_HOST", "0.0.0.0"),
        port=int(os.getenv("CHURCHBOARD_PORT", "8040")),
        data_file=Path(os.getenv("CHURCHBOARD_DATA_FILE", DATA_DIR / "churchboard.json")),
    )

