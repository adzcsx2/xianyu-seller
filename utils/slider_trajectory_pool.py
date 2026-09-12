"""Per-account successful trajectory storage and distance-aware replay."""
import hashlib
import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger


def safe_storage_key(value: str) -> str:
    raw = str(value or "default")
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._")[:64] or "default"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{slug}-{digest}"


class SliderTrajectoryPool:
    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir or Path(__file__).resolve().parent.parent / "trajectories")
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.max_per_cookie = 50
        self.min_pool_size = 5

    @staticmethod
    def _storage_key(cookie_id: str) -> str:
        return safe_storage_key(cookie_id)

    def _cookie_dir(self, cookie_id: str) -> Path:
        directory = self.base_dir / self._storage_key(cookie_id)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def save_trajectory(
        self,
        points: List[List[float]],
        cookie_id: str,
        distance: float,
        success: bool,
        verify_url: str = "",
        duration_ms: float = 0,
    ) -> Optional[str]:
        directory = self._cookie_dir(cookie_id)
        existing = sorted(directory.glob("trajectory_*.json"))
        if len(existing) >= self.max_per_cookie:
            for path in existing[: len(existing) - self.max_per_cookie + 1]:
                path.unlink(missing_ok=True)
        sequence_numbers = []
        for path in existing:
            try:
                sequence_numbers.append(int(path.stem.rsplit("_", 1)[1]))
            except (IndexError, ValueError):
                continue
        filename = f"trajectory_{max(sequence_numbers, default=0) + 1:03d}.json"
        payload = {
            "cookie_id": str(cookie_id),
            "recorded_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "verify_url_hash": hashlib.md5(str(verify_url).encode()).hexdigest()[:8],
            "distance": round(float(distance), 1),
            "success": bool(success),
            "duration_ms": round(float(duration_ms), 1),
            "points": [
                [round(float(point[0]), 2), round(float(point[1]), 2), round(float(point[2]), 1)]
                for point in points
            ],
        }
        (directory / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("滑块轨迹已保存: cookie={} distance={} success={}", cookie_id, distance, success)
        return filename

    def _load_all(self, cookie_id: str) -> List[dict]:
        records = []
        for path in sorted(self._cookie_dir(cookie_id).glob("trajectory_*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                record["_file"] = str(path)
                records.append(record)
            except (OSError, ValueError):
                continue
        return records

    def _touch(self, record: dict) -> None:
        path = self._cookie_dir(record["cookie_id"]) / "last_used.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except ValueError:
            data = {}
        data[os.path.basename(record["_file"])] = time.time()
        path.write_text(json.dumps(data), encoding="utf-8")

    def load_best_trajectory(self, cookie_id: str, target_distance: float, distance_tolerance: float = 0.10):
        records = [record for record in self._load_all(cookie_id) if record.get("success")]
        if not records:
            return None
        for tolerance in (distance_tolerance, 0.15, 0.25, 0.40):
            candidates = [
                record for record in records
                if abs(float(record.get("distance", 0)) - target_distance) / max(target_distance, 1) <= tolerance
            ]
            if candidates:
                selected = min(candidates, key=lambda item: abs(float(item.get("distance", 0)) - target_distance))
                self._touch(selected)
                return selected
        return None

    def get_pool_stats(self, cookie_id: str) -> dict:
        records = self._load_all(cookie_id)
        successful = [record for record in records if record.get("success")]
        return {
            "total": len(records),
            "successful": len(successful),
            "failed": len(records) - len(successful),
            "success_rate": len(successful) / len(records) if records else 0,
            "avg_duration_ms": sum(record.get("duration_ms", 0) for record in records) / len(records) if records else 0,
            "pool_ready": len(records) >= self.min_pool_size,
        }

    def clean_stale(self, cookie_id: Optional[str] = None, max_age_days: int = 7) -> None:
        cutoff = datetime.now() - timedelta(days=max_age_days)
        directories = [self._cookie_dir(cookie_id)] if cookie_id else [path for path in self.base_dir.iterdir() if path.is_dir()]
        for directory in directories:
            for path in directory.glob("trajectory_*.json"):
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                    timestamp = datetime.strptime(record.get("recorded_at", "2000-01-01T00:00:00"), "%Y-%m-%dT%H:%M:%S")
                    if timestamp < cutoff or not record.get("success"):
                        path.unlink(missing_ok=True)
                except (OSError, ValueError):
                    continue


trajectory_pool = SliderTrajectoryPool()

__all__ = ["SliderTrajectoryPool", "safe_storage_key", "trajectory_pool"]
