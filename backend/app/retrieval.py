"""在当前视频的原文里搜索。只按词语匹配，不把匹配分数当成概率。"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass

import jieba
from rank_bm25 import BM25Okapi

from app.chapters import WINDOW_SEC, TranscriptPiece

logger = logging.getLogger("course_review")

DEFAULT_TOP_K = 5
DEFAULT_MAX_CHARS = 6000

# 只收录契约里点名的一对。别的同义词要等测试用课程原文核对后再加。
SYNONYMS = {"查全率": "召回率"}


@dataclass(frozen=True)
class HitSegment:
    id: str
    start_sec: float
    end_sec: float
    text: str


@dataclass(frozen=True)
class RetrievalHit:
    start_sec: float
    end_sec: float
    text: str
    segment_ids: list[str]
    segments: list[HitSegment]


def search_segments(
    segments: list[TranscriptPiece],
    question: str,
    duration_sec: float,
    top_k: int = DEFAULT_TOP_K,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[RetrievalHit]:
    blocks = [block for block in _blocks(segments, duration_sec) if block.tokens]
    query = _tokenize(question)
    if not blocks or not query:
        return []
    scored = _bm25_scores([block.tokens for block in blocks], query)
    ranked = [block for score, block in sorted(zip(scored, blocks), key=lambda item: (-item[0], item[1].start_sec)) if score > 0]
    return _fit(ranked[:top_k], max_chars)


def _blocks(segments: list[TranscriptPiece], duration_sec: float) -> list["_Block"]:
    if duration_sec <= 0:
        return []
    grouped: dict[int, list[TranscriptPiece]] = {}
    for segment in segments:
        text = segment.text.strip()
        if not text or segment.start_sec < 0 or segment.start_sec >= duration_sec:
            continue
        grouped.setdefault(int(segment.start_sec // WINDOW_SEC), []).append(segment)
    blocks: list[_Block] = []
    for index in sorted(grouped):
        pieces = sorted(grouped[index], key=lambda item: (item.start_sec, item.id))
        hit_segments = [HitSegment(item.id, item.start_sec, item.end_sec, item.text.strip()) for item in pieces]
        start = float(index * WINDOW_SEC)
        blocks.append(
            _Block(
                start_sec=start,
                end_sec=float(min(duration_sec, start + WINDOW_SEC)),
                segments=hit_segments,
                tokens=_tokenize("".join(item.text for item in hit_segments)),
            )
        )
    return blocks


def _bm25_scores(corpus: list[list[str]], query: list[str]):
    """使用 rank-bm25 排序。小语料里原公式会把命中词算成 0 或负数，这里改成恒为正的 IDF。"""
    model = BM25Okapi(corpus)
    document_frequency: dict[str, int] = {}
    for frequencies in model.doc_freqs:
        for word in frequencies:
            document_frequency[word] = document_frequency.get(word, 0) + 1
    model.idf = {
        word: math.log((model.corpus_size - freq + 0.5) / (freq + 0.5) + 1)
        for word, freq in document_frequency.items()
    }
    return model.get_scores(query)


def _tokenize(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    for source, target in SYNONYMS.items():
        normalized = normalized.replace(source, target)
    return [token for token in jieba.lcut(normalized) if token.strip()]


def _fit(blocks: list["_Block"], max_chars: int) -> list[RetrievalHit]:
    hits: list[RetrievalHit] = []
    used = 0
    trimmed = False
    for block in blocks:
        kept: list[HitSegment] = []
        for segment in block.segments:
            if used + len(segment.text) > max_chars:
                trimmed = True
                continue
            kept.append(segment)
            used += len(segment.text)
        if not kept:
            continue
        hits.append(
            RetrievalHit(
                start_sec=block.start_sec,
                end_sec=block.end_sec,
                text="".join(segment.text for segment in kept),
                segment_ids=[segment.id for segment in kept],
                segments=kept,
            )
        )
    if trimmed:
        logger.info("retrieval kept %s characters after dropping complete segments", used)
    return hits


@dataclass(frozen=True)
class _Block:
    start_sec: float
    end_sec: float
    segments: list[HitSegment]
    tokens: list[str]
