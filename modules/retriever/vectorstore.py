"""向量落库与余弦排序（SYS-01/SYS-02）。

存储口径（契约）：float32 little-endian；只读同模型同维度同文本哈希的有效向量。
排序用 NumPy 在内存里做，本轮课程量级（单视频百级块）完全够用，不引入向量服务。
"""

from __future__ import annotations

import logging

import numpy as np

from modules.retriever.embedding import EmbeddingError, normalize

logger = logging.getLogger("course_review.rag")


def pack_vector(vector: list[float] | np.ndarray) -> bytes:
    """float32 little-endian 打包。入库前统一走这里。"""
    array = np.asarray(vector, dtype="<f4")
    return array.tobytes()


def unpack_vector(blob: bytes, dimension: int) -> np.ndarray:
    array = np.frombuffer(blob, dtype="<f4")
    if array.size != dimension:
        raise EmbeddingError("EMBED_DIMENSION_MISMATCH")
    return array.copy()


def rank_chunks_by_cosine(
    query_vector: list[float] | np.ndarray,
    rows: list[tuple[str, bytes]],
) -> tuple[list[str], int]:
    """返回按余弦相似度降序的 chunk_id 列表与被跳过的零范数行数。

    rows: [(chunk_id, vector_blob), ...]。个别行维度不符/零范数时跳过该行并计数，
    不让单行坏数据废掉整次检索。
    """
    if not rows:
        return [], 0
    query = normalize(query_vector)
    scored: list[tuple[float, str]] = []
    skipped = 0
    for chunk_id, blob in rows:
        try:
            array = unpack_vector(blob, query.size)
            unit = normalize(array)
        except EmbeddingError:
            skipped += 1
            continue
        score = float(np.dot(query, unit))
        scored.append((score, chunk_id))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [chunk_id for _score, chunk_id in scored], skipped


def rrf_fuse(rank_lists: list[list[str]], k: int = 60) -> list[str]:
    """Reciprocal Rank Fusion：各路 1/(k+rank) 求和，rank 从 1 起。

    只融合排名，不混合 BM25 原始分与余弦分。并列时按首次出现顺序稳定输出。
    """
    scores: dict[str, float] = {}
    for ranked in rank_lists:
        for position, chunk_id in enumerate(ranked, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + position)
    first_seen: dict[str, int] = {}
    for ranked in rank_lists:
        for position, chunk_id in enumerate(ranked):
            first_seen.setdefault(chunk_id, position)
    return [
        chunk_id
        for chunk_id, _score in sorted(
            scores.items(), key=lambda item: (-item[1], first_seen.get(item[0], 0))
        )
    ]
