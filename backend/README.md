# 后端工程

FastAPI 服务入口为 `app/main.py`，导出 `app`。本说明按当前提交的源码编写。

## 已提交模块

- 视频上传受理、分页列表、详情、支持 Range 的视频响应、转写和章节读取、当前视频问答、重试及删除。
- SQLite 数据模型、临时文件处理、统一错误与 request_id、服务重启后的中断任务恢复。
- 60 秒窗口的提取式章节生成逻辑、jieba 与 BM25 检索、httpx 调用模型、原文引用校验及降级分支。
- `tests/` 中的媒体校验、视频接口、检索、章节与问答测试源码。

新上传或重试的视频进入 `queued`。当前入口没有启动任务执行器，`modules/transcriber/` 还只有交接说明，因此转写、索引与章节生成未串入实际视频处理链路。课程问答依赖数据库中已为 `ready` 且已有转写的记录。

## 本地准备与启动

使用项目基线 Python 3.11，在仓库根目录打开 PowerShell。

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
if (-not (Test-Path .env.local)) { Copy-Item .env.example .env.local }
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --workers 1
```

后端提供接口文档 `http://127.0.0.1:8000/docs`。当前尚未实现 `frontend/dist/` 的托管，开发联调时在第二个终端启动前端 Vite，访问 `http://localhost:5173/`。

视频探测需要 FFmpeg 套件中的 `ffprobe`，可配置 `FFPROBE_BIN` 为其实际路径。当前健康检查缺少转写模块时会返回 HTTP 503，响应中包含 `status=not_ready` 和 `transcriber=missing`。该检查仅按转写模块入口文件存在性判断模块状态，真实加载和转写仍需单独验证。

## 配置读取

`app/config.py` 从仓库根目录读取 `.env.local`，已有系统环境变量优先。路径型配置以仓库根目录为基准。

| 配置 | 当前用途 |
| --- | --- |
| `DATA_DIR` | 数据根目录，默认 `data/`，SQLite 固定为该目录内 `app.db` |
| `FFPROBE_BIN` | 视频探测命令或路径 |
| `MAX_UPLOAD_BYTES`、`MAX_VIDEO_SECONDS` | 默认 200 MiB、20 分钟的服务端输入限制 |
| `MAX_UNFINISHED_JOBS` | 排队和处理中任务总量限制，默认 3 |
| `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` | 模型兼容接口基础地址、服务端密钥和模型名，模型默认 qwen-plus |
| `ANSWER_MODE` | `generative` 使用模型生成，`extractive` 进入提取式降级分支 |
| `RETRIEVAL_TOP_K`、`MAX_CONTEXT_CHARACTERS` | 检索候选和上下文上限 |
| `LLM_CONNECT_TIMEOUT_SECONDS`、`LLM_TOTAL_DEADLINE_SECONDS` | 模型请求连接与期限配置 |

`.env.example` 内的 `DATABASE_URL` 尚未被读取，当前数据库位置由 `DATA_DIR` 决定。`WHISPER_*`、转写并发和任务超时字段需要后续转写执行器落实。启动命令明确指定 host/port/worker，按命令实际参数运行。

`llm_configured=true` 只代表三个模型配置有值。真实连通需对可问答的视频发起请求验证。缺少配置、关闭生成或模型请求故障且检索命中原文时，返回 `degraded` 和原文引用；无依据时返回 `not_found`。

## 前端联调

在 `frontend/.env.local` 设置 `VITE_USE_MOCK=false` 后重启前端服务。Vite 将 `/api` 代理到 `http://127.0.0.1:8000`。

悬浮助教预留的 `POST /api/assistant/chat` 当前尚无后端路由，`VITE_ASSISTANT_USE_API` 开关应在实现并确认扩展接口后启用。当前问答路由为 `POST /api/videos/{video_id}/questions`。

## 自动化测试

在仓库根目录执行以下命令。

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -c backend/pytest.ini backend/tests -q
```

测试会建立临时数据库和样例记录，并在相应用例中模拟媒体探测或模型响应。真实录课、模型服务连通与端到端验收需另行完成。本轮 README 更新核对了源码、依赖清单、配置及文档链接，未在本机安装后端依赖或执行上述测试。

## 工程交接

- BE 与 SYS 接入排队执行器、转写输出落库、章节生成和状态推进，提交真实授权录课的完整处理记录。
- SYS 验证目标 Python 环境、直接及传递依赖、FFmpeg 和语音模型，并补齐完整锁文件与环境版本清单。
- FE 与 BE 核对实际接口，QA 执行后端测试和同一批真实样本验收。
- SYS 与 BE 配置前端静态托管及页面路由回退，再验证同源交付版本。

[后端岗位开工单](../docs/岗位开工单/后端工程师.md) · [团队 API 契约](../docs/03_技术方案与接口/02_API与数据模型契约.md) · [环境与部署交接](../docs/03_技术方案与接口/03_环境配置与运行部署.md)
