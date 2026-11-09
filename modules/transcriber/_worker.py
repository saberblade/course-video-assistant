# -*- coding: utf-8 -*-
"""
转写 worker 子进程（SYS / M2）

约束（见《API与数据模型契约》"SYS与BE的转写模块契约"）：
- 只在本子进程内加载模型；父进程可 terminate() 真正终止本进程（含推理）。
- 单进程顺序处理任务，一次只处理一个。
- 任何失败以 {type:"error", code, message} 回报，绝不吞错误返回空列表。
- 不写业务 SQLite、不读业务状态，只听管道命令。

通信协议（jsonlines over stdin/stdout，编码 UTF-8）：
  请求：{"cmd":"warmup"} | {"cmd":"transcribe","video_path":..,"out_dir":..} | {"cmd":"ping"} | {"cmd":"shutdown"}
  响应：{"type":"ok",...} | {"type":"error","code":...,"message":...}
"""
from __future__ import annotations

import json
import math
import os
import pathlib
import sys
import time
import traceback
import uuid

# 契约定义的错误码
CODE_MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
CODE_INVALID_VIDEO = "INVALID_VIDEO"
CODE_AUDIO_REQUIRED = "AUDIO_REQUIRED"
CODE_TRANSCRIBE_FAILED = "TRANSCRIBE_FAILED"
CODE_NO_SPEECH = "NO_SPEECH"


def _err(code: str, message: str) -> dict:
    return {"type": "error", "code": code, "message": message}


def _env(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v.strip() if (v or "").strip() else default


class Worker:
    def __init__(self) -> None:
        self._model = None
        self._language = None

    # ---------- 模型 ----------
    def _ensure_model(self) -> float | None:
        """懒加载模型；返回本次加载耗时（已加载返回 None）。"""
        if self._model is not None:
            return None
        import faster_whisper  # 延迟导入：未接任务不占内存

        model_dir = pathlib.Path(_env("WHISPER_MODEL_DIR", "./models/faster-whisper-small"))
        if not model_dir.is_absolute():
            model_dir = (pathlib.Path.cwd() / model_dir).resolve()
        if not (model_dir / "model.bin").exists():
            raise ValueError(CODE_MODEL_NOT_FOUND)

        t0 = time.perf_counter()
        self._model = faster_whisper.WhisperModel(
            str(model_dir),
            device=_env("WHISPER_DEVICE", "cpu"),
            compute_type=_env("WHISPER_COMPUTE_TYPE", "int8"),
            cpu_threads=int(_env("WHISPER_CPU_THREADS", str(min(8, os.cpu_count() or 8)))),
        )
        self._language = _env("WHISPER_LANGUAGE", "zh") or None
        return time.perf_counter() - t0

    # ---------- 音轨校验（模块内第二防线，与 BE 的 ffprobe 校验互补）----------
    @staticmethod
    def _check_audio(video_path: pathlib.Path) -> float:
        import av

        try:
            with av.open(str(video_path)) as container:
                if not container.streams.audio:
                    raise ValueError(CODE_AUDIO_REQUIRED)
                if not container.duration:
                    raise ValueError(CODE_INVALID_VIDEO)
                dur = container.duration / float(av.time_base)
                if dur <= 0:
                    raise ValueError(CODE_INVALID_VIDEO)
                return dur
        except av.FFmpegError:
            # PyAV 将 ffmpeg 运行时错误统一定义为 FFmpegError（含文件类型错误、损坏流等）
            raise ValueError(CODE_INVALID_VIDEO)

    # ---------- 转写 ----------
    def transcribe(self, video_path: str, out_dir: str) -> dict:
        vp = pathlib.Path(video_path)
        if not vp.is_absolute():  # 契约：必须为 BE 生成的绝对路径
            raise ValueError(CODE_INVALID_VIDEO)
        if not vp.exists() or vp.stat().st_size == 0:
            raise ValueError(CODE_INVALID_VIDEO)

        duration = self._check_audio(vp)
        t0 = time.perf_counter()
        load_time = self._ensure_model()  # 首个任务包含模型加载
        seg_iter, info = self._model.transcribe(
            str(vp),
            language=self._language,
            beam_size=int(_env("WHISPER_BEAM_SIZE", "5")),
            vad_filter=_env("WHISPER_VAD_FILTER", "0") == "1",
        )
        raw = list(seg_iter)
        elapsed = time.perf_counter() - t0

        segments = []
        for s in raw:
            text = (s.text or "").strip()
            if not text:
                continue
            start = max(0.0, float(s.start))
            end = min(float(s.end), duration if duration > 0 else float(s.end))
            if math.isnan(start) or math.isnan(end) or end - start <= 0.01:
                continue
            segments.append(
                {"id": str(uuid.uuid4()), "start_sec": round(start, 3), "end_sec": round(end, 3), "text": text}
            )
        segments.sort(key=lambda x: x["start_sec"])
        if not segments:
            raise ValueError(CODE_NO_SPEECH)

        # 契约：先写 transcript.json（临时文件+原子替换），再向 BE 返回
        out = pathlib.Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        payload = {
            "segments": segments,
            "language": getattr(info, "language", None),
            "duration_sec": round(duration, 3),
            "elapsed_sec": round(elapsed, 3),
            "model_load_sec": round(load_time, 3) if load_time else None,
        }
        target = out / "transcript.json"
        tmp = out / "transcript.json.tmp"
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, target)

        return {
            "type": "ok",
            "segments": segments,
            "language": payload["language"],
            "duration_sec": payload["duration_sec"],
            "elapsed_sec": payload["elapsed_sec"],
            "transcript_path": str(target),
        }


def main() -> None:
    """子进程入口：stdin 逐行收 JSON 任务，stdout 逐行写 JSON 响应。"""
    sys.stdout.reconfigure(encoding="utf-8", write_through=True)
    sys.stdin.reconfigure(encoding="utf-8")
    worker = Worker()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            sys.stdout.write(json.dumps(_err(CODE_TRANSCRIBE_FAILED, f"bad request json: {exc}")) + "\n")
            sys.stdout.flush()
            continue
        cmd = req.get("cmd")
        try:
            if cmd == "warmup":
                model_load_sec = worker._ensure_model()  # noqa: SLF001
                sys.stdout.write(json.dumps({"type": "ok", "msg": "model ready", "model_load_sec": model_load_sec}) + "\n")
            elif cmd == "transcribe":
                out = worker.transcribe(req["video_path"], req["out_dir"])
                sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
            elif cmd == "ping":
                sys.stdout.write(json.dumps({"type": "ok", "msg": "pong"}) + "\n")
            elif cmd == "shutdown":
                sys.stdout.write(json.dumps({"type": "ok", "msg": "bye"}) + "\n")
                sys.stdout.flush()
                return
            else:
                sys.stdout.write(json.dumps(_err(CODE_TRANSCRIBE_FAILED, f"unknown cmd {cmd!r}")) + "\n")
        except ValueError as ve:
            # 受控错误：错误码原样上报
            sys.stdout.write(json.dumps(_err(str(ve), f"受控校验失败: {ve}")) + "\n")
        except Exception as exc:  # noqa: BLE001 其他异常归入 TRANSCRIBE_FAILED
            sys.stdout.write(json.dumps(_err(CODE_TRANSCRIBE_FAILED, f"{exc.__class__.__name__}: {exc}")) + "\n")
            traceback.print_exc(file=sys.stderr)
        sys.stdout.flush()


if __name__ == "__main__":
    main()
