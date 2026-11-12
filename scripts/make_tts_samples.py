"""用百炼 CosyVoice 生成 A/B/C 三段验收样本（SYS）。

为什么不走本机 SAPI：PowerShell 的 Add-Type / COM 在受限环境会被拦截，
而百炼语音合成只需要一个 HTTPS 请求，产出稳定且可重复。

流程：讲稿 → CosyVoice(wav) → ffmpeg 封装 H.264/AAC MP4 → ffprobe 校验。
产物：data/tmp/samples/lecture_{A,B,C}.mp4（不进 Git，*.mp4 已被忽略）

用法：
    python scripts/make_tts_samples.py                # 全部三段
    python scripts/make_tts_samples.py --only A C     # 指定段落
    python scripts/make_tts_samples.py --voice longxiaochun_v2

注意：合成样本用于联调与自测；正式质量证据仍以真实授权录课为准。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT_ROOT / "tests" / "fixtures" / "lecture_scripts.json"
OUT_DIR = PROJECT_ROOT / "data" / "tmp" / "samples"
FFMPEG = PROJECT_ROOT / "tools" / "ffmpeg" / "ffmpeg.exe"
FFPROBE = PROJECT_ROOT / "tools" / "ffmpeg" / "ffprobe.exe"
TTS_URL = "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer"
MODEL = "cosyvoice-v2"


def setup_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass


def api_key() -> str:
    """只从环境或 .env.local 读，绝不打印到日志。"""
    import os

    key = os.getenv("LLM_API_KEY", "")
    if key:
        return key
    env_file = PROJECT_ROOT / ".env.local"
    if env_file.is_file():
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                name, value = line.split("=", 1)
                if name.strip() == "LLM_API_KEY":
                    return value.strip().strip('"').strip("'")
    return ""


def synthesize(client: httpx.Client, text: str, voice: str, target: Path) -> dict:
    payload = {
        "model": MODEL,
        "input": {"text": text, "voice": voice, "format": "wav", "sample_rate": 24000},
    }
    response = client.post(TTS_URL, json=payload, headers={"Authorization": f"Bearer {api_key()}"}, timeout=180)
    if response.status_code != 200:
        raise RuntimeError(f"TTS 失败 HTTP {response.status_code}: {response.text[:200]}")
    url = response.json().get("output", {}).get("audio", {}).get("url")
    if not url:
        raise RuntimeError(f"TTS 未返回音频地址: {response.text[:200]}")
    audio = client.get(url, timeout=180)
    audio.raise_for_status()
    target.write_bytes(audio.content)
    return {"bytes": len(audio.content), "url_expires_at": response.json().get("output", {}).get("audio", {}).get("expires_at")}


def mux(wav: Path, target: Path) -> None:
    if not FFMPEG.is_file():
        raise RuntimeError(f"缺少 ffmpeg: {FFMPEG}")
    command = [
        str(FFMPEG),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=#1a3b6b:s=1280x720:r=15",
        "-i",
        str(wav),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "30",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "96k",
        "-ar",
        "16000",
        "-shortest",
        str(target),
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg 封装失败: {(result.stderr or '')[-400:]}")


def probe(target: Path) -> dict:
    command = [
        str(FFPROBE),
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(target),
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe 失败: {(result.stderr or '')[-300:]}")
    data = json.loads(result.stdout)
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), {})
    audio = next((s for s in data["streams"] if s["codec_type"] == "audio"), {})
    return {
        "duration_sec": round(float(data["format"]["duration"]), 1),
        "size_mb": round(int(data["format"]["size"]) / 1048576, 2),
        "video": f"{video.get('codec_name')} {video.get('width')}x{video.get('height')}",
        "audio": f"{audio.get('codec_name')} {audio.get('channels')}ch {audio.get('sample_rate')}Hz",
    }


def main() -> int:
    setup_stdout()
    parser = argparse.ArgumentParser(description="生成 A/B/C 验收样本")
    parser.add_argument("--only", nargs="*", default=None, help="只生成指定段落，如 --only A C")
    parser.add_argument("--voice", default="longxiaochun_v2", help="CosyVoice 音色")
    args = parser.parse_args()

    if not api_key():
        print("缺少 LLM_API_KEY：请在 .env.local 配置百炼密钥。")
        return 1

    scripts = json.loads(SCRIPTS.read_text(encoding="utf-8"))
    samples = args.only or [key for key in ("A", "B", "C") if key in scripts]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with httpx.Client(trust_env=False) as client:
        for sample in samples:
            entry = scripts[sample]
            wav = OUT_DIR / f"lecture_{sample}.wav"
            mp4 = OUT_DIR / f"lecture_{sample}.mp4"
            began = time.perf_counter()
            print(f"[{sample}] {entry['title']}：{len(entry['text'])} 字，合成中…")
            info = synthesize(client, entry["text"], args.voice, wav)
            mux(wav, mp4)
            meta = probe(mp4)
            print(
                f"[{sample}] 完成 {mp4.name}  {meta['duration_sec']}s  {meta['size_mb']}MB  "
                f"{meta['video']} / {meta['audio']}  用时 {time.perf_counter() - began:.1f}s"
            )
    print(f"\n样本目录：{OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
