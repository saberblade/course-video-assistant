"""时间和文件名这类小工具。"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def elapsed_seconds(status: str, started_at: str | None, finished_at: str | None) -> int:
    if status == "queued" or not started_at:
        return 0
    start = parse_utc(started_at)
    end = parse_utc(finished_at) if finished_at else datetime.now(timezone.utc)
    return max(0, int((end - start).total_seconds()))


def safe_title(filename: str | None) -> str:
    raw_name = Path(filename or "").name
    stem = Path(raw_name).stem.strip()
    cleaned = re.sub(r'[\x00-\x1f<>:"/\\|?*]', "", stem).strip()
    cleaned = cleaned[:120]
    return cleaned or "未命名视频"
