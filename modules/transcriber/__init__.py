# -*- coding: utf-8 -*-
"""
课程视频复习助手 转写模块（SYS）

公开 API：
    warmup()                          -> float | None      预热模型（幂等），返回本次模型加载秒数
    transcribe(video_path, out_dir)   -> list[dict]        同步等待；返回 [{id,start_sec,end_sec,text}]
    cancel_current()                  -> bool              看门狗使用：真正终止当前子进程任务并重启 worker
    shutdown()                        -> None              关闭可终止的专用子进程

行为契约（详见《API与数据模型契约》§SYS与BE的转写模块契约）：
- video_path / out_dir 必须是 BE 生成的绝对本地路径
- 转写放在"可终止的专用子进程"；超时/ cancel 真正 terminate 子进程并重启，不留后台推理
- 同一时刻仅 1 个活动调用；并发第二调用抛 TranscriberBusy
- 失败抛 TranscriberError（code 属于 INVALID_VIDEO / AUDIO_REQUIRED / TRANSCRIBE_FAILED /
  NO_SPEECH / TASK_TIMEOUT / MODEL_NOT_FOUND / PROCESS_INTERRUPTED / CANCELLED）
- 成功时：先写 out_dir/transcript.json（临时文件+原子替换，UTF-8），再返回分段列表
- 本模块不写业务 SQLite、不改业务状态（状态由 BE 统一维护）
"""
from __future__ import annotations

import atexit
import json
import os
import pathlib
import subprocess
import sys
import threading
import time
import uuid

__all__ = [
    "TranscriberError",
    "TranscriberBusy",
    "warmup",
    "transcribe",
    "cancel_current",
    "shutdown",
    "is_healthy",
]

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKER_ENTRY = REPO_ROOT / "modules" / "transcriber" / "_worker.py"

_CODES = {
    "INVALID_VIDEO",
    "AUDIO_REQUIRED",
    "TRANSCRIBE_FAILED",
    "NO_SPEECH",
    "TASK_TIMEOUT",
    "MODEL_NOT_FOUND",
    "PROCESS_INTERRUPTED",
    "CANCELLED",
    "BUSY",
}


class TranscriberError(Exception):
    """受控转写异常；code 与契约错误码一一对应。"""

    def __init__(self, code: str, message: str = ""):
        super().__init__(f"[{code}] {message}" if message else f"[{code}]")
        self.code = code if code in _CODES else "TRANSCRIBE_FAILED"
        self.message = message


class TranscriberBusy(Exception):
    """同一时刻仅 1 个转写可活动；BE 前置 TRANSCRIBE_CONCURRENCY=1 不应触发。"""


_state_lock = threading.RLock()
_state: dict = {
    "proc": None,          # subprocess.Popen 或 None
    "task_lock": threading.Lock(),  # 保证一次只有一个活动调用
    "active": False,       # 易读状态标记
    "env": None,           # 子进程环境缓存
}


def _subprocess_env() -> None:
    """确保子进程能 import 仓库内模块：注入 cwd 与 PYTHONPATH。"""
    env = os.environ.copy()
    py_path = env.get("PYTHONPATH", "")
    parts = [str(REPO_ROOT)] + ([py_path] if py_path else [])
    env["PYTHONPATH"] = os.pathsep.join(parts)
    env["PYTHONIOENCODING"] = "utf-8"
    _state["env"] = env


