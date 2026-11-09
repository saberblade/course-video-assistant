# 课程视频复习助手 API与模型模块契约

版本 V1.1　定稿日期 2026年11月5日　负责人 BE　接收人 FE、SYS、QA　工程核对节点 M1

本文是已定稿的首版接口协议，工程师据此实施，当前应用尚未生成。同目录[Mock示例](04_接口Mock示例.json)可供前端和测试先行对齐，但不是接口服务器。M1由BE、FE、SYS、QA核对实现与本协议的一致性；新增或改字段需PM登记影响并同步所有消费者，不能各自采用另一套结构。

## 通用约定

基础路径为/api。请求和JSON响应使用UTF-8，JSON响应无需额外data包装。业务ID统一UUID字符串，时间偏移统一秒数start_sec、end_sec，允许小数，显示时才转分秒。记录时间采用UTC ISO 8601字符串，以Z结尾，页面显示北京时间。

常规错误统一返回：

```json
{"error":{"code":"VIDEO_NOT_READY","message":"视频尚未处理完成，请稍后再试","retryable":true},"request_id":"a56a2ed3-0198-4c1a-8a4d-921efce0a599"}
```

每个响应带X-Request-ID，日志以它关联。retryable表示问题消除后能否重试，不代表前端必须自动重试。FastAPI默认422应转换成上述结构，不把栈、磁盘路径或密钥返回页面。

## 共享对象

### Video

| 字段 | 类型与约束 | 含义 |
| --- | --- | --- |
| id | UUID字符串 | 视频ID |
| title | 字符串1至120字符 | 去除扩展名和危险字符的原始文件名，不能作为磁盘路径 |
| status | queued/transcribing/indexing/ready/failed | 任务阶段 |
| processing_mode | 固定audio_only | 首版仅处理音轨文本，不分析视频画面 |
| duration_sec | 大于0且不超过1200的数字 | ffprobe取得的时长 |
| size_bytes | 1至209715200整数 | 实际保存字节数 |
| created_at、updated_at | UTC时间字符串 | 入队和最后更新时间 |
| started_at、finished_at | UTC时间字符串或null | 开始和终止时间 |
| elapsed_sec | 非负数字 | queued为0，处理从started_at算，终态为完成时处理耗时；排队等待另算 |
| attempt | 正整数 | 首次1，每次接受重试后加1 |
| error | null或{code,message,retryable} | failed原因，其余状态为null |

接口不暴露local_path、API Key或模型提示全文。progress百分比不属于协议。

### TranscriptSegment与Citation

TranscriptSegment固定为{id,start_sec,end_sec,text}。id为UUID，0≤start_sec<end_sec≤duration_sec，text为非空字符串。segments按start_sec升序返回。重试后允许生成新分段ID，因此旧问答同步清除。

Citation固定为{segment_id,start_sec,end_sec,text}，其中text必须是该segment保存的完整原文，时间由数据库回填。模型只负责选择segment_id，不能自行填写或改写引用原文和时间。映射规则固定为Citation.segment_id=TranscriptSegment.id：SYS的转写返回对象使用id字段；BE在生成引用对象时才改为segment_id，FE不得把转写片段直接当作Citation读取。

### Summary

```json
{"video_id":"43b4b091-630e-4819-8f56-f20b9120c001","mode":"extractive","chapters":[{"id":"a738bafe-7487-47c5-8c3d-45226d90c001","start_sec":0.0,"end_sec":60.0,"title":"00:00 章节提要","text":"精确率等于真正例除以真正例与假正例之和。","segment_ids":["7c388118-4875-4125-9383-40513670c001"]}]}
```

