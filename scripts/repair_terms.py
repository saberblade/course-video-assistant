"""对已有转写执行术语纠正，并重建章节与索引（可重复运行）。

用途：ASR 把 SQLite/索引/单机/部署 等听错时，历史数据也要一起修，
否则检索仍然按错词匹配，问答会持续判"课程里没有依据"。

用法：
    python scripts/repair_terms.py --dry-run          # 只统计会改多少处
    python scripts/repair_terms.py --all              # 修正所有 ready 视频
    python scripts/repair_terms.py --video <UUID>
    python scripts/repair_terms.py --all --no-index   # 只改文本，不重建索引
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
for path in (str(PROJECT_ROOT / "backend"), str(PROJECT_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from sqlalchemy import delete, select  # noqa: E402

from app.chapters import replace_chapters  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.database import make_engine, session_factory_for  # noqa: E402
from app.glossary import apply_terms_with_count  # noqa: E402
from app.models import Segment, Video  # noqa: E402


def setup_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass


def repair_video(db, video: Video, dry_run: bool) -> tuple[int, int, int]:
    """返回（改动分片数、命中次数、章节数）。"""
    rows = db.scalars(select(Segment).where(Segment.video_id == video.id).order_by(Segment.start_sec)).all()
    changed = 0
    hits = 0
    for row in rows:
        fixed, count = apply_terms_with_count(row.text)
        if count:
            changed += 1
            hits += count
            if not dry_run:
                row.text = fixed
    chapters = 0
    if changed and not dry_run:
        db.flush()
        chapters = len(replace_chapters(db, video.id, rows, video.duration_sec))
    return changed, hits, chapters


def main() -> int:
    setup_stdout()
    parser = argparse.ArgumentParser(description="术语纠正与章节/索引重建")
    parser.add_argument("--all", action="store_true", help="处理所有 ready 视频")
    parser.add_argument("--video", help="只处理指定视频 UUID")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写库")
    parser.add_argument("--no-index", action="store_true", help="不重建 RAG 索引")
    args = parser.parse_args()

    if not args.all and not args.video:
        parser.print_help()
        return 1

    settings = get_settings()
    engine = make_engine(settings.database_path)
    factory = session_factory_for(engine)
    db = factory()
    try:
        if args.video:
            video = db.get(Video, args.video)
            videos = [video] if video else []
        else:
            videos = db.scalars(select(Video).where(Video.status == "ready").order_by(Video.created_at)).all()
        if not videos:
            print("没有可处理的视频。")
            return 0

        total_changed = 0
        for video in videos:
            changed, hits, chapters = repair_video(db, video, args.dry_run)
            total_changed += changed
            flag = "将修正" if args.dry_run else "已修正"
            print(f"{video.id}  {video.title:<20} {flag} {changed} 段 / {hits} 处" + ("" if args.dry_run else f"，重建章节 {chapters} 个"))

        if args.dry_run:
            db.rollback()
            print(f"\n[dry-run] 共 {total_changed} 段会被修改，未写入。")
            return 0

        db.commit()

        if not args.no_index and total_changed:
            from modules.retriever.service import IndexService
            from modules.retriever.tables import RagChunk, RagIndex

            service = IndexService(factory)
            for video in videos:
                db.execute(delete(RagChunk).where(RagChunk.video_id == video.id))
                db.execute(delete(RagIndex).where(RagIndex.video_id == video.id))
                db.commit()
                service.enqueue(db, video.id)
            print("索引已重新登记，等待索引线程处理（或用 scripts/rag_index.py build 同步跑完）。")
        return 0
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
