from __future__ import annotations

import csv
import json
import platform
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .database import Database, now_iso


class ExperimentManager:
    def __init__(self, root: Path, db: Database, config: dict[str, Any]):
        self.root, self.db, self.config = root, db, config

    def create(self, name: str, variables: dict[str, Any]) -> dict[str, Any]:
        experiment_id = str(uuid.uuid4())
        slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-")[:48] or "experiment"
        directory = self.root / "experiments" / f"{datetime.now():%Y%m%d-%H%M%S}-{slug}"
        (directory / "figures").mkdir(parents=True)
        try:
            commit = subprocess.check_output(["git", "-C", str(self.root), "rev-parse", "HEAD"], text=True).strip()
        except (subprocess.SubprocessError, FileNotFoundError):
            commit = "uncommitted"
        manifest = {
            "id": experiment_id, "name": name, "created_at": now_iso(), "git_commit": commit,
            "host": platform.uname()._asdict(), "model": self.config["models"]["active"],
            "variables": variables, "reproducibility": {"config": self.config["_config_path"]},
        }
        (directory / "manifest.yaml").write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
        (directory / "raw.jsonl").touch()
        for filename, header in {
            "metrics.csv": ["timestamp", "request_id", "ttft_ms", "prefill_tps", "decode_tps", "input_tokens", "output_tokens", "reused_tokens", "error"],
            "system.csv": ["timestamp", "cpu_percent", "memory_used_mb", "rk3588_npu_load", "rk1828_busy_percent", "temperature_c"],
        }.items():
            with (directory / filename).open("w", newline="", encoding="utf-8") as handle:
                csv.writer(handle).writerow(header)
        (directory / "summary.md").write_text(
            f"# {name}\n\n状态：进行中\n\n## 假设\n\n待填写。\n\n## 方法\n\n见 `manifest.yaml`。\n\n## 结果\n\n待实验完成后由汇总脚本生成。\n",
            encoding="utf-8",
        )
        self.db.execute("INSERT INTO experiments VALUES (?, ?, ?, ?, ?, ?, NULL)",
                        (experiment_id, name, "running", str(directory), json.dumps(variables, ensure_ascii=False), now_iso()))
        return {"id": experiment_id, "name": name, "status": "running", "directory": str(directory)}

    def get(self, experiment_id: str) -> dict[str, Any] | None:
        rows = self.db.rows("SELECT * FROM experiments WHERE id=?", (experiment_id,))
        return rows[0] if rows else None

