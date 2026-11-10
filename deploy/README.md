# 部署交付

系统工程师在此维护部署配置和实际操作说明。Windows 本机为演示交付路径，FastAPI 在 127.0.0.1:8000 同源托管前端构建产物（`frontend/dist` 存在时自动挂载）。实际环境版本清单写入 [docs/environment-versions.md](../docs/environment-versions.md)，执行与偏差记录见 [01_SYS环境与部署记录.md](01_SYS环境与部署记录.md)。在**另一台机器**从零部署（M4 冷启动验收/中途换机）按 [03_新机冷启动部署手册.md](03_新机冷启动部署手册.md) 执行，含验收记录签字模板。

## 部署脚本（已实机演练）

从仓库根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File deploy\start.ps1      # 检查 venv/.env.local/模型后前台启动（Ctrl+C 停止）
powershell -ExecutionPolicy Bypass -File deploy\start.ps1 -NewConsole
powershell -ExecutionPolicy Bypass -File deploy\stop.ps1       # 仅停止本服务的 uvicorn 进程（先确队列为空）
powershell -ExecutionPolicy Bypass -File deploy\backup.ps1     # 服务停止后打包 data/dist/代码与哈希清单，默认保留 7 份
powershell -ExecutionPolicy Bypass -File deploy\restore.ps1 backups\20261109_182247
```

约定：演示使用 1 worker、不 --reload、端口取 `.env.local` 的 `APP_PORT`；`.env.local`（含密钥）永不修改、不入备份包；`tools/`、`models/` 可按 [docs/environment-versions.md](../docs/environment-versions.md) 重建，均不入库。

[环境与部署交接](../docs/03_技术方案与接口/03_环境配置与运行部署.md) · [M1/M2 原始证据](evidence/)
