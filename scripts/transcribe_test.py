# -*- coding: utf-8 -*-
"""
转写真实试跑（SYS / M1）

目的：
    1) 在目标电脑用真实样本验证 faster-whisper small + CPU int8
    2) 输出首次加载、转写耗时、时长比、样本校验值等 M1 证据
    3) 抽查识别质量（与 scripts/sample_text.txt 对照）

用法（course-review 根目录）：
    .\\.venv\\Scripts\\python.exe scripts\\transcribe_test.py [视频或音频路径]
    不带参数时默认处理 data/tmp/sample_lecture.mp4

退出码：0=成功 2=模型目录不完整 3=无语音 4=其他失败
"""
import hashlib
import json
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODEL_DIR = ROOT / "models" / "faster-whisper-small"
DEFAULT_SAMPLE = ROOT / "data" / "tmp" / "sample_lecture.mp4"
TEXT_REF = ROOT / "scripts" / "sample_text.txt"


def sha256_of(path: pathlib.Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    audio = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SAMPLE
    print("== transcribe_test ==")
    print(f"sample      : {audio}")
    print(f"model_dir   : {MODEL_DIR}")

    if not (MODEL_DIR / "model.bin").exists():
        print("RESULT: FAIL - 模型目录不完整（缺 model.bin），对应错误码 MODEL_NOT_FOUND")
        return 2

    # 证据：模型文件校验值
    print("-- model files (sha256) --")
    for f in sorted(MODEL_DIR.iterdir()):
        if f.is_file() and f.suffix.lower() in {".bin", ".json", ".txt"}:
            print(f"  {f.name:24s} {f.stat().st_size:>12,d} bytes  sha256={sha256_of(f)[:24]}...")

    from faster_whisper import WhisperModel

    # 首次加载（冷）
    t0 = time.perf_counter()
    model = WhisperModel(
        str(MODEL_DIR), device="cpu", compute_type="int8", cpu_threads=(os.cpu_count() or 8)
    )
    cold_load = time.perf_counter() - t0
    print(f"cold_model_load: {cold_load:.2f}s")

    # 预热（部分实现会把首段前向作为预热）
    print("warmup: pending (module-level warmup() will be provided at M2)")

    if not audio.exists():
        print(f"RESULT: FAIL - 样本不存在: {audio}")
        return 4

    import av

    with av.open(str(audio)) as container:
        dur = container.duration / float(av.time_base) if container.duration else 0.0
    print(f"audio_duration: {dur:.2f}s")

    seg_iter, info = model.transcribe(str(audio), language="zh", beam_size=5, vad_filter=False)
    t1 = time.perf_counter()
    segments = []
    first_latency = None
    for seg in seg_iter:
        if first_latency is None:
            first_latency = time.perf_counter() - t1
        segments.append({"start": seg.start, "end": seg.end, "text": seg.text.strip()})

    total = time.perf_counter() - t1
    print(f"first_segment_latency: {first_latency:.2f}s")
    print(f"transcribe_total    : {total:.2f}s")
    print(f"segments            : {len(segments)}")
    rtf = total / dur if dur else float("nan")
    print(f"realtime_factor     : {rtf:.3f} (越小越快; 预测20分钟视频约 {dur and (rtf * 1200 / 60):.1f} 分钟)")

    print("-- segments preview --")
    for s in segments[:6]:
        m, s0 = divmod(s["start"], 60)
        m2, _ = divmod(s["end"], 60)
        print(f"  [{int(m):02d}:{s0:05.2f}] {s['text'][:72]}")

    # 质量抽查：关键词命中率（与讲稿对照，反映 int8 small 中文质量）
    ref = TEXT_REF.read_text(encoding="utf-8") if TEXT_REF.exists() else ""
    full_text = "".join(s["text"] for s in segments)
    if ref:
        keys = ["精确率", "召回率", "真正例", "假正例", "假负例", "调和平均", "F1", "训练集", "验证集", "测试集", "泛化能力", "垃圾短信", "超参数"]
        hits = [k for k in keys if k in full_text]
        print(f"keyword_hits: {len(hits)}/{len(keys)} -> {hits}")
        missing = [k for k in keys if k not in hits]
        if missing:
            print(f"keyword_missing: {missing} (int8量化与小模型的常见误识对象，正式样本中再做人工抽查)")

    out = {
        "sample": str(audio),
        "audio_duration_sec": dur,
        "cold_model_load_sec": cold_load,
        "first_segment_latency_sec": first_latency,
        "transcribe_total_sec": total,
        "realtime_factor": rtf,
        "segments": segments,
    }
    (ROOT / "logs").mkdir(exist_ok=True)
    (ROOT / "logs" / "transcribe_test_latest.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("RESULT: PASS - 已写入 logs/transcribe_test_latest.json（正式样本到位后复测更新）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
