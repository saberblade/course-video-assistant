"""打包入口：双击 课迹.exe 即启动服务并打开浏览器。

设计要点：
- 所有“大件”（模型、FFmpeg、前端构建产物、数据）都放在 exe 同级的目录里，
  不塞进 _internal，方便替换与查看；exe 只负责跑 Python 服务。
- 数据库迁移在启动时自动执行；失败也不阻塞启动（会打印原因）。
- 关闭控制台窗口即停止服务。
"""

from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path


def base_dir() -> Path:
    """exe 所在目录（打包后）或仓库根目录（源码运行）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


# Windows 控制台默认 GBK，Python 默认 UTF-8 输出会变乱码，这里对齐控制台编码
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="gbk", errors="replace")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass

BASE = base_dir()
os.chdir(BASE)

# 转写子进程模式：同一个 exe 换个参数进来，只跑 worker，不开服务
if "--transcriber-worker" in sys.argv:
    from modules.transcriber._worker import main as worker_main

    worker_main()
    raise SystemExit(0)  # 让 ./data、./models、.env.local 都相对 exe 目录解析

HOST = os.environ.setdefault("APP_HOST", "127.0.0.1")
PORT = os.environ.setdefault("APP_PORT", "8000")

# 优先用随包携带的 FFmpeg，其次才是 PATH
_ffmpeg = BASE / "tools" / "ffmpeg" / "ffmpeg.exe"
if _ffmpeg.is_file():
    os.environ.setdefault("FFMPEG_BIN", str(_ffmpeg))
    _ffprobe = _ffmpeg.with_name("ffprobe.exe")
    if _ffprobe.is_file():
        os.environ.setdefault("FFPROBE_BIN", str(_ffprobe))


def run_migrations() -> None:
    """把库结构升到最新；旧库会被 env.py 自动标记基线后增量升级。"""
    ini = BASE / "alembic.ini"
    script = BASE / "migrations"
    if not ini.is_file() or not script.is_dir():
        print("[启动] 未找到 alembic.ini/migrations，跳过数据库迁移")
        return
    try:
        from alembic import command
        from alembic.config import Config

        config = Config(str(ini))
        config.set_main_option("script_location", str(script))
        command.upgrade(config, "head")
        print("[启动] 数据库结构已是最新")
    except Exception as exc:  # noqa: BLE001
        print(f"[启动] 数据库迁移失败（服务仍会启动）：{exc}")


def open_browser_later() -> None:
    time.sleep(2.5)
    try:
        webbrowser.open(f"http://{HOST}:{PORT}/")
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    print(f"[启动] 目录：{BASE}")
    run_migrations()

    # 迁移会用到 app 的配置，这里再导入，避免提前初始化数据库连接
    sys.path.insert(0, str(BASE))
    from app.main import app  # noqa: E402
    import uvicorn  # noqa: E402

    dist = BASE / "frontend" / "dist" / "index.html"
    if not dist.is_file():
        print("[启动] 警告：frontend/dist 不存在，页面会 404（只提供 API）")
    if not (BASE / ".env.local").is_file():
        print("[启动] 警告：缺少 .env.local，问答会降级为只给原文")

    if os.environ.get("KEJI_NO_BROWSER") != "1":  # 自测/服务器部署时可关掉自动开浏览器
        threading.Thread(target=open_browser_later, daemon=True).start()
    print(f"[启动] 打开 http://{HOST}:{PORT}/  关闭本窗口即停止服务")
    uvicorn.run(app, host=HOST, port=int(PORT), log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
