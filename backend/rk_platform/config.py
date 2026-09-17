from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]


def load_config() -> dict[str, Any]:
    path = Path(os.getenv("RK_PLATFORM_CONFIG", ROOT / "config/platform.yaml"))
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    config["_root"] = str(ROOT)
    config["_config_path"] = str(path)
    return config


def resolve_path(config: dict[str, Any], value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else Path(config["_root"]) / path