def _spawn_worker():
    proc = subprocess.Popen(
        [sys.executable, "-X", "utf8", str(WORKER_ENTRY)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(REPO_ROOT),
        env=_state["env"],
        text=True,
        encoding="utf-8",
        bufsize=1,  # 行缓冲
    )
    _state["proc"] = proc
    return proc


def _ask(payload: dict) -> dict:
    """向 worker 发送一项任务并等待响应；通信失败归入 PROCESS_INTERRUPTED。"""
    proc = _state["proc"]
    if proc is None or proc.poll() is not None:
        _spawn_worker()
        proc = _state["proc"]
    assert proc is not None and proc.stdin is not None and proc.stdout is not None
    line = json.dumps(payload, ensure_ascii=False)
    try:
        proc.stdin.write(line + "\n")
        proc.stdin.flush()
        resp_raw = proc.stdout.readline()
    except (OSError, ValueError) as exc:
        raise TranscriberError("PROCESS_INTERRUPTED", f"worker 通信失败: {exc}")

    if not resp_raw:
        # worker 已退出（可能在处理中崩溃）
        stderr_tail = ""
        if proc.stderr is not None:
            try:
                stderr_tail = (proc.stderr.read() or "")[-600:]
            except Exception:  # noqa: BLE001
                pass
        _cleanup_worker()
        raise TranscriberError("PROCESS_INTERRUPTED", f"worker 提前退出 rc={proc.poll()} stderr≈{stderr_tail!r}")
    try:
        return json.loads(resp_raw)
    except json.JSONDecodeError as exc:
        _cleanup_worker()
        raise TranscriberError("PROCESS_INTERRUPTED", f"worker 响应不可解析: {exc} / raw={resp_raw[:200]!r}")


def _cleanup_worker() -> None:
    """由父进程真正终止并回收 worker 子进程；不留残留进程。"""
    proc = _state["proc"]
    _state["proc"] = None
    if proc is None:
        return
    try:
        if proc.stdin:
            proc.stdin.close()
    except Exception:  # noqa: BLE001
        pass
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:  # noqa: BLE001
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass


def _tmp_dirs_clean(output_dir: str | None) -> None:
    """取消/超时之后清理未完成的临时产物（transcript.json.tmp）。"""
    if not output_dir:
        return
    tmp = pathlib.Path(output_dir) / "transcript.json.tmp"
    try:
        if tmp.exists():
            tmp.unlink()
    except OSError:
        pass


def warmup() -> float | None:
    """预热模型；幂等。若已有任务在跑则等待其结束后再预热。

    返回本次（若有）模型加载秒数。
    """
    _state["task_lock"].acquire()  # 与 transcribe 串行，避免同时写 worker stdin
    try:
        with _state_lock:
            _subprocess_env()
            resp = _ask({"cmd": "warmup"})
    finally:
        _state["task_lock"].release()
    if resp.get("type") != "ok":
        raise TranscriberError(resp.get("code", "TRANSCRIBE_FAILED"), resp.get("message", ""))
    return resp.get("model_load_sec")


def is_healthy() -> bool:
    """健康检查用：worker 进程存在且能 ping 通（不触发付费/网络行为）。"""
    with _state_lock:
        proc = _state["proc"]
        if proc is None or proc.poll() is not None:
            return False
        try:
            resp = _ask({"cmd": "ping"})
            return resp.get("type") == "ok"
        except TranscriberError:
            return False


def transcribe(video_path: str, output_dir: str, timeout_sec: float | None = None) -> list[dict]:
    """同步转写：阻塞直至完成；返回带 UUID、秒数、非空文本的分段列表（start_sec 升序）。

    timeout_sec 默认取环境 TASK_TIMEOUT_SECONDS（契约 1200）；超时/
    cancel 采用真正终止子进程的方式，随后自动重启 worker 以便后续任务。
    """
    deadline = timeout_sec if timeout_sec else float(os.environ.get("TASK_TIMEOUT_SECONDS", "1200"))
    if deadline <= 0:
        deadline = 1200.0

    # 并发防御：一次只允许一个活动调用。
    # 但不能"抢不到就报错"——启动预热（warmup）会短暂占用同一把锁加载模型，
    # 此时刚到队的任务应当等它让出锁，而不是被判成 TRANSCRIBE_FAILED。
    wait_seconds = float(os.environ.get("TRANSCRIBE_LOCK_WAIT_SECONDS", "180"))
    if not _state["task_lock"].acquire(timeout=wait_seconds):
        raise TranscriberBusy("已有转写任务进行中，请稍后重试")
    _state["active"] = True
    try:
        with _state_lock:
            _subprocess_env()

        vp = pathlib.Path(video_path)
        if not vp.is_absolute():
            raise TranscriberError("INVALID_VIDEO", "video_path 必须为绝对路径（由 BE 生成）")
        if not vp.exists() or vp.stat().st_size == 0:
            raise TranscriberError("INVALID_VIDEO", f"视频文件不存在: {vp}")
        od = pathlib.Path(output_dir)
        if not od.is_absolute():
            raise TranscriberError("INVALID_VIDEO", "output_dir 必须为绝对路径（由 BE 生成）")

        result_holder: dict = {}
        t0 = time.perf_counter()

        from threading import Thread

        def _run():
            result_holder["resp"] = _ask(
                {"cmd": "transcribe", "video_path": str(vp), "out_dir": str(od)},
            )

        th = Thread(target=_run, daemon=True)
        th.start()
        # 等待 + 看门狗
        th.join(timeout=deadline)
        if th.is_alive():
            # 契约：真终止子进程并清理临时文件；之后 worker 可自动重启
            _cleanup_worker()
            _tmp_dirs_clean(output_dir)
            raise TranscriberError("TASK_TIMEOUT", f"转写超过 {deadline:.0f}s 墙钟期限，任务已终止")

        resp = result_holder.get("resp")
        elapsed = time.perf_counter() - t0
        if not resp:
            _cleanup_worker()
            raise TranscriberError("PROCESS_INTERRUPTED", "worker 无响应")

        if resp.get("type") == "ok":
            segments = resp.get("segments") or []
            if not segments:
                # 防御：worker 不应走到这里
                raise TranscriberError("NO_SPEECH", "转写结果为空")
            # 契约字段完整性校验（时间单位秒；uuid；非空文本；有序）
            if not all(
                s.get("id") and isinstance(s.get("text"), str) and s["text"].strip()
                and isinstance(s.get("start_sec"), (int, float)) and isinstance(s.get("end_sec"), (int, float))
                and s["end_sec"] > s["start_sec"] >= 0
                for s in segments
            ):
                raise TranscriberError("TRANSCRIBE_FAILED", "worker 输出未通过字段校验")
            segments.sort(key=lambda x: x["start_sec"])
            resp["total_wall_sec"] = round(elapsed, 3)
            return segments

        code = resp.get("code", "TRANSCRIBE_FAILED")
        raise TranscriberError(code, resp.get("message", ""))
    finally:
        _state["active"] = False
        _state["task_lock"].release()


def cancel_current() -> bool:
    """供 BE 1200 秒看门狗调用：真终止当前任务。

    注意：不获取任务锁（否则与被取消的 transcribe 互相等待）；
    只看 _state["active"] 标记。终止后后续调用会自动重启 worker。
    返回 True 表示确实终止了一个进行中的任务。
    """
    if not _state["active"]:
        return False
    proc = _state["proc"]
    if proc is None:
        return False
    _cleanup_worker()
    return True


def shutdown() -> None:
    """关闭可终止的专用子进程（BE 服务退出时调用）。幂等。"""
    with _state_lock:
        _cleanup_worker()


@atexit.register
def _atexit_shutdown():  # pragma: no cover
    """Python 退出时兜底停 worker，避免后台推理进程残留。"""
    try:
        shutdown()
    except Exception:  # noqa: BLE001
        pass