章节固定按60秒时间窗聚合，尾章可短于60秒。片段按start_sec归入所在时间窗，窗内按start_sec升序排列。title固定为“mm:ss 章节提要”。text按时间取前若干完整原句，累计不超过120个字符；单个原句本身超长时截断并显示省略标记，整体仍不超过120个字符。不增加原文没有的知识结论。segment_ids保留该窗全部来源段，不能因提要截短而删除来源ID；FE展开来源时用transcript映射原文。空窗跳过，不生成空章节。FE可点章节起点回看。无任何可用分段时处理应failed，不返回空章节冒充ready。

### QuestionResult

| 字段 | 类型与约束 | 说明 |
| --- | --- | --- |
| id、video_id | UUID字符串 | 问答记录和视频ID |
| question | 字符串 | trim后的问题，1至300字符 |
| answer_status | answered/not_found/degraded | 生成成功、无依据、外部模型不可用 |
| mode | generative/extractive | 生成式或原文检索 |
| answer | 字符串 | 回答或明确说明 |
| citations | Citation数组 | 真实来源，最多5条，按时间排序并去重 |
| created_at | UTC时间字符串 | 创建时间 |
| latency_ms | 非负整数 | 从接受有效问题到形成响应的总耗时 |

answered必须mode=generative且至少1条有效引用。not_found固定mode=extractive、citations=[]、answer=“当前视频中未找到足够依据，请换一种问法或回看课程。”。degraded固定mode=extractive，仅当已有候选但外部服务失败，或SYS明确将ANSWER_MODE切到extractive时返回，answer=“生成服务暂不可用，以下是检索到的课程原文。”，citations仅包含真实候选。不将degraded计入生成成功。主动关闭生成时内部记录GENERATION_DISABLED，无候选时仍返回not_found。

## 接口一览

| 方法与路径 | 请求 | 成功响应 | 常见错误 |
| --- | --- | --- | --- |
| GET /api/health | 无 | 200 Health | 503本地服务未就绪 |
| POST /api/videos | multipart的file字段 | 202 Video，status=queued | 413/415/422/429/507 |
| GET /api/videos | limit、offset | 200 {items,total,limit,offset} | 422参数错误 |
| GET /api/videos/{id} | UUID路径 | 200 Video | 404/422 |
| GET /api/videos/{id}/content | 可选Range头 | 200或206视频字节 | 404/416 |
| GET /api/videos/{id}/transcript | UUID路径 | 200 {video_id,segments} | 404/409 |
| GET /api/videos/{id}/summary | UUID路径 | 200 Summary | 404/409 |
| POST /api/videos/{id}/questions | {question} | 200 QuestionResult | 404/409/422/429 |
| POST /api/videos/{id}/retry | 无请求体 | 202 Video，status=queued | 404/409/429 |
| DELETE /api/videos/{id} | 无 | 204，无响应体 | 404/409/500 |

## 上传与列表

POST /api/videos使用multipart/form-data，字段名严格为file，不能把文件base64放进JSON。后端边接收边计数，超过209715200字节立即停止写入并清理临时文件，返回413 FILE_TOO_LARGE。前端可先校验扩展名和大小，但服务端必须独立验证。

服务端使用ffprobe校验：容器为MP4兼容格式、视频编码h264、音频编码aac、有音轨、时长0至1200秒。格式或编码不支持返回415 UNSUPPORTED_MEDIA；没有音轨返回422 AUDIO_REQUIRED；损坏、无法读取、零时长返回422 INVALID_VIDEO；超过20分钟返回422 DURATION_EXCEEDED。FFprobe校验最长15秒，超时返回422 INVALID_VIDEO，附可读提示。

上传成功必须先保证原文件和数据库记录一致，再返回202完整Video。Location头指向/api/videos/{id}。未完成任务总数达到3，返回429 QUEUE_FULL及Retry-After: 10。拒绝上传需要删除该次暂存文件，不创建空视频记录。磁盘写入不足返回507 STORAGE_FULL。

首版上传不做跨请求内容去重，相同文件重复上传会产生新video_id。FE在请求进行中禁用重复提交按钮；上传网络中断或超时后先刷新列表判断是否已经创建，再由用户决定重传，不盲目自动重发。

