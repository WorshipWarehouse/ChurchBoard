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
    ssl_certfile: Path | None = None
    ssl_keyfile: Path | None = None

    @property
    def scheme(self) -> str:
        return "https" if self.ssl_certfile and self.ssl_keyfile else "http"


def load_config() -> AppConfig:
    cert = os.getenv("CHURCHBOARD_SSL_CERTFILE", "").strip()
    key = os.getenv("CHURCHBOARD_SSL_KEYFILE", "").strip()
    if bool(cert) != bool(key):
        raise ValueError("Set both CHURCHBOARD_SSL_CERTFILE and CHURCHBOARD_SSL_KEYFILE to enable HTTPS")
    return AppConfig(
        host=os.getenv("CHURCHBOARD_HOST", "0.0.0.0"),
        port=int(os.getenv("CHURCHBOARD_PORT", "8040")),
        data_file=Path(os.getenv("CHURCHBOARD_DATA_FILE", DATA_DIR / "churchboard.json")),
        ssl_certfile=Path(cert).expanduser() if cert else None,
        ssl_keyfile=Path(key).expanduser() if key else None,
    )
