# 课迹 · 课程视频复习助手

北京邮电大学专业实训课设。面向中文录课复习，围绕章节提要、课程问答、原文引用和时间定位，帮助学生找到相关讲解并核对课堂原话。

项目仓库为 [saberblade/course-video-assistant](https://github.com/saberblade/course-video-assistant)。团队由产品经理兼组长、前端工程师、后端工程师、测试工程师和系统工程师组成。

## 当前进展

前端和后端源码已合入 `main`。前端包含产品首页、知识云台、课程列表、视频复习页和悬浮助教，开发环境默认使用前端 Mock。后端已提交 FastAPI 服务、SQLite 数据模型、视频接口、章节提要、BM25 检索、模型问答逻辑及自动化测试源码。转写模块（faster-whisper small CPU int8，本地模型目录已就位）、顺序任务执行器、启动/停止/备份脚本和 `frontend/dist` 同源托管已接入并通过本机端到端冒烟（详见 `deploy/01_SYS环境与部署记录.md`）；qwen-plus 真实调用仍在等待密钥配置。

| 模块 | 当前仓库状态 | 后续交付 |
| --- | --- | --- |
| 产品与协作资料 | 已提供 V1.3 需求、原型、分工、接口和交接资料 | 按实际交付持续维护验收记录 |
| 前端 | 已提交页面源码、Mock、API 适配和构建配置 | 与真实后端联调并提交运行、构建和验收证据 |
| 后端 | 已提交 API、数据库、媒体校验、章节、检索、问答和重试删除逻辑 | 复核 `app/executor.py` 执行器接线，完成前后端联调与真实样本验收 |
| 转写与部署 | 已提交本地转写模块、依赖锁文件、模型目录说明、启动/停止/备份/恢复脚本与端到端冒烟脚本 | qwen-plus 真实调用验收、正式 3–5 分钟样本复测、git 提交/tag 冻结 |
| 测试 | 已提供产品验收资料，并提交 `backend/tests/` 后端测试源码 | 在目标环境执行并记录结果，补齐真实媒体、模型服务和端到端验收 |

Mock 中的上传、处理进度和问答结果为前端模拟。知识地图、学习分析和薄弱预警使用预设教学数据。悬浮助教默认使用内置的站内使用指引。后端已有 SQLite 持久化和问答逻辑；`modules/transcriber` 与顺序执行器已接线，上传视频会经 `queued → transcribing → indexing → ready` 推进（本机 116.88 秒样本端到端约 46 秒完成转写），无密钥时问答返回 `degraded` 原文检索模式。问答生成式验收待 qwen-plus 真实调用完成后进行。

## 快速启动前端

准备 Node.js 22，版本至少为 22.12。首次获取项目可执行以下命令，仓库目录可放在自己的开发目录中。

```powershell
git clone https://github.com/saberblade/course-video-assistant.git
cd course-video-assistant
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run dev
```

已经有本地仓库的成员，在工作区干净时使用 `git pull --ff-only` 同步代码，再从仓库根目录执行两条 npm 命令。本机现有项目位于 `D:\code\course-video-assistant`。

浏览器打开 `http://localhost:5173/`。若 5173 端口已被占用，可运行 `npm.cmd --prefix frontend run dev -- --port 5174`，以终端实际输出的地址为准。Windows PowerShell 使用 `npm.cmd`，其他终端可使用 `npm`。

### 可查看的页面

| 路径 | 内容 |
| --- | --- |
| `/` | 产品介绍，点击“进入知识云台”进入工作区 |
| `/screen` | 示例知识地图 |
| `/screen?view=library` | 上传、课程列表和模拟处理进度 |
| `/screen?view=analysis` | 示例学习分析 |
| `/screen?view=weak` | 示例薄弱预警 |
| `/videos/:id` | 从课程列表打开具体视频，查看播放器、转写、章节提要和课程问答 |

默认开发模式下无需模型密钥即可浏览前端 Mock。刷新页面后 Mock 课程记录恢复初始状态。课程内容提问入口位于具体视频的复习页，悬浮助教用于项目介绍和站内操作指引。

## 启动后端服务

按项目技术基线使用 Python 3.11。在仓库根目录打开 PowerShell，首次准备时执行以下命令。

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
if (-not (Test-Path .env.local)) { Copy-Item .env.example .env.local }
```

随后启动服务，保持该终端运行。

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --workers 1
```

接口文档位于 `http://127.0.0.1:8000/docs`，健康检查为 `GET /api/health`。当前缺少转写模块时，健康接口按代码返回 HTTP 503、`status=not_ready`、`transcriber=missing`，其他已实现接口可分别检查。健康检查中的 `llm_configured` 仅检查配置是否齐全，真实模型连通需要另测。

视频上传需要 FFmpeg 套件中的 `ffprobe` 可用，或通过 `FFPROBE_BIN` 指定其路径。后端默认将数据库与视频写入仓库根目录 `data/`。当前 SQLite 路径由 `DATA_DIR` 派生为 `app.db`，旧环境样例中的 `DATABASE_URL` 尚未被实现读取。

后端直接依赖列在 `backend/requirements.txt`，开发测试依赖列在 `backend/requirements-dev.txt`。本轮 README 更新根据源码核对运行配置，后端依赖安装、服务启动和测试结果仍需在目标环境执行并留存证据。详见[后端运行说明](backend/README.md)。

## 后端联调与配置

课程 API 适配已经放在 `frontend/src/api/videos.ts`，公共类型放在 `frontend/src/types/index.ts`。接口以[团队 API 契约](docs/03_技术方案与接口/02_API与数据模型契约.md)为基线。

后端服务运行在 `http://127.0.0.1:8000` 后，在 `frontend/.env.local` 写入以下配置，重启前端开发服务即可切换真实课程接口。当前可先核对列表、上传受理和错误响应，转写到问答的完整链路需继续接入任务执行器。

```dotenv
VITE_USE_MOCK=false
```

开发服务通过 `frontend/vite.config.ts` 将 `/api` 请求代理到后端，保留 `/api` 路径。开发环境未设置开关时默认启用 Mock，生产构建未设置开关时默认使用真实课程 API。

悬浮助教有独立开关 `VITE_ASSISTANT_USE_API=true`，对应 `POST /api/assistant/chat`。这是前端预留的扩展接口，当前仓库尚无对应后端实现。后端工程师和产品经理确认接口及范围后再开启，具体格式见[前端说明](frontend/README.md)。

后端已实现根目录 `.env.local` 的配置加载，系统环境变量优先。系统工程师按实际账户配置 `LLM_BASE_URL`、`LLM_API_KEY` 和 `LLM_MODEL=qwen-plus`。缺失模型配置、生成被关闭或模型请求故障时，命中原文的问答走提取式降级分支；无有效原文依据时返回 `not_found`。模型密钥仅由服务端读取。

根目录 `.env.example` 同时包含未来转写模块所需的字段，具体读取情况见后端说明。它与 `frontend/.env.local` 的前端开关分别维护。

## 检查与构建

在仓库根目录执行以下命令。

```powershell
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend run build
```

构建产物位于 `frontend/dist/`。当前后端仅注册 API 路由，前端静态托管和页面路由回退尚待实现。开发期在第二个终端运行 Vite，浏览器访问 `http://localhost:5173/`；正式交付方案为 FastAPI 同源托管。

后端已有媒体校验、上传与文件响应、数据库、检索、章节和问答分支等测试源码。在仓库根目录执行以下命令。

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -c backend/pytest.ini backend/tests -q
```

测试使用临时数据、模拟媒体探测或模型响应等方式检查代码行为，真实转写、模型 API 连通和端到端产品验收需分别记录结果。

## 技术栈

| 层次 | 采用方案 |
| --- | --- |
| 已提交前端 | Vue 3、TypeScript 5、Vite 7、Vue Router 4、Element Plus 2、Axios 1 |
| 已提交后端 | FastAPI、Pydantic 2、SQLAlchemy、SQLite；项目运行基线为 Python 3.11 |
| 音视频与转写方案 | FFmpeg / ffprobe、faster-whisper 多语言 small、CPU int8 |
| 已提交检索与问答逻辑 | jieba、rank-bm25、httpx 调用百炼 qwen-plus；真实连通待验证 |
| 演示交付方案 | Windows 本机、FastAPI 同源托管前端构建产物 |

前端依赖按 `frontend/package-lock.json` 安装。后端已提交精确版本的直接依赖清单，当前包括 SQLAlchemy 2.1.8；完整传递依赖锁定、目标环境安装和转写依赖仍由系统工程师组织验证。详细技术基线见[技术栈定稿](docs/03_技术方案与接口/05_技术栈定稿与选型决策.md)。

## 项目目录与负责人

| 路径 | 用途 | 主责 |
| --- | --- | --- |
| `frontend/` | 页面、交互、播放器、Mock 与接口适配 | 前端工程师 |
| `backend/app/` | API、数据库、任务、检索与问答 | 后端工程师 |
| `modules/transcriber/` | 本地语音模型及转写进程封装 | 系统工程师 |
| `scripts/`、`deploy/` | 环境准备、运行、部署与备份交付 | 系统工程师 |
| `backend/tests/` | 后端自动化测试源码 | 后端工程师、测试工程师 |
| `tests/` | 团队用例、脱敏样例与实际验收证据 | 测试工程师 |
| `docs/` | 需求、任务、接口、交接与管理记录 | 产品经理兼组长统筹，各岗位协作 |
| `data/`、`models/`、`logs/`、`backups/` | 本机数据、模型、日志与备份 | 本机准备和运行生成 |

## 团队资料与协作

- [组员先读](docs/00_用前先读.md)
- [项目基线与阶段节点](docs/00_项目导航与统一约定.md)
- [需求工单与验收追踪](docs/02_任务分配与进度/05_需求工单与验收追踪.md)
- [各岗位开工单](docs/岗位开工单)
- [环境准备与启动约定](docs/03_技术方案与接口/03_环境配置与运行部署.md)
- [产品与工程验收资料](docs/05_测试与验收)

需要分类查阅资料时，将仓库克隆或下载到本地，再用浏览器打开 `docs/开始阅读.html`。历史交接文档中的 `course-review` 指本仓库根目录，各岗位按实际工程提交和证据更新状态。模拟调研、演练数据和真实实测记录需保持明确标注。

每项任务写清负责人、交付节点和验收条件。开发前同步代码，在各自功能分支修改，完成后提交 Pull Request，由相关工程师检查，产品经理确认需求与范围。新增后端接口或扩展功能时同步更新契约和验收要求。

本仓库已配置 `.gitignore`，本机密钥、依赖目录、模型、视频、数据库、日志和构建产物按规则忽略。授权课程样本和模型文件另行准备，在交接记录中注明来源和获取方法。前端校徽素材来源见[前端说明](frontend/README.md)。