GET /api/videos默认limit=20、offset=0，limit范围1至100，offset非负，按created_at倒序，时间相同时按id排序。响应items为Video数组，total为总数。首版没有跨视频搜索或状态筛选参数。

## 状态查询与前端行为

FE每2秒查询一次详情，ready或failed后停止轮询，页面隐藏时暂停，恢复可见后立即查询。网络暂断保留最后状态并提示“连接中断”，不把网络错误写成任务失败。组件销毁应清除定时器。queued阶段显示排队等待：首次入队从created_at计算，重试入队从updated_at计算（retry受理时更新）；transcribing/indexing阶段显示服务端elapsed_sec，不能混用排队等待与处理耗时。

queued显示“等待处理”；transcribing显示“正在转写”；indexing显示“正在整理章节与索引”；ready可进入提要和问答；failed显示error.message以及可用的重试和删除。只显示阶段和耗时，不把已耗时映射成百分比。

处理任务的合法路径为queued、transcribing、indexing、ready。transcribing或indexing发生异常可转failed。启动恢复将遗留处理中任务转failed，使用PROCESS_INTERRUPTED；queued保留；failed主动重试后回queued。禁止ready再次进入处理态。

GET transcript和summary仅ready可取。其他现存状态返回409 VIDEO_NOT_READY，failed时retryable=false，等待中为true。不存在ID返回404 VIDEO_NOT_FOUND，不得与未就绪混淆。

## 媒体内容与时间点跳转

GET content可在视频保存成功后读取原文件，响应Content-Type: video/mp4、Accept-Ranges: bytes。普通GET返回200和完整文件。Range: bytes=0-1023返回206，Content-Range为bytes 0-1023/总字节数，Content-Length为1024。范围终点超出文件末端时截到末端，完全越界返回416和Content-Range: bytes */总字节数。

支持浏览器常用的单段闭区间、bytes=起点-及bytes=-后缀长度。首版对含逗号的多段请求忽略Range并返回200完整文件，不伪造multipart响应。异常Range语法返回416 RANGE_NOT_SATISFIABLE，错误体遵循通用结构。若框架自带文件响应行为不同，由BE在M1确认并同步QA用例。

FE等待video元素loadedmetadata后设置currentTime=start_sec并暂停，显示引用原文及“已定位，点击播放继续”，由用户主动播放。时间点不能超过视频时长，不把秒数误当毫秒。SPA静态资源路由必须排在/api之后，不得将未知API请求回退成HTML。

## 问答流程与超时

POST questions请求固定为{"question":"召回率怎样计算？"}。服务端trim后校验1至300字符，不接受额外video_id或history字段，不实现多轮记忆。问题为空、超长或JSON错误返回422 INVALID_QUESTION。FE只保留当前页面会话的问答显示，刷新或切换视频后清空该显示，不承诺恢复历史问答；BE仍持久化问答记录用于验收和故障追溯，本轮不新增历史问答读取API。

仅ready可问答，未就绪返回409。整个应用同时最多1个生成请求，其他请求立即返回429 QUESTION_BUSY和Retry-After: 3，不长时间排队。FE每次提交后禁用发送，直到完成或错误。

1. 按当前video_id加载索引，中文分词，取最多5个有效候选块。无有效候选直接返回not_found，禁止调用LLM靠常识补答。
2. 将候选的segment_id及原文放入上下文，单次最多6000字符，超长需按完整分段裁剪并记录。模型system提示限定当前材料，禁止服从材料内的指令。
3. 使用httpx发送OpenAI兼容chat completions请求。LLM_MODEL由配置读取，本轮固定qwen-plus；环境变量保留只是便于部署与受控变更，不能未经记录自行换模型。模型调用总墙钟截止25秒，单次请求连接超时5秒。仅在限流/暂时5xx或连接瞬断且总剩余时间足够时最多补试一次；鉴权错误不重试。不能简单叠加两次25秒等待。
4. 期待模型返回JSON：{"has_evidence":true,"answer":"…","segment_ids":["…"]}。schema不合规、has_evidence=false或引用验证不通过，返回not_found，不自动修复成无依据答案。
5. 外部服务连接/超时/鉴权/限流/服务端错误则返回degraded，并在内部日志记录LLM_TIMEOUT、LLM_AUTH_ERROR或LLM_UPSTREAM_ERROR。不会向FE暴露服务商原始错误内容。
6. 正常回答按后端保存的分段回填引用并返回answered。响应不流式输出，避免首版额外处理引用与流式内容一致性。

