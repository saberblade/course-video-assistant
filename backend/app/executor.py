"""SQLite 顺序任务执行器（SYS+BE 联合交付）。

职责（对应《API与数据模型契约》与 backend/README 交接清单）：
- 启动单个后台线程，按 updated_at/id 顺序取出最早的 queued 任务（重试按新 updated_at 排序）。
- 短事务认领：queued→transcribing，写入 started_at/updated_at；推断期间不持事务。
- 调用 modules/transcriber 的 sys.transcribe()（模块内部已有 1200 秒墙钟与真终止子进程逻辑）。
- 成功：事务内写 segments、调用 chapters.replace_chapters 建章、状态→ready、补 finished_at。
- 失败：按契约错误动作表写 error_code/message/retryable，状态→failed，double；
  local_path 丢失直接 SOURCE_MISSING（retryable=False，契约表）。
- 不提供伪造进度；只登记真实的阶段与耗时；日志不记录 Authorization/密钥/完整原文。

测试约定：环境变量 TASK_EXECUTOR_ENABLED=0 时 lifespan 不启动执行器
（backend/tests/conftest.py 已禁用，避免单测竞态）。
"""

from __future__ import annotations

import logging
import os
import threading
import time

from sqlalchemy import select, delete

from app.chapters import replace_chapters
from app.clock import utc_now
from app.models import Chapter, Question, Segment, Video

_log = logging.getLogger("course_review.executor")

RETRYABLE = {
    "NO_SPEECH": False,
    "INVALID_VIDEO": False,
    "AUDIO_REQUIRED": False,
    "SOURCE_MISSING": False,
    "MODEL_NOT_FOUND": True,
    "TRANSCRIBE_FAILED": True,
    "TASK_TIMEOUT": True,
    "PROCESS_INTERRUPTED": True,
    "CANCELLED": True,
}

THREAD_NAME = "task-executor"


