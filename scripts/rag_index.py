"""RAG 索引维护（SYS-02 运行侧）。

服务运行时索引线程会自动认领 pending 任务；本脚本用于：
- 查看每个视频的索引状态（status/model/dimension/chunk_count/last_error）
- 给已存在的 ready 视频补登记索引（旧数据处理后不会自动 re-enqueue）
- 强制重建单个视频的索引
- 在没有常驻服务时同步跑一次构建

用法：
    python scripts/rag_index.py status
    python scripts/rag_index.py enqueue --all-ready
    python scripts/rag_index.py enqueue --video <UUID>
    python scripts/rag_index.py rebuild --video <UUID>
    python scripts/rag_index.py build --watch 60
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
for path in (str(PROJECT_ROOT / "backend"), str(PROJECT_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from sqlalchemy import delete, func, select  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.clock import utc_now  # noqa: E402
from app.database import make_engine, session_factory_for  # noqa: E402
from app.models import Segment, Video  # noqa: E402


def _setup_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass


def _open():
    settings = get_settings()
    engine = make_engine(settings.database_path)
    return engine, session_factory_for(engine)


def _tables():
    from modules.retriever.tables import RagChunk, RagIndex

    return RagIndex, RagChunk


def cmd_status(args) -> int:
    engine, factory = _open()
    RagIndex, RagChunk = _tables()
    try:
        db = factory()
        rows = db.scalars(select(RagIndex).order_by(RagIndex.updated_at.desc())).all()
        if not rows:
            print("还没有任何索引记录。执行 enqueue --all-ready 或处理一个新视频。")
            return 0
        print(f"{'video_id':<38}{'批次':<6}{'状态':<10}{'块数':<6}{'模型':<22}维度   更新时间")
        for row in rows:
            count = int(db.scalar(select(func.count()).select_from(RagChunk).where(RagChunk.video_id == row.video_id)) or 0)
            print(
                f"{row.video_id:<38}{row.attempt:<6}{row.status:<10}{count:<6}{row.model:<22}{row.dimension:<6}{row.updated_at}"
            )
            if row.last_error:
                print(f"    错误：{row.last_error}")
        return 0
    finally:
        engine.dispose()


def cmd_enqueue(args) -> int:
    engine, factory = _open()
    try:
        from modules.retriever.service import IndexService

        service = IndexService(factory)
        db = factory()
        try:
            if args.all_ready:
                videos = db.scalars(select(Video).where(Video.status == "ready").order_by(Video.created_at)).all()
            elif args.video:
                video = db.get(Video, args.video)
                if video is None:
                    print(f"视频 {args.video} 不存在。")
                    return 1
                if video.status != "ready":
                    print(f"视频当前状态是 {video.status}，只有 ready 的视频能建索引。")
                    return 1
                videos = [video]
            else:
                print("请指定 --all-ready 或 --video <UUID>。")
                return 1
            if not videos:
                print("没有符合条件的视频。")
                return 0
            for video in videos:
                row_id = service.enqueue(db, video.id)
                print(f"已登记 {video.id}（{video.title}）索引任务 {row_id}")
            return 0
        finally:
            db.close()
    finally:
        engine.dispose()


def cmd_rebuild(args) -> int:
    engine, factory = _open()
    RagIndex, RagChunk = _tables()
    try:
        from modules.retriever.service import IndexService

        db = factory()
        try:
            video = db.get(Video, args.video)
            if video is None:
                print(f"视频 {args.video} 不存在。")
                return 1
            db.execute(delete(RagChunk).where(RagChunk.video_id == video.id))
            db.execute(delete(RagIndex).where(RagIndex.video_id == video.id))
            db.commit()
            row_id = IndexService(factory).enqueue(db, video.id)
            print(f"已清空并重新登记 {video.id} 的索引任务 {row_id}，等待索引线程处理。")
            return 0
        finally:
            db.close()
    finally:
        engine.dispose()


def cmd_build(args) -> int:
    """不依赖常驻服务：同步把 pending 跑完，可指定观察时长。"""
    engine, factory = _open()
    RagIndex, _ = _tables()
    try:
        from modules.retriever.service import IndexService

        service = IndexService(factory)
        deadline = time.monotonic() + args.watch
        built = 0
        while time.monotonic() < deadline:
            if service.build_once():
                built += 1
                continue
            pending = factory()
            try:
                left = int(
                    pending.scalar(select(func.count()).select_from(RagIndex).where(RagIndex.status.in_(("pending", "building"))))
                    or 0
                )
            finally:
                pending.close()
            if left == 0:
                break
            time.sleep(1.0)
        print(f"本轮完成 {built} 个索引构建。")
        return cmd_status(args)
    finally:
        engine.dispose()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RAG 索引维护")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="查看索引状态").set_defaults(func=cmd_status)

    enqueue = sub.add_parser("enqueue", help="登记索引任务")
    enqueue.add_argument("--video", help="单个视频 UUID")
    enqueue.add_argument("--all-ready", action="store_true", help="所有 ready 视频")
    enqueue.set_defaults(func=cmd_enqueue)

    rebuild = sub.add_parser("rebuild", help="清空并重建单个视频索引")
    rebuild.add_argument("--video", required=True)
    rebuild.set_defaults(func=cmd_rebuild)

    build = sub.add_parser("build", help="同步构建 pending 索引")
    build.add_argument("--watch", type=float, default=120.0, help="最多等待多少秒")
    build.set_defaults(func=cmd_build)
    return parser


def main(argv: list[str] | None = None) -> int:
    _setup_stdout()
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
