# -*- coding: utf-8 -*-
"""
Qwen 真实调用冒烟测试（SYS / M1）

用途：验证 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL 三项配置可用，
     输出 request_id、耗时、token 用量等证据，供粘贴进 docs/01_M1_环境验证记录.md 第 5 节。
安全：脚本不打印、不保存密钥；.env.local 不入库。

用法（在 course-review 根目录，先在 .env.local 填好配置）：
    .\\.venv\\Scripts\\python.exe scripts\\llm_smoke_test.py

约定（与《环境配置与部署交接》一致）：
    - LLM_BASE_URL 为 OpenAI 兼容接口的基础地址，本脚本追加 /chat/completions
    - LLM_MODEL 固定 qwen-plus，变更需 PM 登记变更并通知 QA
    - 连接超时 5 秒、总墙钟截止 25 秒
"""
import json
import os
import pathlib
import time
import uuid

import httpx

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env.local"


def load_env(path: pathlib.Path) -> dict:
    """极简 .env 解析；系统环境变量优先。"""
    conf = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            conf[k.strip()] = v.strip()
    # 系统环境变量优先
    for key in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
        if os.environ.get(key):
            conf[key] = os.environ[key]
    return conf


def main() -> int:
    conf = load_env(ENV_FILE)
    base = conf.get("LLM_BASE_URL", "").rstrip("/")
    key = conf.get("LLM_API_KEY", "")
    model = conf.get("LLM_MODEL", "")
    req_id = str(uuid.uuid4())

    print("== llm_smoke_test ==")
    print(f"request_id : {req_id}")
    print(f"base_url   : {base or '(未配置)'}")
    print(f"model      : {model or '(未配置)'}")
    print(f"api_key    : {'已配置(不显示)' if key else '(未配置)'}")

    if not (base and key and model):
        print("RESULT: FAIL - 配置不完整，请在 .env.local 填写 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL")
        return 2
    if "/chat/completions" in base:
        print("WARN: base_url 已含 /chat/completions，将不再追加（契约要求基础地址不含后缀）")
        endpoint = base
    else:
        endpoint = base + "/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": "这是系统工程师连通性测试。请只回复两个字：正常",
            }
        ],
        "temperature": 0,
        "max_tokens": 16,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    t0 = time.perf_counter()
    try:
        # ENHANCED: 连接超时 5 秒；总超时 25 秒（与契约一致，测试不做重试）
        with httpx.Client(timeout=httpx.Timeout(connect=5.0, read=25.0, write=10.0, pool=5.0)) as client:
            resp = client.post(endpoint, json=payload, headers=headers)
        elapsed = time.perf_counter() - t0
    except httpx.HTTPError as exc:
        print(f"RESULT: FAIL - 网络错误 {exc.__class__.__name__}: {exc}")
        print(f"耗时: {time.perf_counter() - t0:.2f}s")
        return 3

    print(f"耗时: {elapsed:.2f}s")
    print(f"HTTP状态: {resp.status_code}")
    if resp.status_code != 200:
        # 脱敏输出：不回显完整响应体，只取错误类型
        print("RESULT: FAIL - 鉴权或服务端错误（响应体已省略，扫描错误类型）")
        ctype = resp.headers.get("content-type", "")
        print(f"content-type: {ctype}")
        for probe in ("InvalidApiKey", "invalid_api_key", "Throttling", "Arrearage", "Model.NotExist", "region"):
            if probe in resp.text:
                print(f"命中错误特征: {probe}")
                break
        return 4

    data = resp.json()
    choice = (data.get("choices") or [{}])[0].get("message", {})
    usage = data.get("usage", {})
    request_upstream_id = data.get("id") or data.get("request_id") or "-"

    print(f"上游id     : {request_upstream_id}")
    print(f"回答       : {(choice.get('content') or '')[:60]}")
    print(f"prompt_tokens: {usage.get('prompt_tokens')}  completion_tokens: {usage.get('completion_tokens')}  total_tokens: {usage.get('total_tokens')}")
    print("RESULT: PASS - 真实调用成功，请将本页数据抄入 docs/01_M1_环境验证记录.md 第 5 节")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