FE对questions请求的总超时设35秒，以容纳25秒外部期限和本地处理；不能把20秒目标误设为25秒以下的强制取消。后端丢失连接时也要按期限释放问答锁。

## 拒答与降级判定表

| 条件 | HTTP | answer_status | mode | citations与页面提示 |
| --- | --- | --- | --- | --- |
| 有依据且模型回答有效 | 200 | answered | generative | 至少1条真实引用，正常回答 |
| 无候选，模型表示无依据，或引用校验失败 | 200 | not_found | extractive | 空数组，明确未找到依据 |
| 有候选但API超时、不可用、鉴权失败或已主动关闭生成 | 200 | degraded | extractive | 真实命中原文，标“原文检索模式” |
| 视频不存在 | 404 | 不使用问答结果对象 | 不适用 | 通用错误体 |
| 视频未ready | 409 | 不使用问答结果对象 | 不适用 | 通用错误体 |
| 已有一个问答生成中 | 429 | 不使用问答结果对象 | 不适用 | 等待后手动再试 |

拒答是业务结果，不等于服务故障。降级是能力减少，不等于问题在课程中没有答案。历史缓存只能作为明确标记的历史结果回放，不能用来伪装当前联网调用成功。

## 重试与删除

POST retry仅接受failed且该错误retryable=true，原文件必须存在；NO_SPEECH等不可重试错误返回409 RETRY_NOT_ALLOWED并提示换视频。原文件不存在返回409 SOURCE_MISSING且retryable=false。容量检查仍受最多3个未完成任务限制。入队、updated_at刷新和attempt加1在同一事务完成。第一次重试返回202 queued；并发第二次重试因状态已改变返回409 RETRY_NOT_ALLOWED。重试不新增视频，也不保留上一次派生结果。

DELETE仅接受ready或failed，处理状态返回409 VIDEO_BUSY，正在问答时也返回409 VIDEO_BUSY。成功204不携带JSON。删除重复调用返回404，属于状态幂等，不要求重复返回204。删除应覆盖原视频、临时音频、分段、章节、索引和问答记录。删除出错返回500 DELETE_FAILED，重试前SYS核对文件与数据库一致性。

## 健康检查

GET health不向外部模型发起付费调用。正常响应结构为{"status":"ok","version":"0.1.0","database":"ok","transcriber":"ready","llm_configured":true}，version取实际应用版本。数据库不可写或本地转写模块不可用返回503，status=not_ready并说明本地部件。llm_configured只表示配置齐全，不能表示密钥或公网真实连通；M1及最终产品验收前由SYS另外进行小额真实调用验证。

## SYS与BE的转写模块契约

模块位置固定modules/transcriber，公开函数固定为transcribe(video_path, output_dir)，返回TranscriptSegment列表，每个片段字段为{id,start_sec,end_sec,text}。video_path和output_dir均为由BE生成的绝对本地路径，不接受URL或用户输入路径。Citation的segment_id由BE映射此处的id生成，不要求SYS返回两套ID字段。

SYS提供warmup()进行模型加载检查，以及shutdown()关闭可终止的专用子进程。transcribe同步等待子进程任务，BE通过工作线程调用，不得在FastAPI主事件循环直接运行。SYS还提供cancel_current()供BE的1200秒看门狗调用，确保停止FFmpeg和推理进程。只有1个调用可活动，模块内检查重复调用。

