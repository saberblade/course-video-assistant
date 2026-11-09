"""用 ffprobe 检查视频。没安装时明确报错，不编造时长。"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.errors import AppError


@dataclass(frozen=True)
class MediaInfo:
    duration_sec: float
    container: str
    video_codec: str
    audio_codec: str


def probe_media(path: Path, ffprobe_bin: str, max_video_seconds: int = 1200, timeout_sec: float = 15) -> MediaInfo:
    executable = shutil.which(ffprobe_bin) or (ffprobe_bin if Path(ffprobe_bin).is_file() else None)
    if executable is None:
        raise AppError(
            503,
            "SERVICE_NOT_READY",
            "还没有安装 ffprobe，请系统工程师先准备 FFmpeg",
            True,
        )
    try:
        completed = subprocess.run(
            [
                executable,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            capture_output=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AppError(422, "INVALID_VIDEO", "视频文件无法读取或已损坏", False) from exc
    if completed.returncode != 0:
        raise AppError(422, "INVALID_VIDEO", "视频文件无法读取或已损坏", False)
    try:
        payload = json.loads(completed.stdout.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise AppError(422, "INVALID_VIDEO", "视频文件无法读取或已损坏", False) from exc
    return _interpret(payload, max_video_seconds)


def _interpret(payload: dict, max_video_seconds: int) -> MediaInfo:
    format_name = str(payload.get("format", {}).get("format_name", ""))
    containers = {item.strip() for item in format_name.split(",") if item.strip()}
    streams = payload.get("streams") or []
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    if audio is None:
        raise AppError(422, "AUDIO_REQUIRED", "视频里没有音轨，请换有讲解声音的文件", False)
    if "mp4" not in containers or video is None or video.get("codec_name") != "h264" or audio.get("codec_name") != "aac":
        raise AppError(415, "UNSUPPORTED_MEDIA", "请使用MP4容器、H.264视频和AAC音频", False)
    try:
        duration = float(payload.get("format", {}).get("duration", 0))
    except (TypeError, ValueError) as exc:
        raise AppError(422, "INVALID_VIDEO", "视频文件无法读取或已损坏", False) from exc
    if duration <= 0:
        raise AppError(422, "INVALID_VIDEO", "视频文件无法读取或已损坏", False)
    if duration > max_video_seconds:
        raise AppError(422, "DURATION_EXCEEDED", "视频时长不能超过20分钟", False)
    return MediaInfo(duration, "mp4", "h264", "aac")
