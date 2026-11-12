"""课程复习 RAG 检索模块（SYS-01/SYS-02/SYS-03）。

子模块分工：
- tables.py     RAG 三表模型（rag_indexes / rag_chunks / chunk_embeddings）
- chunking.py   版本化分块（chunks_v1，120–240 字、尽量不跨 30 秒）
- embedding.py  百炼 text-embedding-v4 适配（1024 维，预算制，受控失败）
- vectorstore.py float32 向量存取 + 余弦排序 + RRF 融合
- service.py    索引生命周期（pending/building/ready/failed，重启恢复）
- hybrid.py     BM25/向量混合检索与 bm25_fallback 降级

用法见 modules/retriever/README.md。测试注入假 EmbeddingClient，不访问网络。
"""

INDEX_VERSION = "idx_v1"
