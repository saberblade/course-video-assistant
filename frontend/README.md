# 课迹前端

Vue 3、TypeScript、Vite、Element Plus 与 Axios 实现的课程视频复习界面。

本轮已提供接口的前端联调完成，可作为阶段交付；学习档案和历史问答部分仍待服务端接口，详见[前端联调与交接](../docs/最终交付/前端联调与交接.md)。

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
| `/login` | 注册 / 登录；成功后返回原本要访问的云台或视频 |
| `/screen` | 课程知识导航：固定画布，滚轮上下移动、左键/滚轮键及触摸拖动、按钮缩放与全览/复位；节点显示起止时间，点击展开原文 |
| `/screen?view=library` | 上传、课程列表和处理进度 |
| `/screen?view=analysis` | 复习进度：本视频标记概况、继续复习和疑问处理入口，不重复展示章节原文列表 |
| `/screen?view=weak` | 待复习清单：本地疑问备注、解决状态与回看 |
| `/videos/:id` | 视频播放、原文转写，以及「章节提要 / 向课程提问」选项卡 |

开发与生产默认连接真实后端。仅开发环境显式设置 `VITE_USE_MOCK=true` 时使用样例并跳过登录；生产构建始终要求真实登录。“我的课程”的上传和列表布局保留。

课程选择由 `src/composables/useCurrentCourse.ts` 共用：“课程知识导航”和“复习进度”查看同一门当前课程；“我的课程”始终展示全部课程；待复习清单汇总跨课程记录。经过课程库、清单或首页再返回时保留当前选择；打开另一门可复习的课程会更新选择。URL 中的 video 参数支持刷新与历史返回恢复；退出或切换账号清空内存中的选择。该状态仅是界面上下文，不是已保存的学习档案，也不代替服务器归属校验。

真实模式使用账号独立课程，不读取或自动上传旧匿名 localStorage 记录。服务端学习档案 API 还未合入，本次先关闭真实模式的新标记/备注保存，并在复习进度和清单提供简短不可用状态，不显示假的 0% 或保存成功。旧匿名记录原样留存；Mock 开发记录继续与真实数据分开。

学习档案接入以[最新接口契约](../docs/中期到答辩之前的规划/02_接口与数据契约.md)为准：播放位置、带版本的标记/备注、历史问答分页仍待 DB-02/03/04 接口合入并联调。本次没有伪造这些响应，也没有宣称已完成跨浏览器档案恢复。

左下角「课迹助教」支持拖动；匿名首页使用内置指引，登录后可调用后端站内助教。跨页面保留当前账号的会话，退出/切账号立即清空；登录页隐藏悬浮按钮以免遮挡表单。课程内容问答在对应视频详情里。

## 账号接入

`src/api/auth.ts` 调用 POST `/api/auth/register`、POST `/api/auth/login`、GET `/api/auth/me`、POST `/api/auth/logout`。注册成功返回登录表单，不冒充已登录。刷新通过 `/me` 恢复身份；401 跳转登录并记住当前业务页面；403 校验错误显示后端提示，不自动重试或绕过。

HttpOnly Cookie 由后端管理，Axios `withCredentials=true`。CSRF 从登录或 `/me` 响应取得，仅放内存，写操作自动带 `X-CSRF-Token`。密码、会话凭据和 CSRF 均不写浏览器存储。账号变化取消在途业务请求，迟到响应也按账号版本拒绝；业务组件、播放器、助教会话重新创建。不同标签页通过 BroadcastChannel 只广播状态变化，不传凭据。

未归属的旧视频不会自动给首个注册账号。新账号课程为空是正常行为，旧数据认领由后端维护工具按指定账号处理，前端不能认领或覆盖归属。

## 联调后端

后端运行在 `http://127.0.0.1:8000` 时，复制 `.env.example` 为 `.env.local`（已有配置时保留并检查），或在 `frontend/.env.local` 写入以下配置，再重启开发服务。

```dotenv
VITE_USE_MOCK=false
VITE_ASSISTANT_USE_API=true
```

`vite.config.ts` 将 `/api` 代理至后端，路径保留 `/api`。视频请求见 `src/api/videos.ts`，类型见 `src/types/index.ts`。协议依据为[团队 API 契约](../docs/03_技术方案与接口/02_API与数据模型契约.md)。真实上传、转写、章节、原文问答、引用、删除及页面刷新已用合成中文样本完成浏览器联调；服务端模型配置就绪后，也已补测生成式回答与引用一致性，见[本机联调记录](../docs/05_测试与验收/07_前后端联调记录_2026-11-10.md)。

悬浮助教开关 `VITE_ASSISTANT_USE_API=true` 在样例配置中开启。登录后调用 `POST /api/assistant/chat`，请求 `{ "messages": [{ "role": "user", "content": "怎么上传课程？" }] }`；前端按真实 `mode` 区分模型回答与基础指引，接口失败显示错误，不伪装生成成功。模型密钥由后端管理。

账号浏览器回归脚本为 `tests/account-auth.e2e.cjs`，使用独立临时数据库、随机测试口令和本机 Chrome。需在运行环境提供 Playwright 模块（可用 `PLAYWRIGHT_MODULE` 指定），准备 `.venv` 与 `data/tmp/sample_lecture.mp4` 合成样本，并先生产构建。在根目录执行 `node frontend/tests/account-auth.e2e.cjs`，结果写入忽略的 `logs/account-ui-*/`；不操作现有课程库。详见[账号联调记录](../docs/05_测试与验收/09_账号前端联调_2026-11-11.md)。

## 构建与部署

```powershell
npm.cmd run typecheck
npm.cmd run build
```

构建输出到 `frontend/dist/`，由系统工程师配置服务托管。构建默认使用真实课程接口。部署时将 `/api` 交给后端处理，前端页面路由回退到 `index.html`。

提交包含源码、公共图标、依赖锁文件和构建配置。依赖用 `npm ci` 安装，运行配置由各成员在本地设置。

顶栏校徽素材来源为[北京邮电大学视觉形象识别系统](https://vi.bupt.edu.cn/jcxt/xhgf.htm)。
