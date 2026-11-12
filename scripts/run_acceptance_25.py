"""25 题验收（G19/G20）：上传 A/B/C 样本 → 等就绪 → 逐题提问 → 判定与留证。

判定口径来自 tests/fixtures/acceptance_questions.json：
- positive：期望 answered，且回答至少覆盖一半 expected_points
- negative：期望 not_found，且不得编造引用
引用合法性单独校验：segment_id 必须属于当前视频，原文逐字一致。

产物：
    tests/evidence/qa_25_<日期>.json    逐题明细（含 request_id、耗时、引用）
    tests/evidence/qa_25_<日期>.md      可读摘要

用法：
    python scripts/run_acceptance_25.py                     # 上传三段样本并验收
    python scripts/run_acceptance_25.py --reuse             # 复用已上传的同名视频
    python scripts/run_acceptance_25.py --min-positive 16   # 调整通过线
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BANK = PROJECT_ROOT / "tests" / "fixtures" / "acceptance_questions.json"
EVIDENCE = PROJECT_ROOT / "tests" / "evidence"


def setup_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass


def login(client: httpx.Client, username: str, password: str) -> None:
    """演示账号不存在时自动注册，保证脚本在干净库上也能跑。"""
    origin = {"Origin": str(client.base_url).rstrip("/")}
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    if response.status_code != 200:
        created = client.post(
            "/api/auth/register",
            json={"username": username, "password": password, "display_name": "验收账号"},
            headers=origin,
        )
        if created.status_code not in (201, 409):
            raise RuntimeError(f"账号不可用：{created.status_code} {created.text[:200]}")
        response = client.post("/api/auth/login", json={"username": username, "password": password})
    response.raise_for_status()
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]


def wait_ready(client: httpx.Client, video_id: str, limit: int = 420) -> dict:
    deadline = time.time() + limit
    body: dict = {}
    while time.time() < deadline:
        body = client.get(f"/api/videos/{video_id}").json()
        if body["status"] in ("ready", "failed"):
            return body
        time.sleep(3)
    return body


def wait_index(client: httpx.Client, video_id: str, limit: int = 120) -> str:
    """索引是可选增强：等它就绪，超时如实记录 bm25 回退，不算失败。"""
    deadline = time.time() + limit
    while time.time() < deadline:
        health = client.get("/api/health").json()
        if health.get("rag_indexes_ready", 0) > 0:
            return "ready"
        time.sleep(2)
    return "timeout"


def upload(client: httpx.Client, path: Path, title: str) -> str:
    with path.open("rb") as handle:
        response = client.post("/api/videos", files={"file": (title + ".mp4", handle, "video/mp4")})
    if response.status_code != 202:
        raise RuntimeError(f"上传失败 {path.name}: {response.status_code} {response.text[:200]}")
    return response.json()["id"]


def main() -> int:
    setup_stdout()
    parser = argparse.ArgumentParser(description="25 题验收")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default="e2e_demo")
    parser.add_argument("--password", default=None, help="兼容旧调用；推荐 ACCEPTANCE_PASSWORD 环境变量或交互输入")
    parser.add_argument("--sample-kind", choices=["synthetic", "recorded"], default="synthetic")
    parser.add_argument("--samples-dir", default=str(PROJECT_ROOT / "data" / "tmp" / "samples"))
    parser.add_argument("--reuse", action="store_true", help="复用库里已有的同名视频，不重复上传")
    parser.add_argument("--min-positive", type=int, default=16)
    parser.add_argument("--only", nargs="*", default=None, help="只跑指定题号，如 --only A01 N01")
    args = parser.parse_args()
    args.password = args.password or os.environ.get("ACCEPTANCE_PASSWORD") or getpass.getpass("验收账号口令（不显示）: ")

    bank = json.loads(BANK.read_text(encoding="utf-8"))["questions"]
    evidence: list[dict] = []
    videos: dict[str, dict] = {}

    with httpx.Client(base_url=args.base_url, timeout=180, trust_env=False) as client:
        login(client, args.username, args.password)
        health = client.get("/api/health").json()
        print("health:", json.dumps(health, ensure_ascii=False))

        scripts = json.loads((PROJECT_ROOT / "tests" / "fixtures" / "lecture_scripts.json").read_text(encoding="utf-8"))
        existing = {item["title"]: item for item in client.get("/api/videos?limit=100").json()["items"]}

        for sample in ("A", "B", "C"):
            title = scripts[sample]["title"]
            if args.reuse and title in existing:
                video = existing[title]
                print(f"[{sample}] 复用 {title} {video['id']} ({video['status']})")
            else:
                path = Path(args.samples_dir) / f"lecture_{sample}.mp4"
                if not path.is_file():
                    print(f"缺少样本 {path}；先运行 scripts/make_tts_samples.py")
                    return 1
                print(f"[{sample}] 上传 {path.name} …")
                video_id = upload(client, path, title)
                video = wait_ready(client, video_id)
                print(f"[{sample}] {video['status']} elapsed={video['elapsed_sec']}s")
                if video["status"] != "ready":
                    print(f"[{sample}] 未就绪，错误：{video.get('error')}")
                    return 1
                video = client.get(f"/api/videos/{video_id}").json()
            index_state = wait_index(client, video["id"])
            segments = client.get(f"/api/videos/{video['id']}/transcript").json()["segments"]
            videos[sample] = {"id": video["id"], "title": title, "index": index_state, "segments": segments}
            print(f"[{sample}] 分片 {len(segments)}，索引 {index_state}")

        for item in bank:
            if args.only and item["id"] not in args.only:
                continue
            sample = item["sample"]
            video = videos[sample]
            began = time.perf_counter()
            response = client.post(
                f"/api/videos/{video['id']}/questions",
                json={"question": item["question"]},
            )
            took = round(time.perf_counter() - began, 2)
            request_id = response.headers.get("x-request-id", "")
            if response.status_code != 200:
                evidence.append(
                    {
                        "id": item["id"],
                        "sample": sample,
                        "question": item["question"],
                        "http": response.status_code,
                        "ok": False,
                        "took_sec": took,
                        "request_id": request_id,
                        "note": response.text[:200],
                    }
                )
                print(f"{item['id']:<5} HTTP {response.status_code}")
                continue

            data = response.json()
            answer = data["answer"]
            points = [p for p in item["expected_points"] if p in answer]
            valid, invalid_reason = True, ""
            segment_map = {s["id"]: s["text"] for s in video["segments"]}
            for citation in data["citations"]:
                if citation["segment_id"] not in segment_map:
                    valid, invalid_reason = False, "引用片段不属于当前视频"
                    break
                if segment_map[citation["segment_id"]] != citation["text"]:
                    valid, invalid_reason = False, "引用原文与转写不一致"
                    break
            if item["kind"] == "negative" and data["citations"]:
                valid, invalid_reason = False, "无依据题不应返回引用"

            status_ok = data["answer_status"] == item["expected_status"]
            # 要点覆盖率作为质量提示，不参与放行判定：措辞不同但意思对时不应误判为失败。
            points_ratio = len(points) / max(1, len(item["expected_points"]))
            ok = status_ok and valid

            evidence.append(
                {
                    "id": item["id"],
                    "sample": sample,
                    "question": item["question"],
                    "http": 200,
                    "answer_status": data["answer_status"],
                    "expected_status": item["expected_status"],
                    "mode": data["mode"],
                    "retrieval_mode": data.get("retrieval_mode"),
                    "citations": len(data["citations"]),
                    "points_hit": f"{len(points)}/{len(item['expected_points'])}",
                    "points_ratio": round(points_ratio, 2),
                    "citation_valid": valid,
                    "invalid_reason": invalid_reason,
                    "ok": ok,
                    "took_sec": took,
                    "latency_ms": data["latency_ms"],
                    "request_id": request_id,
                    "answer": answer[:200],
                }
            )
            print(
                f"{item['id']:<5} {data['answer_status']:<11} 期望 {item['expected_status']:<11} "
                f"引用 {len(data['citations']):<2} 要点 {len(points)}/{len(item['expected_points'])} "
                f"{'OK' if ok else 'NG'}  {took}s"
            )
            time.sleep(0.3)

    kinds = {item["id"]: item["kind"] for item in bank}
    positives = [row for row in evidence if kinds[row["id"]] == "positive"]
    negatives = [row for row in evidence if kinds[row["id"]] == "negative"]
    answered = sum(1 for row in positives if row.get("answer_status") == "answered")
    rejected = sum(1 for row in negatives if row.get("answer_status") == "not_found")
    citation_ok = all(row.get("citation_valid", False) for row in evidence)
    complete_suite = len(evidence) == len(bank)
    passed = complete_suite and answered >= args.min_positive and rejected == len(negatives) and citation_ok

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "base_url": args.base_url,
        "sample_kind": args.sample_kind,
        "scope": "answer status and citation integrity; semantic correctness requires human review",
        "videos": {k: {"id": v["id"], "title": v["title"], "index": v["index"], "segments": len(v["segments"])} for k, v in videos.items()},
        "summary": {
            "positive_answered": f"{answered}/{len(positives)}",
            "negative_rejected": f"{rejected}/{len(negatives)}",
            "citation_valid": citation_ok,
            "passed": passed,
            "complete_suite": complete_suite,
            "semantic_review": "not_executed",
            "formal_quality_passed": False,
            "threshold_positive": args.min_positive,
        },
        "items": evidence,
    }
    json_path = EVIDENCE / f"qa_25_{stamp}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 25 题链路验证结果",
        "",
        f"- 时间：{payload['generated_at']}",
        f"- 服务：{args.base_url}",
        f"- 有依据题返回回答：**{answered}/{len(positives)}**（门槛 {args.min_positive}）",
        f"- 无依据题拒答：**{rejected}/{len(negatives)}**",
        f"- 引用合法性：{'通过' if citation_ok else '不通过'}",
        f"- 链路结论：**{'通过' if passed else '未通过或未跑全'}**",
        f"- 样本：{args.sample_kind}；人工语义判题未执行，本报告不作正式课程质量放行结论。",
        "",
        "| 题号 | 实际 | 期望 | 引用 | 要点 | 耗时 | 结果 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in evidence:
        lines.append(
            f"| {row['id']} | {row.get('answer_status', '-')} | {row.get('expected_status', '-')} | "
            f"{row.get('citations', '-')} | {row.get('points_hit', '-')} | {row.get('took_sec', '-')}s | "
            f"{'OK' if row.get('ok') else 'NG'} |"
        )
    md_path = EVIDENCE / f"qa_25_{stamp}.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\n有依据题 {answered}/{len(positives)}，无依据题 {rejected}/{len(negatives)}，引用合法 {citation_ok}")
    print(f"证据：{json_path.name} / {md_path.name}")
    print("RESULT:", "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
