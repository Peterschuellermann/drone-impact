from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
from pathlib import Path

from droneimpact.config import AppConfig

logger = logging.getLogger(__name__)


def compute_fingerprint(config: AppConfig) -> str:
    """SHA-256 of git commit + serialised config sections that affect results."""
    parts: list[str] = []

    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        parts.append(sha)
    except Exception:
        parts.append("unknown")

    for section in (config.physics, config.engagement, config.casualty, config.scoring):
        parts.append(section.model_dump_json(exclude_none=True))

    digest = hashlib.sha256("||".join(parts).encode()).hexdigest()
    return digest[:12]


def compute_request_hash(
    lat: float,
    lon: float,
    altitude_m: float,
    heading_deg: float,
    speed_m_s: float,
    evaluation_spacing_m: int,
    max_range_m: int,
) -> str:
    canonical = json.dumps(
        [lat, lon, altitude_m, heading_deg, speed_m_s, evaluation_spacing_m, max_range_m],
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]


class ResultCache:
    def __init__(
        self,
        cache_dir: Path,
        fingerprint: str,
        max_entries: int = 50,
        enabled: bool = True,
    ):
        self._dir = cache_dir
        self._fingerprint = fingerprint
        self._max_entries = max_entries
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    def prune_stale(self) -> int:
        if not self._dir.exists():
            return 0
        pruned = 0
        for f in self._dir.glob("*.json"):
            if not f.name.startswith(self._fingerprint + "_"):
                f.unlink()
                pruned += 1
        return pruned

    def get(self, request_hash: str) -> dict | None:
        if not self._enabled:
            return None
        path = self._dir / f"{self._fingerprint}_{request_hash}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except Exception:
            logger.warning("Corrupt cache entry %s — removing", path.name)
            path.unlink(missing_ok=True)
            return None

    def put(self, request_hash: str, response: dict) -> None:
        if not self._enabled:
            return
        self._dir.mkdir(parents=True, exist_ok=True)
        self._evict_if_full()
        path = self._dir / f"{self._fingerprint}_{request_hash}.json"
        path.write_text(json.dumps(response))

    def _evict_if_full(self) -> None:
        entries = sorted(self._dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
        while len(entries) >= self._max_entries:
            oldest = entries.pop(0)
            oldest.unlink()
            logger.debug("Evicted cache entry %s", oldest.name)
