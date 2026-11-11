# 课迹 · 课程视频复习助手

北京邮电大学专业实训课设。面向中文录课复习，提供视频转写、章节提要、课程问答和原文引用定位，帮助学生找到讲解、核对原话，并保存自己的复习标记与疑问。

[项目仓库](https://github.com/saberblade/course-video-assistant) · [前端说明](frontend/README.md) · [后端说明](backend/README.md) · [部署说明](deploy/README.md)

本次课设的**最终开发阶段**建设账号登录、服务端学习档案与混合检索 RAG，并完成运行维护和交付验收。全部任务截止 **2026年11月12日23:59（北京时间）**。完整分工、数据库/API契约和五人提示词见[中期到答辩之前的规划](docs/中期到答辩之前的规划/README.md)，全部必达项见[最终交付总表](docs/中期到答辩之前的规划/08_最终交付总表与签收门槛.md)。本段为任务规划，下文描述当前已实现版本。

## 当前版本

2026 年 11 月 11 日按 [`ea57c26`](https://github.com/saberblade/course-video-assistant/tree/ea57c26) 核对。项目已完成前后端、转写模块与小样本链路接入，正在推进正式样本回归和目标设备验收。

| 能力 | 当前实现 | 使用边界 |
| --- | --- | --- |
| 我的课程 | 上传 MP4、分页列表、处理状态、失败重试、删除 | H.264 视频 + AAC 音轨，须有中文讲课音频；上限 200 MiB、20 分钟 |
| 视频复习 | 播放、转写原文、章节提要、来源原句与时间定位 | 章节按 60 秒窗口抽取原句，属于基础提要 |
| 课程问答 | 基于当前视频检索、生成回答、引用回填、无依据拒答和故障降级 | 本页会话刷新后清空，尚无历史问答查询 API |
| 课程知识导航 | 读取实际视频章节，以时间路线组织，支持搜索、拖动画布、滚动平移及查看来源 | 连线表示时间先后，不表示知识先修关系；Mock 模式使用样例数据 |
| 复习进度 | 统计当前视频的手动章节标记，提供继续复习入口 | 不自动判断知识掌握程度 |
| 待复习清单 | 章节收藏、疑问备注、回看、提问及已解决状态 | 保存在当前浏览器，暂不跨设备同步 |
| 悬浮助教 | 默认内置站内指引；可开启后端使用问答接口 | 只用于产品操作指引，不读取课程内容 |
| 同源部署 | 后端托管 `frontend/dist`，支持 `/screen`、`/videos/:id` 直接访问和刷新 | 缺失 API、静态资源保持 404；构建后重启后端 |

本次新增了复习工作区、SQLite 并发连接回归修复、站内助教接口、SPA 页面回退及一键启停脚本。原有课程视频处理链路继续使用 `queued → transcribing → indexing → ready/failed`。

## 技术栈

| 层次 | 当前方案 |
| --- | --- |
| 前端 | Vue 3、TypeScript 5、Vite 7、Vue Router 4、Element Plus、Axios；Node.js 22，至少 22.12 |
| 后端 | Python 3.11 基线、FastAPI、Pydantic 2、SQLAlchemy、SQLite；文件连接使用 `NullPool` |
| 转写 | faster-whisper 多语言 small、CPU int8、独立子进程，FFmpeg / ffprobe |
| 检索与问答 | jieba、BM25、百炼 qwen-plus；从当前视频原文回填引用 |
| 运行 | Windows PowerShell、单个 Uvicorn worker、顺序任务执行器 |

前端依赖按 `frontend/package-lock.json` 安装，Python 完整依赖按 `requirements.lock.txt` 安装。历史联调曾使用 Python 3.12，团队发布基线仍为 3.11；实际设备版本写入[环境版本清单](docs/environment-versions.md)。

## 首次准备

以下命令在 Windows PowerShell 执行。先安装 Git、Python 3.11 和 Node.js 22，再取得项目。

```powershell
git clone https://github.com/saberblade/course-video-assistant.git
cd course-video-assistant
```

已有仓库的成员在工作区干净时执行 `git pull --ff-only`，无需重复克隆。以下命令均在仓库根目录执行。

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
npm.cmd --prefix frontend ci
if (-not (Test-Path .env.local)) { Copy-Item .env.example .env.local }
if (-not (Test-Path frontend/.env.local)) { Copy-Item frontend/.env.example frontend/.env.local }
```

启动前准备这些资源：

| 项目 | 本机要求 |
| --- | --- |
| FFmpeg / ffprobe | 可在 PATH 中找到，或在根目录 `.env.local` 填写 `FFMPEG_BIN`、`FFPROBE_BIN` 的实际路径 |
| 转写模型 | 完整的 `models/faster-whisper-small/`，或通过 `WHISPER_MODEL_DIR` 指向实际目录；默认 CPU int8、中文 |
| 模型 API | 根目录 `.env.local` 配置 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL=qwen-plus`；基础地址与账户地区匹配 |
| 前端模式 | `frontend/.env.example` 默认 `VITE_USE_MOCK=false`，连接真实课程 API；悬浮助教 API 默认关闭 |

`scripts/download_model_bin.py` 只下载并校验 `model.bin`，还需同一模型仓库与 revision 的配置、分词等配套文件。按[模型准备说明](deploy/02_模型准备说明.md)和[新机冷启动手册](deploy/03_新机冷启动部署手册.md)准备，再用实际预热和转写验证。

根目录 `.env.local` 由后端读取，系统环境变量优先；前端配置放在 `frontend/.env.local`。密钥仅在服务端保存。SQLite 位于 `DATA_DIR/app.db`，旧样例中的 `DATABASE_URL` 当前不参与数据库路径计算。

Git 仓库不包含虚拟环境、模型、工具二进制、授权录课、密钥、数据库或前端构建产物，成员需在自己的运行设备准备。

## 启动方式

### 开发联调：一键启动前后端

完成首次准备后，在根目录运行：

```powershell
.\start.cmd
```

脚本启动后端与 Vite 开发服务，并尝试打开浏览器。默认页面为 `http://127.0.0.1:5173/`，后端为 `http://127.0.0.1:8000/`。已占用的端口会跳过启动，需要核对监听的服务是否属于本项目；脚本会报告两端的就绪情况。

开发模式不要求先生成 `frontend/dist`。未构建时，8000 只提供 API，5173 提供页面；后端健康检查通过仍需实际验证模型和视频处理。

结束前等待转写和问答完成，再执行：

```powershell
.\stop.cmd
```

`stop.cmd` 会检查默认 `data/app.db` 中的未完成视频任务，忙时拒绝停止；显式强制停止可用 `.\stop.cmd -Force`，下次启动会把中断的处理任务记为可重试失败。直接关闭服务窗口会绕过停止脚本的检查。启停实现见 [start-all.ps1](deploy/start-all.ps1) 和 [stop-all.ps1](deploy/stop-all.ps1)。

### 单端口演示：构建后由后端托管

```powershell
npm.cmd --prefix frontend run build
powershell -ExecutionPolicy Bypass -File .\deploy\start.ps1
```

默认打开 `http://127.0.0.1:8000/`。此方式不需要同时运行 Vite；启动前应结束占用后端端口的旧实例。后端在启动时检查 `frontend/dist/index.html`，前端配置或构建变化后重新构建并重启后端。

当前一键脚本按默认 8000/5173 及默认数据路径设计。修改 `APP_PORT` 时，需同时对齐 Vite 中固定的 `/api` 代理目标和启停检查；修改 `DATA_DIR` 时，也需对齐停止、备份与恢复脚本。

## 页面与记录

| 地址 | 用途 |
| --- | --- |
| `/` | 项目首页 |
| `/screen` | 课程知识导航，选择已处理视频、查找章节与原文 |
| `/screen?view=library` | 我的课程：上传、列表、处理进度 |
| `/screen?view=analysis` | 复习进度：当前视频的手动标记概况 |
| `/screen?view=weak` | 待复习清单：疑问、备注、解决状态及回看入口 |
| `/videos/:id` | 播放、转写、章节与课程问答 |
| `/docs` | 后端 API 文档，使用后端端口访问 |

复习标记和疑问通过 `localStorage` 保存，以视频、处理次数和章节关联，Mock 与真实模式隔离。记录只属于当前浏览器和来源地址：5173 与 8000、`localhost` 与 `127.0.0.1` 分别保存；清除站点存储或换设备不会自动恢复。

视频、转写、章节和提交过的问答由后端保存。本页问答显示暂不从数据库恢复，刷新后会清空；切换章节/问答选项卡会保留当前页面结果。复习标记与问答历史是两套记录。

## 接口与问答模式

开发环境的 `/api` 由 Vite 代理到 `http://127.0.0.1:8000`。`VITE_USE_MOCK=true` 使用样例；未设置时开发模式默认 Mock、生产构建默认真实接口。修改前端变量后重启 Vite，生产环境则重新构建。

| 接口 | 用途 |
| --- | --- |
| `GET /api/health` | 数据库可查询性、转写入口文件及模型配置字段检查 |
| `POST /api/videos`、`GET /api/videos` | 上传、分页列表 |
| `GET /api/videos/{id}`、`GET /api/videos/{id}/content` | 状态详情、支持 Range 的视频内容 |
| `GET /api/videos/{id}/transcript`、`GET /api/videos/{id}/summary` | 转写与提取式章节提要 |
| `POST /api/videos/{id}/questions` | 当前视频问答 |
| `POST /api/videos/{id}/retry`、`DELETE /api/videos/{id}` | 失败重试、删除视频及关联数据 |
| `POST /api/assistant/chat` | 站内使用助教，不读取课程数据、不写问答数据库 |

课程问答按以下结果展示：

| 条件 | 状态 / 模式 | 页面含义 |
| --- | --- | --- |
| 有依据且生成成功 | `answered / generative` | 综合回答并附原文引用 |
| 无有效依据或引用校验不通过 | `not_found / extractive` | 明确未找到依据，无引用 |
| 有命中原文，但关闭生成、缺少配置或模型请求故障 | `degraded / extractive` | 原文检索模式，不能记为生成式问答验收通过 |

悬浮助教默认使用前端内置指引。需要后端助教时，在 `frontend/.env.local` 设置 `VITE_ASSISTANT_USE_API=true`，重启或重新构建。请求示例为 `{"messages":[{"role":"user","content":"怎么上传课程？"}]}`，响应含 `answer` 和 `mode`（`generative` 或 `guide`）。未配置模型、受控模型故障或空回答会返回使用指引；同一时刻助教只接纳一个请求，忙时返回 429。最后一个用户问题上限 300 字符，对话最多 20 条、合计 6000 字符。

`health.transcriber=ready` 当前只说明入口文件存在，`llm_configured=true` 只说明配置字段齐全；都不能代替真实模型加载、执行器存活和联网调用检查。

## 验证与已提交证据

环境准备完成后可执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -c backend/pytest.ini backend/tests -q
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend run build
```

后端测试使用临时数据库并设置 `TASK_EXECUTOR_ENABLED=0`，不启动真实转写队列；模型边界使用相应替身，不能据此认定真实模型和正式课程已验收。

| 记录 | 已提交内容与适用范围 |
| --- | --- |
| [11月10日前后端联调](docs/05_测试与验收/07_前后端联调记录_2026-11-10.md) / [机器可读证据](docs/05_测试与验收/07_前后端联调证据_2026-11-10.json) | Windows Chrome、119.4秒中文TTS样本，真实上传、16段转写、2章、问答引用、拒答、定位、删除及两种部署方式的页面刷新；一次生成式问答3581ms、2条引用 |
| [前端复习逻辑验证](docs/05_测试与验收/08_前端复习逻辑验证_2026-11-10.json) / [调整记录](docs/07_管理记录/06_前端复习逻辑调整_2026-11-10.md) | 真实章节来源、手动标记、备注、刷新恢复、存储隔离与多视口验证；后续路线图和画布交互调整亦有记录 |
| [SYS环境与部署记录](deploy/01_SYS环境与部署记录.md) / [转写验收](deploy/evidence/logs_transcriber_acceptance.json) | 11月9日基准机与较早TTS样本，转写7项PASS、工具及部署演练；与11月10日样本分开记录 |

历史联调记录的 45/46/56 项结果分别对应不同阶段。11月11日本机已按锁文件准备 Python 3.11.9 环境，后端 56 项测试、前端生产构建及依赖检查通过；119.27秒TTS样本约23.19秒到ready，生成16段转写、2章，真实生成问答和拒答、浏览器引用定位已核对。详见[本机运行基线](docs/中期到答辩之前的规划/当前版本运行基线_20261111.json)。该基线不代表最终阶段新增账号、学习档案和混合检索已完成验收；异常问题见[函数级复现](docs/中期到答辩之前的规划/当前版本异常复现_20261111.json)。正式样本与最终候选版本仍按交付总表执行。

实际转写和连通脚本见[运行脚本说明](scripts/README.md)。`scripts/e2e_smoke.py` 会尝试删除列表第一页的已有可删除视频，并在结束时删除本次样本，只在专用测试数据中执行。

## 仍需完善与验收

- BE：补齐模型返回非 JSON、空 `choices`、错误字段的受控处理；增强执行器认领和写入失败后的恢复；完善真实就绪检查。SPA 页面回退已实现，不再列为未实现功能。
- FE / QA：复核后端助教开关开启后的浏览器行为、弱相关问题拒答与异常恢复。账号、服务端复习记录、历史问答查询及混合检索按[最终阶段规划](docs/中期到答辩之前的规划/README.md)实施，当前版本尚未提供这些新增能力。
- QA：用正式授权的三段 3–5 分钟录课、20 道正题和 5 道无依据题验证答案、引用、处理耗时、问答期限和重启恢复。合成样本链路记录不能代替该验收。
- SYS / QA：在目标设备完成新机冷启动、一键启停及完整备份恢复演练。启停脚本已提交且语法检查通过，实机结果需登记；恢复数据、构建与源码版本需相互匹配。
- PM：按同一候选提交核对证据与未解决问题，正式验收通过后再冻结发布版本。

详细门槛见[测试计划](docs/05_测试与验收/01_测试计划与验收门槛.md)与[实际发布验收记录](docs/05_测试与验收/03_测试结果与发布验收记录.md)。

## 备份、目录与协作

等待转写和问答结束并停止服务后，按[部署说明](deploy/README.md)执行 `deploy/backup.ps1`；恢复使用 `deploy/restore.ps1 -BackupPath backups/实际备份目录`。当前脚本按默认 `data/` 目录工作，恢复数据和 `frontend/dist`，源码提交另行匹配；复制恢复不会自动清除备份后新增的文件，需在隔离副本核对完整回退结果。

| 目录 | 内容 / 主责 |
| --- | --- |
| `frontend/` | 页面、复习工作区、浏览器记录、API适配 / FE |
| `backend/app/`、`backend/tests/` | API、数据库、问答、执行器、后端测试 / BE |
| `modules/transcriber/` | 转写子进程与模型调用 / SYS |
| `deploy/`、`scripts/` | 启停、资源准备、备份恢复与冒烟 / SYS |
| `tests/`、`docs/05_测试与验收/` | 实际回归、用例和证据 / QA |
| `docs/` | 需求、方案、分工、交接与管理 / PM统筹 |
| `data/`、`models/`、`tools/`、`logs/`、`backups/` | 本机运行资源与产物，按规则忽略 |

组员从[先读文档](docs/00_用前先读.md)、[项目统一约定](docs/00_项目导航与统一约定.md)、[API契约](docs/03_技术方案与接口/02_API与数据模型契约.md)、[需求追踪](docs/02_任务分配与进度/05_需求工单与验收追踪.md)和[岗位开工单](docs/岗位开工单)开始；也可在本地打开 `docs/开始阅读.html`。历史资料按当时版本留存，当前行为以源码及对应验证记录为准。

开发前同步，使用各自功能分支提交 Pull Request；接口或配置变化同步交接说明，交付包含提交ID、验证记录和剩余问题。前端校徽素材来源见[前端说明](frontend/README.md)。
