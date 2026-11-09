# SYS 环境与部署记录（2026-11-09）

主责 SYS。本记录汇总 M1/M2 证据、今日接入工作（转写执行器、同源托管、预热线程、部署脚本）与实测数据。
历史详情见 `deploy/evidence/01_M1_环境验证记录.md`（M1）与 `deploy/evidence/02_M2_转写模块验收记录.md`（M2）。
环境版本清单见 `docs/environment-versions.md`。所有数值均为本机实测，未实测一律标"待"。

## 1. 今日接入概览（仓库 course-video-assistant-main）

M2 前把 course-review 里完成的 SYS 交付物并入团队仓库，并补齐契约要求的"排队执行器"拼图：

| 交付物 | 位置 | 说明 |
| --- | --- | --- |
| 转写模块源码 | `modules/transcriber/` | 仓库内验收 7/7 PASS（logs/transcriber_acceptance.json） |
| 依赖锁文件 | `requirements.lock.txt` | 44 包（后端+转写），sha256 见版本清单 |
| 可执行工具链 | `tools/ffmpeg`(6.1.1)、`tools/node22`(v22.23.4) | 便携版，不入库（.gitignore），来源 npmmirror |
| 本地模型 | `models/faster-whisper-small/` | model.bin sha256 与 HF LFS OID 一致 |
| 任务执行器 | `backend/app/executor.py` | 新增（SYS 编写，**待 BE 复核合并**），串起 queued→transcribing→indexing→ready/failed |
| 生命周期接线 | `backend/app/main.py` | 集中三行：执行器启动/停止（TASK_EXECUTOR_ENABLED 可关）、转写预热线程、frontend/dist 同源托管 |
| 静态托管验证 | `frontend/dist`（构建产物） | GET / 与 /assets 均 200；/api、/docs 优先级不受影响 |
| 端到端冒烟 | `scripts/e2e_smoke.py` | 全链路真实通过，见第 3 节数据 |
| 部署脚本 | `deploy/start|stop|backup|restore.ps1` | 全部实机演练，见第 4 节 |
| 今日脚本修复 | `scripts/make_sample_video.ps1` | ffprobe JSON 解析修复（PS 5.1 GBK 解码坑） |

## 2. 后端测试与模块验收（仓库内）

- `pytest -c backend/pytest.ini backend/tests -q` → **36 passed**（含按模块就位更新的健康检查用例）。
- 转写模块 7 项验收在仓库 venv 复跑 → **7/7 PASS**（数据存 `logs/transcriber_acceptance.json`）。
- README 现状中"转写任务执行器、模型模块…待接入"已对应落地；git 冻结待团队操作。

## 3. 端到端真实冒烟（LLM 密钥未配置，问答走 degraded）

命令：`deploy/start.ps1` 后执行 `.venv\Scripts\python.exe -X utf8 scripts\e2e_smoke.py`。
证据完整存档：`logs/e2e_local_run.json`（video_id=499c1a06-39b1-4458-9403-68bba2d8df86）。

| 步骤 | 实测 |
| --- | --- |
| GET /api/health | 200，status=ok，transcriber=ready，llm_configured=false |
| 上传样本（116.88 s / 1,050,195 B） | 202 Accepted → queued |
| 执行器认领 | 立即 transcribing（idle 轮询 1 s） |
| 转写（small, CPU int8，预热后） | 墙钟 **46 s**（16 段；transcribing起讫与 elapsed_sec=46.0 一致） |
| 章节生成 | 2 个 60 秒窗口章节，段引用 id 与转写一致 |
| 问答1"召回率怎样计算？" | 200 / **degraded** / extractive，5 条真实候选引用，引用文本经与转写逐字比对一致 |
| 问答2 无依据问题 | 200 / degraded（弱相关仍返回 5 候选，见偏差 D-08） |
| 删除 | 204 → 再次 404（幂等），列表归零 |

不足 1 分钟即可完成"上传→转写→章节→问答→删除"，链路无人工干预。

## 4. 部署脚本实机演练（M3 交付）

