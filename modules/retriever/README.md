# modules/retriever — RAG 检索模块（卢乙源 / SYS）

对应任务：SYS-01（embedding 适配、版本化分块、BM25/向量检索、RRF）、SYS-02（索引生命周期与 fallback）、SYS-03（状态读取）。
规格来源：`docs/中期到答辩之前的规划/03_RAG增强与创新点.md` 与 `02_接口与数据契约.md`（基线 `f49acbd`）。

## 子模块

| 文件 | 职责 |
| --- | --- |
| `tables.py` | RAG 三表 ORM（挂 `app.database.Base`，`create_all` 幂等） |
| `chunking.py` | 版本化分块 `chunks_v1`：120–240 字、尽量不跨 30 秒、长句不伪造拆分 |
| `embedding.py` | 百炼 `text-embedding-v4`/1024 维适配；预算制；失败抛 `EmbeddingError` |
| `vectorstore.py` | float32 little-endian 存取、余弦排序、RRF（k=60） |
| `service.py` | 索引状态机 pending→building→ready/failed；后台线程；重启恢复 |
| `hybrid.py` | 混合检索 + `bm25_fallback`；返回类型与 `app.retrieval.RetrievalHit` 兼容 |

## 环境开关（配置样例与本机秘密分开）

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `RAG_INDEXING_ENABLED` | `0` | 执行器是否启动索引线程；`.env.local` 设 `1` 启用 |
| `RAG_RETRIEVAL_MODE` | `bm25` | 问答默认检索方式（`bm25`/`hybrid`）；评测证明有收益前保持 `bm25` |
| `RAG_EMBEDDING_MODEL` | `text-embedding-v4` | 向量模型 |
| `RAG_EMBEDDING_DIMENSION` | `1024` | 向量维度（v4 支持 64–2048） |
| `RAG_EMBEDDING_BATCH_SIZE` | `10` | 单次请求文本条数 |
| `RAG_EMBEDDING_BASE_URL` / `_API_KEY` | 回落 `LLM_BASE_URL`/`LLM_API_KEY` | 同一百炼账号；密钥只在服务端 |
| `RAG_EMBEDDING_CONNECT_TIMEOUT` | `5` | 连接超时秒 |
| `RAG_INDEX_BUDGET_SECONDS` | `300` | 后台构建 embedding 总墙钟 |
| `RAG_INDEX_IDLE_SECONDS` | `1` | 索引线程空闲轮询 |

## 给李沛丰（DB-01 迁移）的表字段

ORM 已在 `tables.py`，迁移可直接对照生成；要点：

- `rag_indexes`：唯一 `(video_id, attempt)`；`status ∈ pending/building/ready/failed`；记录 `model/dimension/index_version/chunking_version/chunk_count/last_error`。
- `rag_chunks`：`video_id` 外键 `ondelete=CASCADE`；`segment_ids_json` 保留真实 segment 顺序；`text_hash = sha256(chunking_version + \x1f + text)`；`ordinal` 是时间顺序。
- `chunk_embeddings`：唯一 `(chunk_id, model, dimension, text_hash)`；`vector_blob` float32 little-endian；`dtype='float32_le'`。
- 删除视频 → 外键级联清块与向量；重试（新 attempt）→ 构建时整体作废旧块/旧索引行。

## 给许梓轩（BE-04 集成）的接入点

```python
from modules.retriever.hybrid import retrieve_with_legacy_fallback

# qa/路由内，替换现有 search_segments 调用处：
outcome = retrieve_with_legacy_fallback(
    db, video.id, question, list(segments), video.duration_sec,
    top_k=settings.retrieval_top_k, max_chars=settings.max_context_characters,
)
# outcome.mode_used ∈ {bm25, hybrid, bm25_fallback, unavailable} —— 与生成模式分开记录
# outcome.hits 与 app.retrieval.search_segments 返回同类型，直接进既有引用回填逻辑
```

`GET /api/videos/{id}/retrieval-status` 数据源：

```python
from modules.retriever.service import IndexService
IndexService.get_status(db, video_id)   # 返回索引状态/模型/维度/块数/last_error/embedding_configured
```

路由归属与鉴权（登录+owner）由许统一加；模块层不做权限判断，但调用方必须先校验归属再调（契约：不得把未授权原文送去 embedding 或 LLM 后才过滤）。

## 失败码

| 码 | 含义 | 处置 |
| --- | --- | --- |
| `EMBED_NOT_CONFIGURED` | 向量配置缺失 | 索引 failed / 查询回 BM25 |
| `EMBED_TIMEOUT` | 超预算 | 同上 |
| `EMBED_AUTH_ERROR` | 401/403 | 同上，检查服务端密钥 |
| `EMBED_UPSTREAM_ERROR` | 限流/5xx/响应形状 | 单次重试后如实失败 |
| `EMBED_DIMENSION_MISMATCH` | 返回维度不符 | 该批失败，不让假向量入库 |
| `EMBED_EMPTY_VECTOR` / `EMBED_ZERO_NORM` | 空向量/零范数 | 受控失败或排序时跳过 |

## 测试

`backend/tests/test_rag_retriever.py`：分块规则、RRF 数学、索引构建/重建失效、
混合检索（假 embedder 语义簇）、降级路径、失败状态、级联清理、状态字典。
真实链路证据：`scripts/rag_probe.py`（真实 embedding API + 真实库，输出 `logs/rag_probe.json`）。
