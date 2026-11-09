# -*- coding: utf-8 -*-
"""
model.bin 多线程分块下载器（SYS / M1 环境准备）

背景：hf-mirror 单线程仅 ~25-40KB/s，huggingface_hub 下载反复卡断。
方案：对固定 revision 的 model.bin 发起 16 路并发 Range 请求，
     每段独立写盘并用 .segN.ok 状态文件断点续传，全部完成后用
     HF API 返回的 LFS sha256 校验后落为正式 model.bin。

用法（course-review 根目录）：
    .\\.venv\\Scripts\\python.exe scripts\\download_model_bin.py
"""
import hashlib
import json
import os
import pathlib
import sys
import threading
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODEL_DIR = ROOT / "models" / "faster-whisper-small"
REPO = "Systran/faster-whisper-small"
REVISION = "536b0662742c02347bc0e980a01041f333bce120"
URL = f"https://hf-mirror.com/{REPO}/resolve/{REVISION}/model.bin"
WORK = MODEL_DIR / ".binwork"
TARGET = MODEL_DIR / "model.bin"
N_SEG = 16
UA = {"User-Agent": "Mozilla/5.0 tool-downloader/1.0"}


def get_json_tree():
    url = f"https://hf-mirror.com/api/models/{REPO}/tree/{REVISION}?recursive=true"
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.load(r)


def fetch_range(start: int, end: int, seg: int, total: int, stats):
    """下载一段；已存在 .ok 则跳过；每次重试从段内已写字节续传。"""
    ok_marker = WORK / f".seg{seg}.ok"
    part = WORK / f"model.bin.part{seg}"
    expected = end - start + 1
    if ok_marker.exists() and part.exists() and part.stat().st_size == expected:
        return
    written = part.stat().st_size if part.exists() else 0
    for attempt in range(1, 51):
        try:
            headers = dict(UA)
            headers["Range"] = f"bytes={start + written}-{end}"
            req = urllib.request.Request(URL, headers=headers)
            # 注意：urllib 的 timeout 只接受单个数值（连接与读共用）
            with urllib.request.urlopen(req, timeout=60) as resp:
                with open(part, "ab") as f:
                    while written < expected:
                        chunk = resp.read(1 << 18)  # 256KB
                        if not chunk:
                            break
                        f.write(chunk)
                        f.flush()
                        written += len(chunk)
                        stats["bytes"] += len(chunk)
            if written >= expected:
                ok_marker.write_text("ok")
                print(f"segment {seg}: done ({expected} bytes)", flush=True)
                return
        except Exception as exc:  # noqa: BLE001 - 网络异常必须重试
            print(f"segment {seg} attempt {attempt}: {exc}", flush=True)
            part = WORK / f"model.bin.part{seg}"
            written = part.stat().st_size if part.exists() else 0
            time.sleep(min(30, 2 * attempt))
            continue
    raise RuntimeError(f"segment {seg} failed after max retries")


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)

    # 1) 元数据：LFS sha256 + 总大小
    print("fetching file metadata via hf-mirror API ...", flush=True)
    tree = get_json_tree()
    entry = next(item for item in tree if item.get("path") == "model.bin")
    lfs = entry.get("lfs") or {}
    expect_size = int(entry.get("size") or lfs.get("size") or 0)
    expect_sha = lfs.get("oid")
    print(f"size={expect_size}  lfs_sha256={expect_sha}", flush=True)
    if not expect_size:
        # 兜底：用 Range 探测
        req = urllib.request.Request(URL, method="HEAD", headers=UA)
        with urllib.request.urlopen(req, timeout=60) as r:
            cr = r.headers.get("Content-Range") or ""
            expect_size = int(cr.split("/")[-1]) if cr else 0
        print(f"size(fallback)={expect_size}", flush=True)

    if TARGET.exists() and TARGET.stat().st_size == expect_size and expect_sha:
        h = hashlib.sha256()
        with open(TARGET, "rb") as f:
            for blk in iter(lambda: f.read(1 << 22), b""):
                h.update(blk)
        if h.hexdigest() == expect_sha:
            print("RESULT: PASS - model.bin 已存在且校验通过")
            return 0

    # 2) 并发分块
    seg_size = expect_size // N_SEG
    ranges = [(i * seg_size, (i + 1) * seg_size - 1) for i in range(N_SEG)]
    ranges[-1] = (ranges[-1][0], expect_size - 1)  # 末段收敛

    stats = {"bytes": 0, "t0": time.time(), "lock": threading.Lock()}

    def bump(n):
        with stats["lock"]:
            stats["bytes"] += n
    # 注：fetch_range 内部直接统计，不使用 bump

    def runner(start, end, seg):
        fetch_range(start, end, seg, expect_size, stats)

    print(f"downloading {expect_size:,} bytes with {N_SEG} threads ...", flush=True)
    t_start = time.time()
    threads = [threading.Thread(target=runner, args=(*r, i), daemon=True) for i, r in enumerate(ranges)]
    for t in threads:
        t.start()
    done = False
    while not done:
        alive = sum(1 for t in threads if t.is_alive())
        elapsed = time.time() - t_start
        got = sum(p.stat().st_size for p in WORK.glob("model.bin.part*") if p.exists())
        want = sum(e - s + 1 for s, e, *_ in ranges)
        print(f"progress: {got:,}/{want:,} ({got / want * 100:.1f}%)  {got / 1024 / elapsed:.0f} KB/s  alive={alive}", flush=True)
        done = alive == 0
        if not done:
            time.sleep(15)
    for t in threads:
        t.join()

    # 3) 合并 + 校验
    print("merging segments ...", flush=True)
    h = hashlib.sha256()
    with open(TARGET, "wb") as out:
        for i, (start, end) in enumerate(ranges):
            part = WORK / f"model.bin.part{i}"
            pm = WORK / f".seg{i}.ok"
            if not pm.exists():
                print(f"RESULT: FAIL - segment {i} 缺少完成标记")
                return 4
            with open(part, "rb") as f:
                for blk in iter(lambda: f.read(1 << 22), b""):
                    out.write(blk)
                    h.update(blk)

    if expect_sha and h.hexdigest() != expect_sha:
        print(f"RESULT: FAIL - sha256 不匹配: {h.hexdigest()} != {expect_sha}")
        TARGET.unlink(missing_ok=True)
        return 5

    for p in WORK.glob("*"):
        p.unlink()
    print(f"RESULT: PASS - model.bin {TARGET.stat().st_size:,} bytes, sha256={h.hexdigest()}, 用时 {time.time() - t_start:.0f}s")
    (ROOT / "logs").mkdir(exist_ok=True)
    (ROOT / "logs" / "model_download_done.txt").write_text(
        f"size={TARGET.stat().st_size}\nsha256={h.hexdigest()}\nsource={URL}\nthreads={N_SEG}\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("中断：可重新运行脚本继续断点续传")
        sys.exit(130)
