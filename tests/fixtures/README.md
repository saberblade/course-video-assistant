[Uploading README.md…]()
# 验收样例与正式样本登记

本目录只保存脱敏、可公开提交的固定题集和空白登记模板。

- `acceptance_questions.json`：从 `docs/05_测试与验收/02_样本脚本与问题集.md` 固化的 20 道有答案题与 5 道无答案题。
- `authorized_samples.example.json`：A/B/C 正式授权视频的登记模板。
- `authorized_samples.2026-11-12.json`：本轮用户自录 A/B/C 的脱敏哈希、时长和获取方式。
- `authorized_samples.local.json`：本机实际登记文件，包含绝对路径和授权信息，已由 `.gitignore` 排除。

授权视频原文件不得提交到 Git。仓库只记录样本 ID、SHA-256、授权范围、确认人、确认时间和真值时间区间。模拟脚本、SYS 合成视频或历史联调样本不能冒充正式 A/B/C。
