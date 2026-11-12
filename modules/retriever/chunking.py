"""版本化分块（SYS-01）。

规则（契约 03_RAG增强与创新点.md）：
- 合并相邻完整转写句；目标 120–240 字；尽量不跨 30 秒。
- 长片段不伪造拆分时间：超过 240 字的单句整句成块。
- 保留 segment_ids 与真实时间区间；chunking_version 固定，文本哈希可复算。

分块是纯函数：同样输入永远得到同样输出，测试与重建索引都依赖这一点。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import uuid4

from app.chapters import TranscriptPiece

CHUNKING_VERSION = "chunks_v1"
TARGET_MIN_CHARS = 120
MAX_CHARS = 240
MAX_SPAN_SEC = 30.0
_HASH_SEP = "\x1f"


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    segment_ids: list[str]
    start_sec: float
    end_sec: float
    text: str
    text_hash: str

    @property
    def char_count(self) -> int:
        return len(self.text)


def build_chunks(segments: list[TranscriptPiece]) -> list[Chunk]:
    """按规则把转写句合并成块。输入按时间排序后的完整句列表。"""
    valid = [
        piece
        for piece in segments
        if piece.text.strip() and piece.end_sec > piece.start_sec >= 0
    ]
    valid.sort(key=lambda item: (item.start_sec, item.id))

    chunks: list[Chunk] = []
    pieces: list[TranscriptPiece] = []
    chars = 0

    def flush() -> None:
        nonlocal pieces, chars
        if not pieces:
            return
        text = "".join(piece.text.strip() for piece in pieces)
        chunks.append(
            Chunk(
                ordinal=len(chunks),
                segment_ids=[piece.id for piece in pieces],
                start_sec=float(pieces[0].start_sec),
                end_sec=float(max(piece.end_sec for piece in pieces)),
                text=text,
                text_hash=text_hash_of(text),
            )
        )
        pieces = []
        chars = 0

    for piece in valid:
        piece_chars = len(piece.text.strip())
        if not pieces:
            pieces = [piece]
            chars = piece_chars
            continue
        span = piece.end_sec - pieces[0].start_sec
        merged_chars = chars + piece_chars
        # 已达目标长度后：再装会超 240 字或跨 30 秒 → 先收块
        if chars >= TARGET_MIN_CHARS and (merged_chars > MAX_CHARS or span > MAX_SPAN_SEC):
            flush()
            pieces = [piece]
            chars = piece_chars
            continue
        # 未达目标长度但下一句会突破 240 字硬上限 → 也先收块
        if merged_chars > MAX_CHARS:
            flush()
            pieces = [piece]
            chars = piece_chars
            continue
        pieces.append(piece)
        chars = merged_chars
    flush()
    return chunks


def text_hash_of(text: str) -> str:
    """块文本哈希：掺入 chunking_version，换分块规则即整体失效。"""
    raw = CHUNKING_VERSION + _HASH_SEP + text
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def segment_ids_json(chunk: Chunk) -> str:
    return json.dumps(chunk.segment_ids, ensure_ascii=False)
