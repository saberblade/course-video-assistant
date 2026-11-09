"""按每 60 秒从转写原句摘出章节提要。不调用大模型，也不编造原文没有的话。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import Chapter

WINDOW_SEC = 60
MAX_CHARS = 120
ELLIPSIS = "…"


class TranscriptPiece(Protocol):
    id: str
    start_sec: float
    end_sec: float
    text: str


@dataclass(frozen=True)
class ChapterDraft:
    start_sec: float
    end_sec: float
    title: str
    text: str
    segment_ids: list[str]


def build_chapters(segments: list[TranscriptPiece], duration_sec: float) -> list[ChapterDraft]:
    if duration_sec <= 0:
        return []
    grouped: dict[int, list[TranscriptPiece]] = {}
    for segment in segments:
        text = segment.text.strip()
        if not text or segment.start_sec < 0 or segment.start_sec >= duration_sec:
            continue
        grouped.setdefault(int(segment.start_sec // WINDOW_SEC), []).append(segment)

    chapters: list[ChapterDraft] = []
    for index in sorted(grouped):
        window_start = index * WINDOW_SEC
        window_end = min(duration_sec, window_start + WINDOW_SEC)
        pieces = sorted(grouped[index], key=lambda item: (item.start_sec, item.id))
        sentences = [item.text.strip() for item in pieces]
        text = _summary_text(sentences)
        if not text:
            continue
        chapters.append(
            ChapterDraft(
                start_sec=float(window_start),
                end_sec=float(window_end),
                title=_title(window_start),
                text=text,
                segment_ids=[item.id for item in pieces],
            )
        )
    return chapters


def replace_chapters(db: Session, video_id: str, segments: list[TranscriptPiece], duration_sec: float) -> list[Chapter]:
    """用当前转写重写这一条视频的章节。调用方负责提交事务。"""
    db.execute(delete(Chapter).where(Chapter.video_id == video_id))
    rows: list[Chapter] = []
    for draft in build_chapters(segments, duration_sec):
        row = Chapter(
            id=str(uuid4()),
            video_id=video_id,
            start_sec=draft.start_sec,
            end_sec=draft.end_sec,
            title=draft.title,
            text=draft.text,
            segment_ids_json=json.dumps(draft.segment_ids, ensure_ascii=False),
        )
        db.add(row)
        rows.append(row)
    return rows


def _title(start_sec: float) -> str:
    total_seconds = int(start_sec)
    return f"{total_seconds // 60:02d}:{total_seconds % 60:02d} 章节提要"


def _summary_text(sentences: list[str]) -> str:
    chosen = ""
    for sentence in sentences:
        if not chosen and len(sentence) > MAX_CHARS:
            return sentence[: MAX_CHARS - 1] + ELLIPSIS
        if len(chosen) + len(sentence) > MAX_CHARS:
            break
        chosen += sentence
    return chosen
