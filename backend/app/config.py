"""读取配置。环境变量优先于 .env.local，密钥只放服务端。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_local_env() -> None:
    """把 course-review/.env.local 里尚未设置的变量读进来。不覆盖已经存在的环境变量。"""
    path = PROJECT_ROOT / ".env.local"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class Settings:
    app_env: str
    app_host: str
    app_port: int
    app_version: str
    data_dir: Path
    ffmpeg_bin: str
    ffprobe_bin: str
    max_upload_bytes: int
    max_video_seconds: int
    max_unfinished_jobs: int
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_connect_timeout_seconds: float
    llm_total_deadline_seconds: float
    answer_mode: str
    retrieval_top_k: int
    max_context_characters: int

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_base_url and self.llm_api_key and self.llm_model)

    @property
    def database_path(self) -> Path:
        return self.data_dir / "app.db"


@lru_cache
def get_settings() -> Settings:
    load_local_env()
    data_dir = Path(os.getenv("DATA_DIR", "data"))
    if not data_dir.is_absolute():
        data_dir = PROJECT_ROOT / data_dir
    return Settings(
        app_env=os.getenv("APP_ENV", "demo"),
        app_host=os.getenv("APP_HOST", "127.0.0.1"),
        app_port=int(os.getenv("APP_PORT", "8000")),
        app_version=os.getenv("APP_VERSION", "0.1.0"),
        data_dir=data_dir.resolve(),
        ffmpeg_bin=os.getenv("FFMPEG_BIN", "ffmpeg"),
        ffprobe_bin=os.getenv("FFPROBE_BIN", "ffprobe"),
        max_upload_bytes=int(os.getenv("MAX_UPLOAD_BYTES", "209715200")),
        max_video_seconds=int(os.getenv("MAX_VIDEO_SECONDS", "1200")),
        max_unfinished_jobs=int(os.getenv("MAX_UNFINISHED_JOBS", "3")),
        llm_base_url=os.getenv("LLM_BASE_URL", ""),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", "qwen-plus"),
        llm_connect_timeout_seconds=float(os.getenv("LLM_CONNECT_TIMEOUT_SECONDS", "5")),
        llm_total_deadline_seconds=float(os.getenv("LLM_TOTAL_DEADLINE_SECONDS", "25")),
        answer_mode=os.getenv("ANSWER_MODE", "generative"),
        retrieval_top_k=int(os.getenv("RETRIEVAL_TOP_K", "5")),
        max_context_characters=int(os.getenv("MAX_CONTEXT_CHARACTERS", "6000")),
    )
