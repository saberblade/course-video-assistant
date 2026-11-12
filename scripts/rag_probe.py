# -*- coding: utf-8 -*-
"""RAG 混合检索真机探测（SYS-01/SYS-02 证据生成器）。

流程：
1) HTTP：确认服务在线；库内无 ready 视频时自动上传 data/tmp/sample_lecture.mp4 并等待转写完成
2) DB/模块：确保向量索引已构建（真实百炼 text-embedding-v4 调用，密钥取自服务端 .env.local）
3) 检索对照：A=基线 60 秒窗 BM25；B=新块 BM25（chunks_v1）；C=BM25+向量 RRF
   每题记录 Hit@1 / MRR / 候选数 / 耗时 / 缓存命中；C 对首题连跑两次验证查询缓存
4) 证据写入 logs/rag_probe.json，控制台输出摘要

用法（仓库根目录，服务已启动）：
    .\\.venv\\Scripts\\python.exe scripts\\rag_probe.py [video_id]

注意：本脚本只读业务库并构建向量索引，不删除任何数据；不上传密钥到任何日志。
"""

from __future__ import annotations

import json
import pathlib
import sys
import time

import httpx

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

BASE = "http://127.0.0.1:8000"
OUT = ROOT / "logs" / "rag_probe.json"
SAMPLE = ROOT / "data" / "tmp" / "sample_lecture.mp4"

# 探测题组：kw 是"支持片段判定关键词"（出现即认定该块支持本题）
QUESTIONS = [
    {"q": "召回率的定义是什么", "kw": "召回率", "tag": "原词题"},
    {"q": "正类样本被成功找出来的比例对应哪个指标", "kw": "召回率", "tag": "同义改写A"},
    {"q": "哪个指标说明漏掉的真正例越少越好", "kw": "召回率", "tag": "同义改写B"},
    {"q": "测试集能不能参与模型的调参过程", "kw": "测试集", "tag": "原词题"},
    {"q": "卷积神经网络一共有多少层", "kw": None, "tag": "无依据题"},
]


def _mrr(hits, kw) -> float:
    if kw is None:
        return 0.0
    for rank, hit in enumerate(hits, start=1):
        if kw in hit.text:
            return 1.0 / rank
    return 0.0


def _hit_at(hits, kw, k: int) -> int:
    if kw is None:
        return 0
    return 1 if any(kw in hit.text for hit in hits[:k]) else 0


def _summarize(tag: str, outcome) -> dict:
    hits = outcome.hits
    return {
        "mode_used": outcome.mode_used,
        "hit1": None,
        "mrr": None,
        "hits_count": len(hits),
        "top_text": hits[0].text[:60] if hits else "",
        "top_segment_ids": hits[0].segment_ids if hits else [],
        "diagnostics": outcome.diagnostics,
    }


def wait_ready(client: httpx.Client, video_id: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"{BASE}/api/videos/{video_id}").json()
        status = body.get("status")
        if status == "ready":
            return
        if status == "failed":
            raise RuntimeError(f"视频处理失败: {body}")
        time.sleep(3)
    raise RuntimeError("等待转写完成超时")