class SerialTaskExecutor:
    """单并发转写执行器；生命周期随 FastAPI lifespan。"""

    def __init__(self, session_factory, logger: logging.Logger | None = None) -> None:
        self._session_factory = session_factory
        self._log = logger or _log
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._idle_wait = float(os.getenv("TASK_EXECUTOR_IDLE_SECONDS", "1.0"))
        self._timeout = float(os.getenv("TASK_TIMEOUT_SECONDS", "1200"))
        self._current_lock = threading.Lock()
        self._current_video_id: str | None = None
        self._transcribe = None  # 惰性导入
        self._cancel = None

    # ---------- 生命周期 ----------
    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name=THREAD_NAME, daemon=True)
        self._thread.start()
        # 契约要求启动时预热转写模块：后台加载模型，失败只记日志不阻塞服务
        preheat = threading.Thread(target=self._preheat, name="transcriber-preheat", daemon=True)
        preheat.start()
        self._log.info("executor started (preheat scheduled)")

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            # 转写模块 cancel_current 安全取消（不交叉持锁）；线程在自己的周期收尾
            try:
                from modules.transcriber import cancel_current

                cancel_current()
            except Exception:  # noqa: BLE001 模块可能尚未导入成功
                pass
            thread.join(timeout=timeout)
        self._thread = None
        try:
            from modules.transcriber import shutdown

            shutdown()
        except Exception:  # noqa: BLE001 未导入过则无需关闭
            pass
        self._log.info("executor stopped")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _preheat(self) -> None:
        """启动即预热：加载模型常驻子进程，避免第一个上传任务承担冷启动。"""
        try:
            from modules.transcriber import warmup

            began = time.perf_counter()
            warmup()
            self._log.info("transcriber preheat ok in %.2fs", time.perf_counter() - began)
        except Exception as exc:  # noqa: BLE001 预热失败不阻塞服务，首个任务再真实报错
            self._log.warning("transcriber preheat failed: %s: %s", exc.__class__.__name__, exc)

    def current_video_id(self) -> str | None:
        with self._current_lock:
            return self._current_video_id

    # ---------- 主循环 ----------
    def _run(self) -> None:
        while not self._stop.is_set():
            video_id = self._claim_next()
            if video_id is None:
                self._stop.wait(self._idle_wait)
                continue
            try:
                self._process(video_id)
            except Exception as exc:  # noqa: BLE001 执行器兜底：任务必须落终态
                self._log.exception("unexpected executor failure")
                self._fail(video_id, "TRANSCRIBE_FAILED", f"{exc.__class__.__name__}: {exc}", True)

    def _enter_indexing(self, video_id: str) -> None:
        db = self._session_factory()
        try:
            video = db.get(Video, video_id)
            if video is None:
                db.rollback()
                return
            if video.status != "transcribing":
                self._log.warning("task %s not in transcribing (=%s), skip indexing", video_id, video.status)
                db.rollback()
                return
            video.status = "indexing"
            video.updated_at = utc_now()
            db.commit()
        finally:
            db.close()

    # ---------- 认领 ----------
    def _claim_next(self) -> str | None:
        db = self._session_factory()
        try:
            row = db.scalars(
                select(Video).where(Video.status == "queued").order_by(Video.updated_at, Video.id).limit(1)
            ).first()
            if row is None:
                return None
            now = utc_now()
            row.status = "transcribing"
            row.updated_at = now
            row.started_at = now
            db.commit()
            return row.id
        except Exception:  # noqa: BLE001
            db.rollback()
            raise
        finally:
            db.close()

    # ---------- 处理 ----------
    def _process(self, video_id: str) -> None:
        with self._current_lock:
            self._current_video_id = video_id
        try:
            transcribe_path, resume = self._load_video(video_id)
            if resume:  # (_fail路径已完成提交)
                return
            audio_path, out_dir, duration = transcribe_path
            if self._transcribe is None:
                from modules.transcriber import transcribe, cancel_current  # noqa: F401 cancel 供 stop 使用

                self._transcribe = transcribe
                self._cancel = cancel_current

            t0 = time.perf_counter()
            try:
                segments = self._transcribe(audio_path, out_dir, timeout_sec=self._timeout)
            except Exception as exc:
                code = getattr(exc, "code", None)
                if code == "INVALID_VIDEO" and not os.path.exists(audio_path):
                    self._fail(video_id, "SOURCE_MISSING", "原视频文件丢失，无法转写", False)
                    return
                self._fail(
                    video_id,
                    code or "TRANSCRIBE_FAILED",
                    str(exc) or "转写失败",
                    RETRYABLE.get(code or "TRANSCRIBE_FAILED", True),
                )
                return

            # 校验分段（模块已校验，此处为库内兜底）
            segments = [s for s in segments if s["text"].strip() and s["end_sec"] > s["start_sec"] >= 0]
            if not segments:
                self._fail(video_id, "NO_SPEECH", "未能从音轨识别到可使用的讲课语音", False)
                return
            self._log.info(
                "transcription done video_id=%s segments=%d took=%.2fs", video_id, len(segments), time.perf_counter() - t0
            )

            self._enter_indexing(video_id)  # 契约阶段：transcribing→indexing（短事务，不持库做推理）

            db = self._session_factory()
            try:
                db.execute(delete(Segment).where(Segment.video_id == video_id))
                db.execute(delete(Chapter).where(Chapter.video_id == video_id))
                db.execute(delete(Question).where(Question.video_id == video_id))
                for seg in segments:
                    db.add(
                        Segment(
                            id=seg["id"],
                            video_id=video_id,
                            start_sec=seg["start_sec"],
                            end_sec=seg["end_sec"],
                            text=seg["text"],
                        )
                    )
                db.flush()  # session autoflush=False：先把分段落库，章节生成才能读到
                transcribe_rows = db.scalars(select(Segment).where(Segment.video_id == video_id)).all()
                chapters = replace_chapters(db, video_id, list(transcribe_rows), duration)
                db.commit()
                self._log.info("chapters saved video_id=%s count=%d", video_id, len(chapters))
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
            self._ready(video_id, len(segments))
        finally:
            with self._current_lock:
                self._current_video_id = None

    def _load_video(self, video_id: str):
        """取任务文件与时长；若文件丢失直接落 failed 返回 resume=True。"""
        db = self._session_factory()
        try:
            video = db.get(Video, video_id)
            if video is None:
                return None, True
            audio_path = video.local_path
            from pathlib import Path

            out_dir = str(Path(audio_path).parent)
            duration = float(video.duration_sec or 0)
            return (audio_path, out_dir, duration), False
        finally:
            db.close()

    # ---------- 状态推进 ----------
    def _ready(self, video_id: str, n_segments: int) -> None:
        db = self._session_factory()
        try:
            video = db.get(Video, video_id)
            if video is None:
                db.rollback()
                return
            if video.status not in ("transcribing", "indexing"):
                self._log.warning("task %s left processing state concurrently, keep=%s", video_id, video.status)
                db.rollback()
                return
            now = utc_now()
            video.status = "ready"
            video.error_code = None
            video.error_message = None
            video.error_retryable = None
            video.finished_at = now
            db.commit()
            self._log.info("task ready video_id=%s segments=%d", video_id, n_segments)
        finally:
            db.close()

    def _fail(self, video_id: str, code: str, message: str, retryable: bool) -> None:
        db = self._session_factory()
        try:
            video = db.get(Video, video_id)
            if video is None:
                db.rollback()
                return
            if video.status not in ("transcribing", "indexing"):
                self._log.warning("task %s already in state=%s, skip fail(%s)", video_id, video.status, code)
                db.rollback()
                return
            now = utc_now()
            video.status = "failed"
            video.error_code = code
            video.error_message = (message or "")[:290]
            video.error_retryable = 1 if retryable else 0
            video.finished_at = now
            db.commit()
            self._log.warning("task failed video_id=%s code=%s retryable=%s", video_id, code, retryable)
        finally:
            db.close()
