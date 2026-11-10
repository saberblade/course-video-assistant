# 课迹 · 课程视频复习助手

北京邮电大学专业实训课设。面向中文录课复习，通过章节提要、课程问答、原文引用和时间定位，帮助学生找到相关讲解并核对课堂原话。

[项目仓库](https://github.com/saberblade/course-video-assistant)由产品经理兼组长、前端工程师、后端工程师、测试工程师和系统工程师共同维护。

## 当前进展

前端、后端、转写模块、顺序任务执行器和部署脚本均已合入 `main`。上传视频的处理链路已接通 `queued → transcribing → indexing → ready/failed`，后端可在构建产物存在时挂载 `frontend/dist/`。

| 模块 | 已提交内容 | 待完成事项 |
| --- | --- | --- |
| 产品与协作 | V1.3 需求、原型、分工、接口与交接资料 | 按实际交付更新产品验收记录 |
| 前端 | 首页、知识云台、视频复习页、Mock、课程 API 适配及悬浮助教；本机真实接口浏览器联调已通过 | 正式授权课程与生成式回答验收 |
| 后端 | 视频 API、SQLite、章节、BM25 检索、问答、任务执行器及静态托管接线 | 补齐模型响应异常处理、队列异常恢复、就绪判断与生产路由回退，完成正式样本验收 |
| 转写与部署 | faster-whisper 子进程模块、44 包依赖锁、部署/冒烟脚本与新机冷启动手册 | 目标设备准备资源并执行冷启动、正式转写和完整恢复验收 |
| 测试与证据 | 后端测试源码及 SYS 上传的环境、转写与端到端记录 | QA 复测正式授权样本和完整验收题集，冻结发布版本 |

SYS 提交的记录包含 Qwen 真实调用，以及合成中文样本的上传、转写、章节、生成式问答、拒答和删除结果。下文列出证据入口。克隆仓库只获取源码和文档，虚拟环境、工具二进制、模型、密钥、样本视频及构建产物需要在运行设备上另行准备。

## 中期后推进（11月10日核对）

当前阶段以真实视频复习闭环和异常恢复为主。源码已提交、开发验证和正式验收分别登记，阶段完成度不代表测试通过率。

| 主责 | 优先任务 | 验证依据 |
| --- | --- | --- |
| BE | 模型返回非 JSON、空 `choices`、字段错误等受控降级；任务认领/写入异常后的恢复；真实就绪判断；SPA 路由回退 | [模型调用](backend/app/qa.py)、[执行器](backend/app/executor.py)、[健康检查](backend/app/routers/health.py)、[服务入口](backend/app/main.py)及待补充的回归测试 |
| FE | 真实 API 下的上传、状态恢复、问答、引用定位、重试和删除；生产页面刷新及错误提示 | 浏览器请求、生产构建与引用定位记录 |
| SYS | 目标电脑依赖与完整模型、预热状态、冷启动、隔离备份恢复及代码/数据版本匹配 | [冷启动手册](deploy/03_新机冷启动部署手册.md)与目标机实际记录 |
| QA | 正式授权录课、20 道正题加 5 道无依据题、引用支持、性能及故障恢复的独立回归 | [测试计划](docs/05_测试与验收/01_测试计划与验收门槛.md)与[实际验收记录](docs/05_测试与验收/03_测试结果与发布验收记录.md) |
| PM | 冻结范围、协调接口与样本、核对证据并作验收决定 | 候选提交、任务回执及未解决问题清单 |

章节提要当前按 60 秒窗口抽取原句；知识地图、学习分析与薄弱预警来自前端预设数据，尚无对应真实分析服务。全局助教保持内置使用指引。问答记录虽已写入数据库，当前未提供历史查询 API，前端刷新清空本页会话；历史恢复列为主链路验收后的可选扩展。

## 先查看前端界面

准备 Node.js 22，版本至少为 22.12。首次获取项目时执行以下命令。

```powershell
git clone https://github.com/saberblade/course-video-assistant.git
cd course-video-assistant
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run dev
```

已有本地仓库的成员在工作区干净时运行 `git pull --ff-only`，再执行 npm 命令。本机项目目录为 `D:\code\course-video-assistant`，其他成员可使用自己的目录。Windows PowerShell 使用 `npm.cmd`，其他终端可使用 `npm`。

打开 `http://localhost:5173/`。若端口已占用，可运行 `npm.cmd --prefix frontend run dev -- --port 5174`，以终端显示的地址为准。

| 页面 | 内容 |
| --- | --- |
| `/` | 产品介绍，点击“进入知识云台”进入工作区 |
| `/screen` | 课程知识导航：从真实章节和来源原文进入回看 |
| `/screen?view=library` | 上传、课程列表与处理进度 |
| `/screen?view=analysis` | 复习进度：当前视频的手动章节标记 |
| `/screen?view=weak` | 待复习清单：本地疑问备注、回看与解决状态 |
| `/videos/:id` | 从课程列表打开具体视频，查看播放器、转写、章节与课程问答 |

开发环境默认使用前端 Mock，刷新后 Mock 课程记录恢复初始状态。连接真实接口后，课程知识导航按视频章节展示来源和回看入口；复习进度与待复习清单基于用户在当前浏览器留下的手动标记和备注，不计算知识掌握程度。复习记录暂不跨设备同步，8000 与 5173 的本地存储相互独立。悬浮助教默认提供内置的站内使用指引。课程问答位于具体视频的复习页。详见[前端调整记录](docs/07_管理记录/06_前端复习逻辑调整_2026-11-10.md)。

## 准备完整运行环境

以下命令均在仓库根目录的 PowerShell 中执行。Python 基线为 3.11，后端与转写依赖按根目录锁文件安装。

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
if (-not (Test-Path .env.local)) { Copy-Item .env.example .env.local }
```

新电脑可按[新机冷启动部署手册](deploy/03_新机冷启动部署手册.md)选择从已就绪设备拷贝资源或联网准备环境。该手册已补齐操作步骤和验收记录模板，目标机部署结果需实际执行后登记。

首次启动前，由 SYS 准备以下本机文件和配置。

| 项目 | 准备要求 |
| --- | --- |
| FFmpeg / ffprobe | 安装后加入 PATH，或在根目录 `.env.local` 中为 `FFMPEG_BIN`、`FFPROBE_BIN` 设置实际路径。便携工具可放在 `tools/ffmpeg/` |
| 转写模型 | 准备完整的 faster-whisper small 模型目录，默认 `models/faster-whisper-small/`，多语言、CPU int8 |
| 模型 API | 按实际百炼账户填写 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL=qwen-plus` |
| 前端构建 | 使用 Node.js 22 与前端锁文件执行 `npm ci` 和 `npm run build` |

模型下载器 `scripts/download_model_bin.py` 仅下载并校验 `model.bin`。完整模型还需相同模型仓库与 revision 的配置、分词等配套文件，来源以脚本中的 `REPO` 和 `REVISION` 为准。按[模型准备说明](deploy/02_模型准备说明.md)组织文件，再执行转写验收确认可加载。模型文件和便携工具均未包含在 Git 仓库中。

根目录 `.env.local` 由后端读取，系统环境变量优先。前端开关写在独立的 `frontend/.env.local`。密钥仅由服务端保存与读取。当前 SQLite 路径为 `DATA_DIR/app.db`，旧配置样例中的 `DATABASE_URL` 尚未被代码读取。

## 一条命令启动

依赖装好、`.env.local` 配置就绪后，在项目根目录执行：

```powershell
.\start.cmd
```

后端（8000）与 Vite 开发服（5173）各开一个窗口，两边就绪后自动打开浏览器；已在运行的端口会被跳过，不会被强杀。首次使用前仍需执行一次 `npm.cmd --prefix frontend ci`；缺少 `frontend/dist` 时会提示先构建。

关闭：

```powershell
.\stop.cmd
```

`stop.cmd` 先查任务队列，存在 `queued/transcribing/indexing` 的任务时拒绝关闭，避免任务变成 `PROCESS_INTERRUPTED`；确实要强行关闭用 `.\stop.cmd -Force`。直接关掉那两个窗口也可以。脚本实现在 `deploy/start-all.ps1` 与 `deploy/stop-all.ps1`，根目录的 `.cmd` 只是免去敲长命令的封装。

## 构建与启动完整版本

环境、模型和配置就绪后执行以下命令。

```powershell
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run build
powershell -ExecutionPolicy Bypass -File .\deploy\start.ps1
```

默认访问地址如下，修改 `APP_PORT` 后以脚本输出为准。

| 地址 | 用途 |
| --- | --- |
| `http://127.0.0.1:8000/` | 同源前端页面 |
| `http://127.0.0.1:8000/docs` | API 文档 |
| `http://127.0.0.1:8000/api/health` | 健康检查 |

启动脚本使用本机 `.venv`，默认前台运行，一个 Uvicorn worker，端口从根目录 `.env.local` 的 `APP_PORT` 读取。后端在启动时检查 `frontend/dist/index.html`，存在则挂载静态页面，缺失则仅启动 API；先构建再启动，构建后需重启服务。`FrontendFiles` 为 `/screen`、`/videos/:id` 提供页面入口，开发版与同源部署版的直接访问和刷新已在 Windows Chrome 验证；缺失 API 和静态资源仍返回 404。

执行器默认开启，后台预热模型并按顺序处理上传任务。模型缺失或加载失败时查看服务日志与具体任务错误。`/api/health` 当前按模块入口文件是否存在报告 `transcriber`，按配置字段是否齐全报告 `llm_configured`，实际转写和模型连通需要分别验证。

## 开发联调与问答模式

开发期可同时运行后端与 Vite。在 `frontend/.env.local` 写入以下配置，重启前端开发服务以使用真实课程接口。

```dotenv
VITE_USE_MOCK=false
```

也可复制 `frontend/.env.example` 为 `frontend/.env.local`；该示例默认关闭悬浮助教扩展 API。本次联调的本机配置、结果和重启步骤见[前后端联调记录（2026-11-10）](docs/05_测试与验收/07_前后端联调记录_2026-11-10.md)。

Vite 将 `/api` 代理到 `http://127.0.0.1:8000`。未设置开关时，开发模式默认启用 Mock，生产构建默认使用真实课程 API。构建所用的 `VITE_*` 配置在构建时生效，修改后重新构建。

后端在有有效转写依据、生成开启且模型调用成功时返回 `answered/generative`。无有效依据时返回 `not_found`。关闭生成、缺少配置或模型故障且检索命中原文时走 `degraded/extractive` 分支，不能据此判定生成式问答已验收。

悬浮助教的 `VITE_ASSISTANT_USE_API=true` 开关对应 `POST /api/assistant/chat`，请求体为 `{"messages":[{"role":"user","content":"…"}]}`，响应为 `{"answer":"…","mode":"generative|guide"}`。该接口只回答站内使用问题，不读课程数据、不写数据库；同一时刻只放一个请求进模型（并发时返回 429 `ASSISTANT_BUSY`），未配置模型或模型超时降级为 `guide` 并在正文说明，问题超过 300 字符返回 422。前端默认仍使用内置指引，确认后再打开开关并重新构建。课程问答接口为 `POST /api/videos/{video_id}/questions`。详见[前端说明](frontend/README.md)与[后端说明](backend/README.md)。

## 检查与现有证据

安装完整锁文件后，可在仓库根目录执行后端测试和前端类型检查。

```powershell
.\.venv\Scripts\python.exe -m pytest -c backend/pytest.ini backend/tests -q
npm.cmd --prefix frontend run typecheck
```

后端单元测试通过 fixture 设置 `TASK_EXECUTOR_ENABLED=0`，避免启动真实转写队列。真实模型连通、转写与端到端测试分别由 `scripts/llm_smoke_test.py`、`scripts/test_transcriber.py`、`scripts/e2e_smoke.py` 提供，准备要求见[运行脚本说明](scripts/README.md)。

`e2e_smoke.py` 使用 `data/tmp/sample_lecture.mp4`，会先尝试删除列表第一页的已有可删除视频，结束时删除本次上传样本，仅在专用演示测试数据中执行。`scripts/make_sample_video.ps1` 可通过 Windows 中文 TTS 与 FFmpeg 生成链路样本。

以下为 SYS 上传的 2026 年 11 月 9 日记录，代表其测试机和对应样本的结果。本轮 README 更新核对了源码与存档，未在当前电脑重新安装环境、下载模型或复跑这些测试。

| 检查 | 已提交的记录 | 证据入口 |
| --- | --- | --- |
| 环境与构建 | Python 3.11、Node 22、FFmpeg 版本及前端构建记录；后端锁文件共 44 个包 | [环境版本清单](docs/environment-versions.md) |
| 后端测试 | SYS 记录为 36 passed，完整目标机复测由 QA 登记 | [SYS 部署记录](deploy/01_SYS环境与部署记录.md) |
| 转写模块 | 7 项 PASS，覆盖预热、正常转写、并发、取消恢复、无效文件、无音轨与关闭 | [转写验收 JSON](deploy/evidence/logs_transcriber_acceptance.json) |
| 端到端 | 116.88 秒 TTS 样本，处理 elapsed_sec 为 66.0，上传至就绪轮询用时 68.3 秒；16 段转写、2 个章节、生成式回答和无依据拒答均有记录 | [端到端 JSON](deploy/evidence/logs_e2e_local_run.json) |

正式 3–5 分钟授权录课的处理时间目标、20 道正题加 5 道无依据题的验收、完整备份回退及发布 tag 冻结仍待团队完成。单段合成样本和单次问答结果不足以代表正式性能与产品质量验收。

## 停止、备份与恢复

等待任务与问答结束后，可在启动终端按 Ctrl+C 停止服务。部署脚本位于 `deploy/`，SYS 已上传演练记录，实际操作先核对服务状态和备份目录。

| 脚本 | 当前用途 |
| --- | --- |
| `start.cmd` / `stop.cmd` | 根目录入口，一条命令启停前后端两个窗口 |
| `deploy/start-all.ps1` | 启动后端与 Vite 开发服，轮询 `/api/health` 确认就绪后打开浏览器 |
| `deploy/stop-all.ps1` | 先查任务队列再停止两个服务，队列未清零时需 `-Force` |
| `deploy/start.ps1` | 检查环境并前台启动服务 |
| `deploy/stop.ps1` | 按 Uvicorn 命令行匹配终止进程，使用前核对目标 PID |
| `deploy/backup.ps1` | 停服后备份数据、源码、构建产物及清单，默认保留 7 份 |
| `deploy/restore.ps1 -BackupPath backups/实际备份目录` | 停服后恢复数据与 `frontend/dist`，代码版本需另外匹配 |

备份与恢复脚本按默认 `data/` 目录工作。修改 `DATA_DIR` 的环境需由 SYS 对齐脚本后执行。恢复采用复制方式，正式回退还需检查现有文件、数据和代码版本是否一致，按[部署说明](deploy/README.md)及交接清单验证。

## 技术栈与目录

| 路径或层次 | 内容 | 主责 |
| --- | --- | --- |
| `frontend/` | Vue 3、TypeScript 5、Vite 7、Vue Router 4、Element Plus 2、Axios 1 | FE |
| `backend/app/` | FastAPI、Pydantic 2、SQLAlchemy、SQLite、jieba、BM25、httpx 与顺序执行器 | BE，SYS 协作 |
| `modules/transcriber/` | faster-whisper 多语言 small、CPU int8、可终止子进程 | SYS |
| `scripts/`、`deploy/` | 环境准备、测试、启动与备份恢复 | SYS |
| `backend/tests/`、`tests/` | 自动化测试、团队用例与实际验收证据 | BE、QA |
| `docs/` | 需求、任务、接口、交接与管理记录 | PM 统筹，各岗位协作 |
| `data/`、`models/`、`logs/`、`backups/`、`tools/` | 本机运行数据、模型、工具和产物 | 在各自电脑准备 |

前端按 `frontend/package-lock.json` 安装，完整 Python 依赖按 `requirements.lock.txt` 安装。大模型采用百炼 qwen-plus，具体账户地区与可用基础地址由 SYS 在本机配置。原有[技术选型](docs/03_技术方案与接口/05_技术栈定稿与选型决策.md)与[实际环境版本](docs/environment-versions.md)共同作为交接依据。

## 团队资料与协作

- [组员先读](docs/00_用前先读.md)
- [项目基线与阶段节点](docs/00_项目导航与统一约定.md)
- [需求工单与验收追踪](docs/02_任务分配与进度/05_需求工单与验收追踪.md)
- [各岗位开工单](docs/岗位开工单)
- [团队 API 契约](docs/03_技术方案与接口/02_API与数据模型契约.md)
- [产品与工程验收资料](docs/05_测试与验收)
- [新机冷启动部署与验收记录模板](deploy/03_新机冷启动部署手册.md)

分类查阅资料时，将仓库克隆或下载到本地，再用浏览器打开 `docs/开始阅读.html`。历史交接文档中的 `course-review` 指本仓库根目录，阶段完成情况以对应提交、实测证据和成员回执为准。

开发前同步代码，在各自功能分支修改，完成后提交 Pull Request。BE 复核本次 `executor.py`、`main.py` 及测试 fixture 的接线改动，QA 按同一题集复测。新增接口或功能时同步更新契约和验收要求。模拟调研、预设教学数据、合成链路样本和正式授权录课应分别标明来源。

仓库已配置 `.gitignore`，本机密钥、依赖、模型、录课、数据库、日志、工具和构建产物按规则忽略。授权课程样本与模型另行准备。前端校徽素材来源见[前端说明](frontend/README.md)。
