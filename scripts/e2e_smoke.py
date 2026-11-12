# -*- coding: utf-8 -*-
"""端到端冒烟验证（SYS）：上传→queued→转写→章节→ready→索引→问答→删除，全链路真实执行。

前置：
  1. 服务运行在 --base-url（默认 127.0.0.1:8000）
  2. 样本视频存在（默认 data/tmp/samples/lecture_A.mp4，可 --sample 指定）
  3. .env.local 已配置工具与模型（LLM 密钥可空，空则走 extraction 降级）

设计约束（账号化之后）：
  - 必须登录并带 X-CSRF-Token；匿名请求一律 401。
  - **只删除本次运行自己上传的视频**，绝不清空他人或演示数据。
产物：logs/e2e_local_run.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

import httpx

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_SAMPLE = ROOT / "data" / "tmp" / "samples" / "lecture_A.mp4"
OUT = ROOT / "logs" / "e2e_local_run.json"
STEPS: list[dict] = []


def step(name: str, detail: dict) -> None:
    STEPS.append({"step": name, **detail})
    print(f"[{name}] {json.dumps(detail, ensure_ascii=False)[:320]}")


def login(client: httpx.Client, base: str, username: str, password: str) -> None:
    origin = {"Origin": base}
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    if response.status_code != 200:
        created = client.post(
            "/api/auth/register",
            json={"username": username, "password": password, "display_name": "冒烟账号"},
            headers=origin,
        )
        assert created.status_code in (201, 409), f"注册失败: {created.status_code} {created.text[:200]}"
        response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, f"登录失败: {response.status_code} {response.text[:200]}"
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    client.headers["Origin"] = base


def main() -> int:
    parser = argparse.ArgumentParser(description="端到端冒烟")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default="e2e_demo")
    parser.add_argument("--password", default="demo-Passw0rd")
    parser.add_argument("--sample", default=str(DEFAULT_SAMPLE))
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    sample = pathlib.Path(args.sample)

    if not sample.is_file():
        print(f"缺少样本 {sample}；先运行 scripts/make_tts_samples.py")
        return 2

    created_id: str | None = None
    with httpx.Client(base_url=base, timeout=120, trust_env=False) as client:
        # 0. 匿名必须 401：账号化之后任何业务接口都要求登录
        anonymous = httpx.get(f"{base}/api/videos", timeout=10, trust_env=False)
        step("anonymous_denied", {"status": anonymous.status_code})
        assert anonymous.status_code == 401, "未登录访问业务接口应为 401"

        login(client, base, args.username, args.password)
        step("health", {"body": client.get("/api/health").json()})
        before = client.get("/api/videos").json()["total"]
        step("baseline_total", {"total": before})

        # 1. 上传
        started = time.time()
        with sample.open("rb") as handle:
            upload = client.post("/api/videos", files={"file": (sample.name, handle, "video/mp4")})
        step("upload", {"status": upload.status_code, "body": upload.json(), "took": round(time.time() - started, 2)})
        assert upload.status_code == 202, f"上传应 202: {upload.status_code} {upload.text[:200]}"
        video = upload.json()
        created_id = video["id"]
        assert video["status"] == "queued" and video["error"] is None

        # 2. 轮询到终态
        trace = []
        deadline = time.time() + 420
        final = None
        while time.time() < deadline:
            body = client.get(f"/api/videos/{created_id}").json()
            trace.append({"t": round(time.time() - started, 1), "status": body["status"]})
            if body["status"] in ("ready", "failed"):
                final = body
                break
            time.sleep(2)
        assert final is not None, "420 秒内未得到终态"
        assert final["status"] == "ready", f"应 ready 而非 {final['status']}: {final['error']}"
        step("poll_to_ready", {"total_sec": round(time.time() - started, 1), "elapsed_sec": final["elapsed_sec"], "trace": trace[::5]})

        # 3. 转写与章节
        segments = client.get(f"/api/videos/{created_id}/transcript").json()["segments"]
        assert len(segments) >= 5, f"分段数量异常: {len(segments)}"
        assert all(s["end_sec"] > s["start_sec"] >= 0 for s in segments)
        summary = client.get(f"/api/videos/{created_id}/summary").json()
        assert summary["mode"] == "extractive" and summary["chapters"]
        step("content", {"segments": len(segments), "chapters": len(summary["chapters"])})

        # 4. 索引登记（后台线程可能还在建，只记录不阻塞）
        health = client.get("/api/health").json()
        step("rag", {"status": health.get("rag_status"), "ready": health.get("rag_indexes_ready"), "failed": health.get("rag_indexes_failed")})

        # 5. 问答（对口问题 + 无依据问题）
        q1 = client.post(f"/api/videos/{created_id}/questions", json={"question": "HTTP请求通常包含哪些部分？"})
        assert q1.status_code == 200, q1.text[:200]
        d1 = q1.json()
        step("question_positive", {"answer_status": d1["answer_status"], "mode": d1["mode"], "retrieval": d1.get("retrieval_mode"), "citations": len(d1["citations"])})
        if health.get("llm_configured"):
            assert d1["answer_status"] in ("answered", "not_found"), f"密钥有效时不应 degraded: {d1['answer_status']}"
        if d1["answer_status"] == "answered":
            assert d1["mode"] == "generative" and d1["citations"], "answered 必须有生成模式和引用"

        q2 = client.post(f"/api/videos/{created_id}/questions", json={"question": "这段课程建议早餐吃什么？"})
        assert q2.status_code == 200
        d2 = q2.json()
        step("question_negative", {"answer_status": d2["answer_status"], "citations": len(d2["citations"])})
        assert d2["answer_status"] in ("not_found", "answered")
        if d2["answer_status"] == "not_found":
            assert d2["citations"] == []

        # 6. 引用必须来自当前视频且逐字一致
        segment_map = {s["id"]: s["text"] for s in segments}
        for citation in d1["citations"] + d2["citations"]:
            assert citation["segment_id"] in segment_map, f"引用片段不属于当前视频: {citation['segment_id']}"
            assert segment_map[citation["segment_id"]] == citation["text"], "引用原文必须与转写一致"
        step("citations_verified", {"count": len(d1["citations"]) + len(d2["citations"])})

        # 7. 历史问答可恢复
        history = client.get(f"/api/videos/{created_id}/questions?limit=10").json()
        assert history["total"] >= 2, "历史问答应至少包含刚才两条"
        step("history", {"total": history["total"], "returned": len(history["items"])})

        # 8. 只删本次上传的视频
        removed = client.delete(f"/api/videos/{created_id}")
        assert removed.status_code == 204, f"删除应 204: {removed.status_code}"
        assert client.get(f"/api/videos/{created_id}").status_code == 404
        created_id = None
        after = client.get("/api/videos").json()["total"]
        assert after == before, f"列表应回到基线 {before}，实际 {after}"
        step("delete_own_video", {"status": 204, "total_after": after})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"steps": STEPS}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("RESULT: PASS - 全链路真实冒烟通过，证据已存", OUT)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({"steps": STEPS, "error": str(exc)}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"RESULT: FAIL - {exc}")
        sys.exit(1)