def main() -> int:
    from app.config import load_local_env

    load_local_env()
    with httpx.Client(timeout=120) as client:
        health = client.get(f"{BASE}/api/health")
        if health.status_code != 200:
            print("RESULT: FAIL - 服务未运行")
            return 2
        videos = client.get(f"{BASE}/api/videos").json()
        items = videos.get("items", [])
        target = None
        if len(sys.argv) > 1:
            target = next((v for v in items if v["id"] == sys.argv[1]), None)
            if target is None:
                print("RESULT: FAIL - 指定的视频不存在")
                return 2
        else:
            ready = [v for v in items if v["status"] == "ready"]
            if ready:
                target = sorted(ready, key=lambda v: v["created_at"], reverse=True)[0]
        if target is None:
            if not SAMPLE.exists():
                print("RESULT: FAIL - 库内无 ready 视频，且缺少样本文件（先跑 scripts\\make_sample_video.ps1）")
                return 2
            print("上传样本并等待转写 ...")
            with SAMPLE.open("rb") as handle:
                upload = client.post(f"{BASE}/api/videos", files={"file": (SAMPLE.name, handle, "video/mp4")})
            if upload.status_code != 202:
                print(f"RESULT: FAIL - 上传失败 {upload.status_code}: {upload.text[:200]}")
                return 2
            target = {"id": upload.json()["id"]}
        video_id = target["id"]
        wait_ready(client, video_id, timeout=240)
        print(f"目标视频 ready: {video_id}")

    # ---------- 模块阶段：真实索引 + A/B/C 对照 ----------
    from app.config import get_settings
    from app.database import make_engine, session_factory_for
    from app.models import Segment, Video
    from app.retrieval import search_segments
    from modules.retriever.hybrid import retrieve, _QUERY_CACHE
    from modules.retriever.service import IndexService
    from sqlalchemy import select

    settings = get_settings()
    engine = make_engine(settings.database_path)
    factory = session_factory_for(engine)

    db = factory()
    try:
        video = db.get(Video, video_id)
        segments = db.scalars(
            select(Segment).where(Segment.video_id == video_id).order_by(Segment.start_sec, Segment.id)
        ).all()
        duration = float(video.duration_sec or 0)
    finally:
        db.close()

    service = IndexService(factory)
    db = factory()
    try:
        status = IndexService.get_status(db, video_id)
        print(f"索引状态(建前): {status['index_status']} chunks={status['chunk_count']}")
        if status["index_status"] in ("absent", "failed"):
            service.enqueue(db, video_id)  # ready 则不动；pending/building 交给服务端线程
    finally:
        db.close()

    # 等服务端索引线程完成（若 RAG_INDEXING_ENABLED=0 则无人在做，走超时后自建）
    waited = 0.0
    while waited < 90:
        db = factory()
        try:
            status = IndexService.get_status(db, video_id)
        finally:
            db.close()
        if status["index_status"] == "ready":
            break
        if status["index_status"] == "failed":
            print(f"RESULT: WARN - 服务端索引失败({status['last_error']})，探测进程直接重建")
            break
        time.sleep(2)
        waited += 2

    build_started = time.perf_counter()
    if status["index_status"] != "ready" and not service.build(video_id):
        print("RESULT: FAIL - 索引构建未成功（见 rag_indexes.last_error）")
        engine.dispose()
        return 3
    build_seconds = round(time.perf_counter() - build_started, 2)
    db = factory()
    try:
        status = IndexService.get_status(db, video_id)
    finally:
        db.close()
    print(f"索引 ready: chunks={status['chunk_count']} model={status['model']} dim={status['dimension']} build={build_seconds}s")

    report = {
        "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "video_id": video_id,
        "segments": len(segments),
        "index": {key: status[key] for key in ("index_status", "index_version", "model", "dimension", "chunking_version", "chunk_count")},
        "build_seconds": build_seconds,
        "questions": [],
    }

    for question in QUESTIONS:
        q = question["q"]
        kw = question["kw"]
        entry = {"question": q, "tag": question["tag"], "kw": kw, "runs": {}}

        a_hits = search_segments(list(segments), q, duration, top_k=5, max_chars=6000)
        a = _summarize("A", type("O", (), {"hits": a_hits, "mode_used": "bm25_baseline", "diagnostics": {}})())
        a["hit1"] = _hit_at(a_hits, kw, 1)
        a["hit5"] = _hit_at(a_hits, kw, 5)
        a["mrr"] = _mrr(a_hits, kw)
        entry["runs"]["A_baseline60s"] = a

        outcome_b = retrieve(db, video_id, q, mode="bm25")
        b = _summarize("B", outcome_b)
        b["hit1"] = _hit_at(outcome_b.hits, kw, 1)
        b["hit5"] = _hit_at(outcome_b.hits, kw, 5)
        b["mrr"] = _mrr(outcome_b.hits, kw)
        entry["runs"]["B_chunks_bm25"] = b

        _QUERY_CACHE.clear()  # 每题都从冷缓存开始，保证 embed_seconds 是首调真实值
        began = time.perf_counter()
        outcome_c = retrieve(db, video_id, q, mode="hybrid")
        wall = round(time.perf_counter() - began, 3)
        c = _summarize("C", outcome_c)
        c["hit1"] = _hit_at(outcome_c.hits, kw, 1)
        c["hit5"] = _hit_at(outcome_c.hits, kw, 5)
        c["mrr"] = _mrr(outcome_c.hits, kw)
        c["wall_seconds"] = wall
        entry["runs"]["C_hybrid"] = c
        if kw is not None:
            tag_line = f"{entry['tag']} | A(hit1={a['hit1']},mrr={a['mrr']:.2f}) B(hit1={b['hit1']},mrr={b['mrr']:.2f}) C(hit1={c['hit1']},mrr={c['mrr']:.2f},embed={c['diagnostics'].get('embed_seconds')}s)"
        else:
            tag_line = f"{entry['tag']} | C top={'无候选' if not outcome_c.hits else outcome_c.hits[0].text[:30]}"
        print(tag_line)

        if entry["tag"] == "原词题" and entry["question"].startswith("召回率"):
            # 缓存验证：同题立刻再跑一次，应命中缓存且不再调接口
            outcome_c2 = retrieve(db, video_id, q, mode="hybrid")
            entry["runs"]["C_hybrid_cached"] = _summarize("C2", outcome_c2)
        report["questions"].append(entry)

    engine.dispose()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"RESULT: PASS - 证据已写入 {OUT.name}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - 探测脚本把任何异常落成 FAIL 而不是堆栈崩溃
        print(f"RESULT: FAIL - {exc.__class__.__name__}: {exc}")
        sys.exit(1)
