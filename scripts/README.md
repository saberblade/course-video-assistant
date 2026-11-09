# 运行脚本

系统工程师维护的 Windows 环境准备、验收与冒烟脚本。全部在仓库根目录执行（PowerShell 5.1 兼容；`.ps1` 保持纯 ASCII，中文证据写 `logs/` 与 `deploy/evidence/`）。

| 脚本 | 用途 | 状态 |
| --- | --- | --- |
| `env_check.ps1` | 环境自检（Python/FFprobe/模型目录等） | 已测（M1） |
| `make_sample_video.ps1` | 用 Windows TTS 生成 `data/tmp/sample_lecture.mp4`（MP4/H.264/AAC，ffprobe 校验） | 已测 |
| `transcribe_test.py` | 转写测时（冷/预热、RTF） | 已测（冷 49.61 s / 预热 39.60 s @116.88 s） |
| `test_transcriber.py` | 转写模块 7 项验收（warmup/transcribe/busy/cancel/无效/无音轨/shutdown），证据写 `logs/transcriber_acceptance.json` | 仓库内复跑 7/7 PASS |
| `download_model_bin.py` | whisper-small model.bin 16 线程分块下载器（hf-mirror，含校验） | 已测（sha256 与 HF LFS OID 一致） |
| `llm_smoke_test.py` | qwen-plus 真实调用冒烟（读 `.env.local`） | ✅ 已测 PASS（2026-11-09：qwen-plus 0.42s/24 tokens，大陆兼容端点） |
| `e2e_smoke.py` | 后端全链路真实冒烟（上传→转写→章节→问答→删除），证据写 `logs/e2e_local_run.json` | 已测 PASS（2026-11-09） |

启动/停止/备份/恢复在 `deploy/`（start.ps1 / stop.ps1 / backup.ps1 / restore.ps1）。

[系统岗位开工单](../docs/岗位开工单/系统工程师.md)