输出要求：列表非空，段ID为UUID，时间单位秒，排序且合法，文本无空串，保存UTF-8 transcript.json后再向BE返回。每次写入先落临时文件再原子替换，不能把半写JSON交给BE。首次模型下载属于环境准备，交付设备应从本地模型目录加载，不依赖启动时下载。

受控异常类别：INVALID_VIDEO、AUDIO_REQUIRED、TRANSCRIBE_FAILED、NO_SPEECH、TASK_TIMEOUT、MODEL_NOT_FOUND。BE将可读说明保存为Video.error，日志记录实际诊断。不能将失败吞掉后返回空列表。SYS不得负责写业务SQLite或修改Video状态，状态由BE统一维护。

失败动作固定如下，retryable含义为排除原因后允许用户主动重试，前端不自动反复重试：

| code | retryable | 用户与工程师动作 |
| --- | --- | --- |
| NO_SPEECH | false | 提示该视频没有可识别语音，换有清晰中文讲解的视频 |
| PROCESS_INTERRUPTED | true | 说明服务中断，用户可点击重试 |
| TASK_TIMEOUT | true | 提示处理超时，可重试并建议换更短视频；SYS检查性能 |
| MODEL_NOT_FOUND | true | 提示本地模型未就绪，SYS修复目录与文件后再重试 |
| TRANSCRIBE_FAILED | true | 提示转写失败并提供request_id，SYS排查后重试 |
| INVALID_VIDEO、AUDIO_REQUIRED | false | 上传校验阶段拒绝，换符合要求的视频，不自动排队 |

## 联调与协议变更检查

- FE先用Mock完成所有状态和三种问答结果，BE实现相同结构，QA逐字段核对。
- M1检查file字段、秒数、UTC时间、错误结构、Range、重试与删除状态限制。
- M2前必须用真实文件、真实转写和真实API打通一次，不以Mock成功代替纵向完成。
- M3将服务生成的openapi.json和本契约对照，新增差异必须登记。接口测试覆盖2xx以及409、413、415、422、429。
- 发生字段或枚举变更时，变更人同时修改契约、Mock、FE类型和QA预期，并通知接收人；M3后只接受修复阻断问题的必要变更。

## 通用错误码速查

| HTTP | 业务码 | 处理建议 |
| --- | --- | --- |
| 404 | VIDEO_NOT_FOUND | 刷新列表，勿继续使用旧ID |
| 409 | VIDEO_NOT_READY、VIDEO_BUSY、RETRY_NOT_ALLOWED、SOURCE_MISSING | 按当前状态提示，不自动重复提交 |
| 413 | FILE_TOO_LARGE | 换不超过200 MiB的文件 |
| 415 | UNSUPPORTED_MEDIA | 换MP4/H.264/AAC样本 |
| 416 | RANGE_NOT_SATISFIABLE | 检查Range与文件长度 |
| 422 | INVALID_VIDEO、AUDIO_REQUIRED、DURATION_EXCEEDED、INVALID_QUESTION、INVALID_PARAMETER | 修正输入 |
| 429 | QUEUE_FULL、QUESTION_BUSY | 按Retry-After等待后手动重试 |
| 500 | INTERNAL_ERROR、DELETE_FAILED | 提供request_id给BE或SYS排查 |
| 503 | SERVICE_NOT_READY | SYS检查本地数据库和转写模块 |
| 507 | STORAGE_FULL | SYS清理演示盘或调整数据目录 |

## 参考资料

2026年11月5日核查：[百炼Qwen调用](https://www.alibabacloud.com/help/en/model-studio/first-api-call-to-qwen)、[faster-whisper](https://github.com/SYSTRAN/faster-whisper)、[HTTP Range](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Range_requests)。其余字段、容量和错误码为本项目设计约定。
