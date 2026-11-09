# 本地转写模块

SYS 已提交 `__init__.py` 和 `_worker.py`。模块采用 faster-whisper 多语言 small、CPU int8，在专用子进程中加载模型、检查音轨并转写，通过 JSON 行协议与父进程通信。

## 准备要求

在仓库根目录使用 Python 3.11 虚拟环境安装 `requirements.lock.txt`，准备 `models/faster-whisper-small/` 完整模型目录和 FFmpeg/ffprobe。模型和工具二进制由每台运行设备单独准备。

`scripts/download_model_bin.py` 仅下载并校验 `model.bin`，其 `REPO` 为 `Systran/faster-whisper-small`，revision 以脚本常量为准。配置、分词等配套文件需与同一来源一致，并通过真实预热和转写验证。详见[模型准备说明](../../deploy/02_模型准备说明.md)。

## 模块接口

| 接口 | 行为 |
| --- | --- |
| `warmup()` | 加载模型，幂等；返回本次加载秒数或 None |
| `transcribe(video_path, output_dir, timeout_sec=None)` | 同步等待转写，输入视频与输出目录均为绝对路径；返回含 id、start_sec、end_sec、text 的分段列表 |
| `cancel_current()` | 终止当前专用子进程，后续调用可重新启动 |
| `shutdown()` | 清理专用子进程 |
| `is_healthy()` | 检查 worker 存在并可 ping 通 |

模块内部限制单个活动转写，受控错误通过 `TranscriberError.code` 上报，并发调用可触发 `TranscriberBusy`。正常转写将 UTF-8 `transcript.json` 写入临时文件后原子替换。模块不修改业务数据库或视频状态。

## 后端接入与配置

`backend/app/executor.py` 已调用本模块，在后台顺序推进 queued、transcribing、indexing、ready/failed，并将片段和章节写入数据库。执行器默认开启，关闭开关为 `TASK_EXECUTOR_ENABLED=0`。

模块读取 `WHISPER_MODEL_DIR`、`WHISPER_DEVICE`、`WHISPER_COMPUTE_TYPE`、`WHISPER_LANGUAGE` 和 `TASK_TIMEOUT_SECONDS`，默认转写期限 1200 秒。运行服务时根目录 `.env.local` 由后端加载；直接运行模块脚本时，配置读取方式以该脚本实现为准。

## 验收与当前边界

准备完整模型、工具和 `data/tmp/sample_lecture.mp4` 后，在仓库根目录运行以下命令。

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts\test_transcriber.py
```

脚本覆盖预热、正常转写、并发与超时、取消恢复、无效视频、无音轨和关闭。SYS 上传的[验收 JSON](../../deploy/evidence/logs_transcriber_acceptance.json)记录 7 项 PASS，本轮文档更新未在当前电脑重新执行。

已提交链路证据使用 116.88 秒的中文 TTS 合成样本。正式 3–5 分钟授权录课的转写质量与性能仍需复测，不能将合成样本耗时作为正式验收结论。

[模块验收说明](../../deploy/evidence/02_M2_转写模块验收记录.md) · [接口与模型契约](../../docs/03_技术方案与接口/02_API与数据模型契约.md)
