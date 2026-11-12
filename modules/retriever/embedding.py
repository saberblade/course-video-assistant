"""百炼语义向量适配（SYS-01）。

端点：OpenAI 兼容 /embeddings；模型默认 text-embedding-v4，维度 1024。
密钥复用服务端 LLM_API_KEY（同一百炼账号），也可用 RAG_EMBEDDING_API_KEY 覆盖。
失败必须受控：超时/限流/鉴权/维度不符/零范数都抛 EmbeddingError，绝不返回假向量。
预算制：调用方传入剩余墙钟秒数，超预算直接 EMBED_TIMEOUT，不吃掉生成时间。
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

import httpx
import numpy as np

logger = logging.getLogger("course_review.rag")

DEFAULT_MODEL = "text-embedding-v4"
DEFAULT_DIMENSION = 1024
DEFAULT_BATCH_SIZE = 10


class EmbeddingError(Exception):
    """受控向量错误。code 供日志/诊断，不含密钥与完整请求体。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class EmbeddingConfig:
    base_url: str
    api_key: str
    model: str
    dimension: int
    batch_size: int
    connect_timeout: float

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)


def load_embedding_config() -> EmbeddingConfig:
    """向量配置：独立变量优先，回落复用 LLM 三件套。"""
    return EmbeddingConfig(
        base_url=os.getenv("RAG_EMBEDDING_BASE_URL", os.getenv("LLM_BASE_URL", "")),
        api_key=os.getenv("RAG_EMBEDDING_API_KEY", os.getenv("LLM_API_KEY", "")),
        model=os.getenv("RAG_EMBEDDING_MODEL", DEFAULT_MODEL),
        dimension=int(os.getenv("RAG_EMBEDDING_DIMENSION", str(DEFAULT_DIMENSION))),
        batch_size=max(1, int(os.getenv("RAG_EMBEDDING_BATCH_SIZE", str(DEFAULT_BATCH_SIZE)))),
        connect_timeout=float(os.getenv("RAG_EMBEDDING_CONNECT_TIMEOUT", "5")),
    )


class EmbeddingClient:
    """可注入的向量客户端接口（测试用假实现替换）。"""

    def embed(self, texts: list[str], budget_seconds: float) -> list[list[float]]:
        raise NotImplementedError


class BailianEmbeddingClient(EmbeddingClient):
    """真实调用百炼兼容端点。分批、单次重试、维度与范数校验。"""

    def __init__(self, config: EmbeddingConfig) -> None:
        self._config = config

    def embed(self, texts: list[str], budget_seconds: float) -> list[list[float]]:
        if not self._config.configured:
            raise EmbeddingError("EMBED_NOT_CONFIGURED")
        if not texts:
            return []
        deadline = time.monotonic() + max(0.0, budget_seconds)
        out: list[list[float] | None] = [None] * len(texts)
        for start in range(0, len(texts), self._config.batch_size):
            batch = texts[start : start + self._config.batch_size]
            vectors = self._embed_batch(batch, deadline)
            for offset, vector in enumerate(vectors):
                out[start + offset] = vector
        return [vector for vector in out if vector is not None]

    def _embed_batch(self, texts: list[str], deadline: float) -> list[list[float]]:
        retried = False
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise EmbeddingError("EMBED_TIMEOUT")
            timeout = httpx.Timeout(
                connect=self._config.connect_timeout, read=remaining, write=remaining, pool=5
            )
            try:
                with httpx.Client() as client:
                    response = client.post(
                        _embeddings_url(self._config.base_url),
                        headers={"Authorization": f"Bearer {self._config.api_key}"},
                        json={
                            "model": self._config.model,
                            "input": texts,
                            "dimensions": self._config.dimension,
                            "encoding_format": "float",
                        },
                        timeout=timeout,
                    )
            except httpx.TimeoutException as exc:
                raise EmbeddingError("EMBED_TIMEOUT") from exc
            except httpx.TransportError as exc:
                if not retried and deadline - time.monotonic() > 1:
                    retried = True
                    continue
                raise EmbeddingError("EMBED_UPSTREAM_ERROR") from exc
            if response.status_code in (401, 403):
                raise EmbeddingError("EMBED_AUTH_ERROR")
            if response.status_code == 429 or response.status_code >= 500:
                if not retried and deadline - time.monotonic() > 1:
                    retried = True
                    continue
                raise EmbeddingError("EMBED_UPSTREAM_ERROR")
            if response.status_code != 200:
                raise EmbeddingError("EMBED_UPSTREAM_ERROR")
            payload = response.json()
            data = payload.get("data")
            if not isinstance(data, list) or len(data) != len(texts):
                raise EmbeddingError("EMBED_UPSTREAM_ERROR")
            ordered = sorted(data, key=lambda item: item.get("index", 0))
            return [_validate_vector(item.get("embedding"), self._config.dimension) for item in ordered]


def _embeddings_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/embeddings"):
        return base
    return base + "/embeddings"


def _validate_vector(raw: object, dimension: int) -> list[float]:
    if not isinstance(raw, list) or len(raw) != dimension:
        raise EmbeddingError("EMBED_DIMENSION_MISMATCH")
    array = np.asarray(raw, dtype=np.float32)
    if not np.all(np.isfinite(array)):
        raise EmbeddingError("EMBED_EMPTY_VECTOR")
    norm = float(np.linalg.norm(array.astype(np.float64)))
    if norm <= 1e-6:
        raise EmbeddingError("EMBED_ZERO_NORM")
    return array.tolist()


def normalize(vector: list[float] | np.ndarray) -> np.ndarray:
    """查询/入库共用的单位化；零范数在入库侧已被拦截，这里兜底断言。"""
    array = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(array.astype(np.float64)))
    if norm <= 1e-6:
        raise EmbeddingError("EMBED_ZERO_NORM")
    return (array / norm).astype(np.float32)