| 脚本 | 结果 | 备注 |
| --- | --- | --- |
| deploy/start.ps1 | OK | 检查 venv/.env.local/模型/端口后启动（1 worker、无 --reload） |
| deploy/stop.ps1 | OK | 仅按命令行匹配本服务； venv 启动器+底层解释器双进程均正确停止；二次运行为空操作 |
| deploy/backup.ps1 | OK | 服务运行中会拒绝；停止后备份 `backups/20261109_182247/`（70+ 文件，MANIFEST 含 3 项 sha256 与版本/git 状态），Keep 轮转参数就绪 |
| deploy/restore.ps1 | OK | 恢复后 app.db 哈希与备份一致（B0575AF1…），pre_restore 安全副本与端口占用保护均触发验证 |

正式 M4（11-12）将按契约做完整备份/回退演练并清点队列异常路径。

## 5. 偏差与教训登记（接续 M1/M2 的 D-01~D-07）

- **D-08（待 QA/BE 裁定）**：契约"无候选→not_found"，但检索实现无相关性阈值，BM25 对任何问句都给出 5 个候选 → 无依据问题返回 degraded 而非 not_found。影响：拒答路径验收可能展示为降级。建议 BE 增加候选分数阈值或在 qa 层判定"可引用"下限；e2e 脚本已改为记录实测值不断言。
- **D-09（已修复）**：PS 5.1 用控制台 GBK 解码原生程序 stdout，ffprobe 输出含中文路径的 UTF-8 JSON 时引号被吞→解析失败。修复：脚本改为 cmd 重定向到文件后再按 UTF8 读取（make_sample_video.ps1）。
- **D-10（已修复，重要给 BE）**：SQLAlchemy session 设 autoflush=False（默认值在 app/database.py 会话配置中显式关闭），执行器"插入分段后立即 select"拿到空集→章节为 0→summary 409。修复：插入后 `db.flush()`（executor.py）。回归：36 tests + e2e 全通过。
- **D-11（已修复）**：backup.ps1 初版误用 robocopy 复制单文件 data\app.db（robocopy 只接受目录，exit 16）。修复：单文件改 Copy-Item。
- **D-12（记录）**：一个服务在任务管理器呈现两个 python.exe（venv 启动器 + 底层解释器），stop.ps1 按命令行匹配两者，避免"只停一半"。
- **D-13（已解决）**：新建百炼 key 曾带"API-Key restrictions"（IP 白名单/业务空间限制），探测返回 `403 access_denied`；用户在控制台解除后同 key 生效（0.30s 200）。交接：给 QA/BE 建 key 用**默认业务空间 + 不设 IP 白名单**。
- **D-14（判定，不采用）**：外部中转站（ChatGPT 类，`zz-api.cc.cd`）作为"qwen 备选"被尝试：其 Cloudflare WAF 对**所有服务端程序化调用**返回 403（本机 httpx/UA/curl 三种指纹 + 异地出口共 4 次），浏览器可开控制台但 API 不可用 → 判定不能作为后端模型源；未采用、无契约变更（qwen-plus 本就是基线）。

## 6. 待办（阻塞/移交）

1. ~~Qwen 真实调用~~ → **✅ 2026-11-09 完成**：冒烟 0.42s PASS；全链路 `answered`（generative+真实引用）与 `not_found`（诚实拒答）实证；端点与 request_id 见证据 01 第 5 节。**移交**：首次批量验收前在控制台核对免费额度与用量提醒（预算 duties：PM 确认 30 元上限口径）。
2. **正式 3–5 分钟授权样本**：QA/PM 交付后在目标机复测，更新"≤8 分钟"验收（未测前不写达标）。补充：116.88s 样本多次实测 44–66s 波动（受机内负载影响），正式复测按空闲机执行。
3. **git 冻结**：仓库 commit + tag（M3 要求"不能只写最新版"）；MANIFEST 已支持记录 commit。
4. **BE 复核**：executor.py / main.py / conftest.py / test_be01.py 四处改动请 BE 过目（均为可回退的最小接线）。
5. **FE**：dist 构建已验证（npm ci + build 通过，同源托管已上线）；前后端联调时注意 App 内 Mock 仍默认，需切真实 API。
