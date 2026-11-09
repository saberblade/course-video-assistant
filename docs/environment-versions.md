# environment-versions.md

SYS 实机记录的环境版本清单。契约要求见 docs/03_技术方案与接口/03_环境配置与运行部署.md（"版本清单与交接记录"）。
**口径：只记实测值；未实测/未冻结的项明确标"待"。记录时间 2026-11-09（本地 UTC+8）。**

| 检查项 | 应记录信息 | 实测值 | 状态 |
| --- | --- | --- | --- |
| 主机 | OS / CPU / 内存 / 磁盘 / 浏览器 | Windows 11 家庭中文版 build 26200 (AMD64)；Intel 13th Gen Core i7-13620H；物理内存 15.8 GB（采集时空闲 4.2 GB）；D 盘可用 238.8 GB；Microsoft Edge 157.0.4341.42 | 已记录 |
| Python | 3.11 完整版本与路径 | CPython 3.11.0，venv 位于 `D:\桌面\课程三\course-video-assistant-main\.venv`（`py -3.11 -m venv .venv` 创建） | 已记录 |
| Node | 22.x 且 ≥22.12 的完整版本与路径 | Node.js **v22.23.4**、npm 10.9.9，便携版 `D:\桌面\课程三\course-video-assistant-main\tools\node22\node.exe`（不改动全局 Node 24） | 已记录 |
| 后端依赖 | requirements.lock.txt 及校验值 | `requirements.lock.txt`，44 个锁定包；**sha256 = 65c7f7a00cc1c710ad52406899ccb1f33dfd784145da9f4922f298a3e752921d**（含 fastapi==0.162.0、sqlalchemy==2.1.8、pydantic==2.14.2、faster-whisper==1.2.1） | 已记录 |
| 前端依赖 | package-lock.json 及构建结果 | `frontend/package-lock.json` 已入库；2026-11-09 在本机 `npm ci` + `npm run build` 成功（vite，10.19s），产物 `frontend/dist/` 8 个文件共 1,670,883 B；构建告警：个别 chunk >500 kB（提示代码分割，非错误） | 已记录 |
| 音视频 | FFmpeg/ffprobe 版本与样本编码 | ffmpeg/ffprobe **6.1.1**（gyan.dev essentials build）`tools\ffmpeg\`；样本 `data/tmp/sample_lecture.mp4`：MP4/mov,mp4 → h264 1280x720 + AAC 16kHz mono，时长 116.88 s，大小 1,050,195 B（ffprobe 校验） | 已记录 |
| 转写 | faster-whisper/CTranslate2 版本、模型目录与校验 | faster-whisper 1.2.1（ctranslate2 4.8.5，av 18.1.0，onnxruntime 1.31.1，tokenizers 0.23.3，huggingface_hub 2.4.0）；模型目录 `models/faster-whisper-small/`，model.bin 483,546,902 B，**sha256 = 3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671**（与 HF openai/whisper-small LFS OID 一致，断网加载测试通过） | 已记录 |
| 大模型 | qwen-plus、地区、基础地址、测试 request_id | 大陆站兼容端点 `dashscope.aliyuncs.com/compatible-mode/v1` + qwen-plus；冒烟 PASS（request_id `chatcmpl-feb524f7-…`，0.42 s，24 tokens）；全链路 answered/not_found 实证见 `logs/e2e_local_run.json`；密钥只在服务端 `.env.local`，不入库不入文档 | ✅ 已实测（2026-11-09） |
| 发布版本 | commit/tag、打包时间、变更摘要 | 本地目录未 git init（团队仓库约定 GitHub saberblade/course-video-assistant）；**待团队冻结**：提交后打 tag，backup/MANIFEST 已可记录 commit。当前以 requirements.lock.txt sha256 + model.bin sha256 作为可复核锚点 | 待 git 冻结 |
| 备份回退 | 备份位置、版本、恢复检查记录 | 脚本 `deploy/backup.ps1`、`deploy/restore.ps1` 已实机演练：备份 `backups/20261109_182247/`（MANIFEST 含三项 sha256 与版本），restore 后 data/app.db 恢复哈希与备份一致（B0575AF1…）；端口占用保护、pre_restore 安全副本均触发验证 | 已演练（正式 M4 全面检查待做） |

## 依赖种子来源

- 后端框架层：`backend/requirements.txt`（8 个直接依赖）→ 实机安装后 \`pip freeze\` 冻结为根目录 `requirements.lock.txt`（含转写链路）。
- 前端：`frontend/package-lock.json` 由 FE 维护，本机仅按 lock 执行 `npm ci`，不升级版本。
- FFmpeg 6.1.1 与 Node 22.23.4 便携版来自 npmmirror 二进制镜像（存放于 `tools/`，不入库，见 .gitignore）。
- SQL noteworthy：SQLite 引擎由 app/database.py 创建（check_same_thread=False、timeout=30、外键开启）。

## 与契约数字的对照

- 3–5 分钟样本 ≤ 8 分钟：**未测**。当前样本仅 116.88 s（实测转写墙钟约 44–48 s，RTF≈0.4 外推乐观但**不得作为验收宣言**），待 QA/PM 提供正式授权样本后在目标机复测。
- 预算 30 元内部上限：2026-11-09 冒烟+e2e 已产生真实调用，首日全部落于新号免费额度，实付≈0（以控制台账单为准）；首次批量验收前由 PM 确认额度提醒/用量核对。
