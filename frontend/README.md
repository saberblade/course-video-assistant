# 课迹前端

Vue 3、TypeScript、Vite、Element Plus 与 Axios 实现的课程视频复习界面。

## 启动

Node.js 22.12 或以上。在仓库根目录打开终端后执行以下命令。

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

打开终端显示的地址，默认是 `http://localhost:5173/`。Windows PowerShell 可使用上面的 `npm.cmd`，其他终端使用 `npm` 即可。5173 已被占用时可运行 `npm.cmd run dev -- --port 5174`。

## 页面和数据

| 路径 | 用途 |
| --- | --- |
| `/` | 产品介绍，点击「进入知识云台」开始使用 |
| `/screen` | 课程知识导航：固定画布，滚轮上下移动、左键/滚轮键及触摸拖动、按钮缩放与全览/复位；节点显示起止时间，点击展开原文 |
| `/screen?view=library` | 上传、课程列表和处理进度 |
| `/screen?view=analysis` | 复习进度：本视频标记概况、继续复习和疑问处理入口，不重复展示章节原文列表 |
| `/screen?view=weak` | 待复习清单：本地疑问备注、解决状态与回看 |
| `/videos/:id` | 视频播放、原文转写，以及「章节提要 / 向课程提问」选项卡 |

开发环境默认使用前端 Mock，可演示上传、删除、处理状态和三种问答结果。刷新后 Mock 记录恢复初始状态。设置 `VITE_USE_MOCK=false` 后，课程知识导航使用现有视频与章节接口，“我的课程”的原有功能保留。

复习记录由 `src/composables/useReviewRecords.ts` 管理，仅存于当前来源的 localStorage；真实模式与 Mock 分开保存。8000 与 5173 是不同来源，记录各自独立，不跨设备同步。存储失败时明确提示仅当前页面有效。

已复习标记和疑问的解决状态分别保存，移出清单不会清除已复习标记。进度只统计当前视频、当前处理版本的实际章节；不推断掌握程度、学习时长和播放进度。重新处理后的旧标记不计入新章节进度，旧备注保留，回看前验证来源状态。后续后端持久化可集中替换 `useReviewRecords.ts`，当前没有新增服务端接口。详见[调整记录](../docs/07_管理记录/06_前端复习逻辑调整_2026-11-10.md)。

左下角「课迹助教」支持拖动，提供内置的项目介绍与站内使用问答，切换页面时保留本次对话。课程内容问答在对应视频详情里。

## 联调后端

后端运行在 `http://127.0.0.1:8000` 时，复制 `.env.example` 为 `.env.local`（已有配置时保留并检查），或在 `frontend/.env.local` 写入以下配置，再重启开发服务。

```dotenv
VITE_USE_MOCK=false
```

`vite.config.ts` 将 `/api` 代理至后端，路径保留 `/api`。视频请求见 `src/api/videos.ts`，类型见 `src/types/index.ts`。协议依据为[团队 API 契约](../docs/03_技术方案与接口/02_API与数据模型契约.md)。真实上传、转写、章节、原文问答、引用、删除及页面刷新已用合成中文样本完成浏览器联调；服务端模型配置就绪后，也已补测生成式回答与引用一致性，见[本机联调记录](../docs/05_测试与验收/07_前后端联调记录_2026-11-10.md)。

悬浮助教另有独立开关 `VITE_ASSISTANT_USE_API=true`，开启后调用 `POST /api/assistant/chat`，请求 `{ "messages": [{ "role": "user", "content": "怎么上传课程？" }] }`，成功响应 `{ "answer": "…", "mode": "generative" }`；未配置模型或模型故障时后端返回 `mode: "guide"` 的降级答复，前端只需要读 `answer`。适配见 `src/api/assistant.ts`。模型密钥由后端管理。

## 构建与部署

```powershell
npm.cmd run typecheck
npm.cmd run build
```

构建输出到 `frontend/dist/`，由系统工程师配置服务托管。构建默认使用真实课程接口。部署时将 `/api` 交给后端处理，前端页面路由回退到 `index.html`。

提交包含源码、公共图标、依赖锁文件和构建配置。依赖用 `npm ci` 安装，运行配置由各成员在本地设置。

顶栏校徽素材来源为[北京邮电大学视觉形象识别系统](https://vi.bupt.edu.cn/jcxt/xhgf.htm)。
