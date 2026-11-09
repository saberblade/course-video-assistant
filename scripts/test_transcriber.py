# -*- coding: utf-8 -*-
"""
transcriber 模块验收（SYS → BE/QA 交接）

覆盖契约要点：
  A. warmup 预热（幂等、可计时）
  B. transcribe 正常路径：字段完整（UUID/秒/非空文本/升序）、transcript.json 原子落盘
  C. 并发防御：活动期间第二调用 → TranscriberBusy
  D. 超时/取消：真正终止子进程（TASK_TIMEOUT），不留残留进程，之后可恢复使用
  E. 受控错误：不存在文件 INVALID_VIDEO；无音轨样本 AUDIO_REQUIRED；损坏文件 INVALID_VIDEO
  F. shutdown 关闭；is_healthy 状态

运行（course-review 根目录）：
    .\\.venv\\Scripts\\python.exe -X utf8 scripts\\test_transcriber.py
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # 让 `import modules.transcriber` 可用

SAMPLE_MP4 = ROOT / "data" / "tmp" / "sample_lecture.mp4"
NO_AUDIO_MP4 = ROOT / "data" / "tmp" / "sample_no_audio.mp4"
CORRUPT_MP4 = ROOT / "data" / "tmp" / "sample_corrupt.mp4"
OUT_DIR = ROOT / "data" / "tmp" / "transcribe_out"

RESULTS: list[tuple[str, str, str]] = []  # (name, PASS/FAIL, note)


def check(name: str, fn):
    t0 = time.perf_counter()
    try:
        note = fn() or "ok"
        RESULTS.append((name, "PASS", note))
        print(f"[PASS] {name}  ({note})  {time.perf_counter() - t0:.2f}s")
    except Exception as exc:  # noqa: BLE001
        RESULTS.append((name, "FAIL", f"{exc}"))
        print(f"[FAIL] {name}  ({exc})")


def ensure_samples() -> None:
    """准备两个受控错误样本：无音轨 MP4、损坏 MP4（用文本重命名模拟）。"""
    ffmpeg = ROOT / "tools" / "ffmpeg" / "ffmpeg.exe"
    if not NO_AUDIO_MP4.exists() and ffmpeg.exists():
        subprocess.run(
            [str(ffmpeg), "-hide_banner", "-y", "-f", "lavfi", "-i",
             "color=c=red:s=320x240:r=10", "-t", "3", "-an", str(NO_AUDIO_MP4)],
            check=True, capture_output=True,
        )
    if not CORRUPT_MP4.exists():
        CORRUPT_MP4.write_text("this is not a video", encoding="utf-8")


def test_warmup() -> str:
    import modules.transcriber as T

    t1 = T.warmup()
    t2 = T.warmup()
    assert t1 is not None and t2 is None, f"warmup 应首次计时后续幂等: {t1}, {t2}"
    assert 0 < t1 < 60, f"首次模型加载秒数异常: {t1}"
    return f"首次加载 {t1:.2f}s"


def test_transcribe_ok() -> str:
    import modules.transcriber as T

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    segs = T.transcribe(str(SAMPLE_MP4), str(OUT_DIR))
    wall = time.perf_counter() - t0
    assert isinstance(segs, list) and len(segs) > 0, "结果必须非空列表"
    for s in segs:
        assert s["id"] and len(s["id"]) == 36, f"id 必须为 UUID: {s.get('id')}"
        assert isinstance(s["text"], str) and s["text"].strip(), "text 必须非空"
        assert s["end_sec"] > s["start_sec"] >= 0, f"时间非法: {s}"
    starts = [s["start_sec"] for s in segs]
    assert starts == sorted(starts), "分段必须按 start_sec 升序"

    tj = OUT_DIR / "transcript.json"
    assert tj.exists(), "必须先写 transcript.json 再返回"
    doc = json.loads(tj.read_text(encoding="utf-8"))
    assert len(doc["segments"]) == len(segs), "transcript.json 与返回列表长度不一致"
    assert not (OUT_DIR / "transcript.json.tmp").exists(), "不应残留 .tmp 文件"
    return f"{len(segs)} 段 / 墙钟 {wall:.1f}s / transcript.json ✓"


def test_busy() -> str:
    import modules.transcriber as T

    holder: dict = {}

    def long_call():
        try:
            holder["segs"] = T.transcribe(str(SAMPLE_MP4), str(OUT_DIR), timeout_sec=4)
        except Exception as exc:  # noqa: BLE001
            holder["err"] = exc

    th = threading.Thread(target=long_call, daemon=True)
    th.start()
    time.sleep(0.8)  # 让第一个任务进入活动状态
    try:
        T.transcribe(str(SAMPLE_MP4), str(OUT_DIR))
        th.join(timeout=30)
        raise AssertionError("并发第二调用未被拒绝")
    except T.TranscriberBusy:
        th.join(timeout=30)
        err = holder.get("err")
        assert err is not None and getattr(err, "code", "") == "TASK_TIMEOUT", (
            f"首个调用应因看门狗超时终止: {err}"
        )
        return "busy 拒绝 ✓ + 超时真终止 TASK_TIMEOUT ✓"
    finally:
        th.join(timeout=30)


def test_cancel_then_recover() -> str:
    import modules.transcriber as T

    holder: dict = {}

    def long_call():
        try:
            holder["segs"] = T.transcribe(str(SAMPLE_MP4), str(OUT_DIR), timeout_sec=3000)
        except Exception as exc:  # noqa: BLE001
            holder["err"] = exc

    th = threading.Thread(target=long_call, daemon=True)
    th.start()
    time.sleep(1.0)
    cancelled = T.cancel_current()
    assert cancelled is True, "cancel_current 应返回 True"
    th.join(timeout=40)
    err = holder.get("err")
    assert err is not None and getattr(err, "code", "") in {"PROCESS_INTERRUPTED", "TASK_TIMEOUT"}, (
        f"取消后应有受控异常: {err}"
    )
    # 恢复：下一次调用自动重启 worker 并正常工作
    segs = T.transcribe(str(SAMPLE_MP4), str(OUT_DIR), timeout_sec=240)
    assert len(segs) > 0
    return f"取消→{err.code}→重启恢复成功({len(segs)}段)"


def test_invalid_video() -> str:
    import modules.transcriber as T

    try:
        T.transcribe(str(ROOT / "不存在文件.mp4"), str(OUT_DIR))
        raise AssertionError("不存在的文件未触发 INVALID_VIDEO")
    except T.TranscriberError as e:
        assert e.code == "INVALID_VIDEO", f"应报 INVALID_VIDEO: {e.code}"
    try:
        T.transcribe(str(CORRUPT_MP4), str(OUT_DIR))
        raise AssertionError("损坏文件未触发 INVALID_VIDEO")
    except T.TranscriberError as e:
        assert e.code == "INVALID_VIDEO", f"应报 INVALID_VIDEO: {e.code}"
    return "不存在/损坏 → INVALID_VIDEO ✓"


def test_audio_required() -> str:
    import modules.transcriber as T

    assert NO_AUDIO_MP4.exists(), "缺无音轨样本（需 tools/ffmpeg）"
    try:
        T.transcribe(str(NO_AUDIO_MP4), str(OUT_DIR))
        raise AssertionError("无音轨样本未触发 AUDIO_REQUIRED")
    except T.TranscriberError as e:
        assert e.code == "AUDIO_REQUIRED", f"应报 AUDIO_REQUIRED: {e.code}"
    return "无音轨 → AUDIO_REQUIRED ✓"


def test_shutdown() -> str:
    import modules.transcriber as T

    T.warmup()
    assert T.is_healthy(), "shutdown 前 worker 应健康"
    T.shutdown()
    assert T.is_healthy() is False, "shutdown 后 worker 应不可用"
    return "shutdown ✓ is_healthy ✓"


def main() -> int:
    print("== transcriber 模块验收 ==")
    print(f"sample: {SAMPLE_MP4}")
    if not SAMPLE_MP4.exists():
        print("缺少样本：先运行 scripts\\make_sample_video.ps1")
        return 2
    ensure_samples()

    # 顺序执行（模块有并发互斥约束，测试也保持顺序）
    for name, fn in [
        ("warmup 预热", test_warmup),
        ("transcribe 正常路径", test_transcribe_ok),
        ("busy 并发防御 + 超时终止", test_busy),
        ("cancel_current 取消恢复", test_cancel_then_recover),
        ("无效视频受控错误", test_invalid_video),
        ("无音轨受控错误", test_audio_required),
        ("shutdown 关闭", test_shutdown),
    ]:
        check(name, fn)

    passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
    print(f"== 汇总: {passed}/{len(RESULTS)} ==")
    out = {"results": [{"name": n, "status": s, "note": nt} for n, s, nt in RESULTS]}
    (ROOT / "logs").mkdir(exist_ok=True)
    (ROOT / "logs" / "transcriber_acceptance.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("证据已存: logs/transcriber_acceptance.json")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
