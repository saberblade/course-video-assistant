# 后端工程

FastAPI 服务入口为 `app/main.py`，导出 `app`。当前已接入 SYS 提交的顺序任务执行器、后台转写预热与前端静态托管。

## 已提交模块

- 视频上传、分页列表、详情、支持 Range 的视频响应、转写与章节读取、当前视频问答、重试和删除。
- SQLite 数据模型、临时文件处理、统一错误与 request_id、服务重启后的中断任务恢复。
- 60 秒窗口提取式章节生成、jieba 与 BM25 检索、httpx 模型调用、原文引用校验及降级分支。
- `app/executor.py` 顺序领取 queued 任务，推进转写、分段落库、章节生成及 ready/failed 终态。
- `tests/` 中的媒体校验、视频接口、检索、章节与问答测试源码。

执行器默认随 FastAPI 生命周期启动与停止。`TASK_EXECUTOR_ENABLED=0` 可关闭执行器，单元测试 fixture 已设置该值。任务输出和错误按实际执行结果登记，真实问答依赖 ready 视频的转写片段。

## 本地准备与启动

使用 Python 3.11，在仓库根目录的 PowerShell 中准备包含转写依赖的完整环境。

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
if (-not (Test-Path .env.local)) { Copy-Item .env.example .env.local }
```

按[根目录说明](../README.md)准备 FFmpeg/ffprobe、完整 small 模型、服务端配置及前端构建产物，再启动服务。

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\start.ps1
```

脚本从 `.env.local` 读取 `APP_PORT`，默认 8000，使用一个 Uvicorn worker。默认前端为 `http://127.0.0.1:8000/`，接口文档为 `/docs`。需要手动前台启动时可在仓库根目录使用以下命令，端口以该命令为准。

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --workers 1
```

存在 `frontend/dist/index.html` 时，服务会在 API 路由之后挂载静态页面。未构建时跳过挂载并写日志，构建后重启服务。`app/frontend.py` 的 `FrontendFiles` 为 `/screen`、`/videos/:id` 返回 Vue 入口，兼容 Windows 路径分隔符；缺失 API 与静态资源仍保留 404。浏览器刷新与直接访问已完成本机验证。

## 配置与健康检查

`app/config.py` 从仓库根目录读取 `.env.local`，已有系统环境变量优先。主要配置如下。

| 配置 | 当前用途 |
| --- | --- |
| `DATA_DIR` | 数据根目录，默认 `data/`；数据库为其中的 `app.db` |
| `FFPROBE_BIN` | 服务端视频探测命令或实际路径 |
| `MAX_UPLOAD_BYTES`、`MAX_VIDEO_SECONDS` | 默认 200 MiB、20 分钟的输入限制 |
| `MAX_UNFINISHED_JOBS` | 排队和处理中任务总量限制，默认 3 |
| `WHISPER_MODEL_DIR`、`WHISPER_DEVICE`、`WHISPER_COMPUTE_TYPE`、`WHISPER_LANGUAGE` | 转写模块继承读取；默认本地 small 模型、CPU、int8、中文 |
| `TASK_EXECUTOR_ENABLED` | 默认开启，值为 `0` 时关闭执行器 |
| `TASK_TIMEOUT_SECONDS` | 默认 1200 秒，转写超时终止控制 |
| `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` | 服务端模型兼容接口配置，模型默认 qwen-plus |
| `ANSWER_MODE` | `generative` 使用模型，`extractive` 进入提取式降级分支 |
| `RETRIEVAL_TOP_K`、`MAX_CONTEXT_CHARACTERS` | 检索候选和上下文上限 |

根目录 `.env.example` 中的 `DATABASE_URL` 尚未被读取，数据库位置由 `DATA_DIR` 决定。转写并发目前通过顺序执行器和模块内部锁固定为 1，修改并发配置字段不会自动增加工作线程。

`GET /api/health` 检查数据库可查询性、转写模块入口文件和模型配置字段。`transcriber=ready` 仅说明模块文件存在，`llm_configured=true` 仅说明配置齐全。模型是否可加载、队列是否正常工作及 API 是否真实连通，应通过相应脚本与实际样本验证。

有有效依据且生成成功时返回 `answered/generative`。无依据时返回 `not_found`。关闭生成、缺少配置或模型请求故障且检索命中原文时返回 `degraded/extractive`。SYS 已上传启用 Qwen 的问答与拒答记录，正式质量验收仍需 QA 执行完整题集。

## 前端联调

在 `frontend/.env.local` 设置 `VITE_USE_MOCK=false` 并重启 Vite，`/api` 会代理到 `http://127.0.0.1:8000`。生产构建默认使用真实课程接口，修改前端环境变量后重新构建。

悬浮助教路由为 `POST /api/assistant/chat`：只回答站内使用问题，不读课程数据、不写数据库；同一时刻只放一个请求进模型，并发时返回 429 `ASSISTANT_BUSY`；未配置模型、模型超时或空回答降级为 `mode: "guide"`；问题超过 300 字符、最后一条不是用户消息或带未知字段返回 422；单次对话最多 20 条、合计 6000 字符。课程问答路由为 `POST /api/videos/{video_id}/questions`。

## 测试与证据

安装根目录锁文件后，在仓库根目录执行后端测试。

```powershell
.\.venv\Scripts\python.exe -m pytest -c backend/pytest.ini backend/tests -q
```

fixture 设置 `TASK_EXECUTOR_ENABLED=0`，使用临时数据库并模拟相应的媒体或模型响应。SYS 的[部署记录](../deploy/01_SYS环境与部署记录.md)报告后端 36 passed，[端到端 JSON](../deploy/evidence/logs_e2e_local_run.json)包含合成中文样本的上传、转写、章节、生成式回答与拒答记录。本轮文档更新核对了源码和存档，未在当前电脑复跑环境或测试。

`scripts/e2e_smoke.py` 会先尝试删除视频列表第一页中的可删除记录，结束时删除本次样本，需在专用测试数据中执行。环境与转写验收命令见[运行脚本说明](../scripts/README.md)。

## 工程交接

- BE 复核 SYS 新增的执行器、生命周期接线及测试调整，检查并发、取消、异常恢复和事务一致性。
- QA 使用正式授权的 3–5 分钟样本和既定 20+5 题集，分别验证处理时间、答案质量、拒答和引用。
- FE 已完成本机真实接口流程和同源深层路由刷新检查，见[联调记录](../docs/05_测试与验收/07_前后端联调记录_2026-11-10.md)；QA/SYS 在正式交付设备复核。
- SYS/QA 完成目标机复测、完整备份回退与发布版本冻结。恢复脚本当前恢复数据和 dist，源码需另外切换到匹配提交。

[后端岗位开工单](../docs/岗位开工单/后端工程师.md) · [团队 API 契约](../docs/03_技术方案与接口/02_API与数据模型契约.md) · [环境版本清单](../docs/environment-versions.md)
