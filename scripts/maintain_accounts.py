"""账号与数据维护 CLI（DB-05）。

用途：课设演示环境的账号与归属维护。所有写操作先展示将改动的对象再要求确认，
密码只用交互输入（getpass），不接受命令行明文，也不写入日志或标准输出。

用法：
    python scripts/maintain_accounts.py check
    python scripts/maintain_accounts.py create-user --username demo_a --display-name 演示甲
    python scripts/maintain_accounts.py reset-password --username demo_a
    python scripts/maintain_accounts.py claim-video --video-id <UUID> --username demo_a
    python scripts/maintain_accounts.py list-users
    python scripts/maintain_accounts.py unowned

写操作默认停服或使用可控事务；本脚本不删除任何业务数据。
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
for path in (str(BACKEND_ROOT), str(PROJECT_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from sqlalchemy import delete, func, select  # noqa: E402

from app.auth import hash_password, normalize_username, validate_new_account  # noqa: E402
from app.clock import utc_now  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.database import make_engine, session_factory_for  # noqa: E402
from app.models import PlaybackProgress, Question, ReviewRecord, Session as LoginSession, User, Video  # noqa: E402


def _setup_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 老终端不支持就按默认编码
        pass


def _open_session():
    settings = get_settings()
    engine = make_engine(settings.database_path)
    return engine, session_factory_for(engine)


def _ask_password(from_stdin: bool = False) -> str:
    """交互输入密码。--password-stdin 供自动化演示使用，仍不经过命令行参数与日志。"""
    if from_stdin:
        first = sys.stdin.readline().rstrip("\r\n")
        second = sys.stdin.readline().rstrip("\r\n")
    else:
        first = getpass.getpass("请输入新密码（不显示）: ")
        second = getpass.getpass("请再输入一次确认: ")
    if not first:
        raise SystemExit("密码为空，未做任何修改。")
    if first != second:
        raise SystemExit("两次输入不一致，未做任何修改。")
    return first


def _confirm(prompt: str, assume_yes: bool) -> bool:
    if assume_yes:
        print(f"{prompt} -> 已按 --yes 直接执行")
        return True
    answer = input(f"{prompt} 输入 yes 继续，其他任意键取消: ").strip().lower()
    return answer == "yes"


def _find_user(db, username: str) -> User | None:
    return db.scalars(select(User).where(User.username_normalized == normalize_username(username))).first()


# ---------------- 子命令 ----------------


def cmd_list_users(args) -> int:
    engine, factory = _open_session()
    try:
        db = factory()
        rows = db.scalars(select(User).order_by(User.created_at)).all()
        if not rows:
            print("当前没有任何账号。")
            return 0
        print(f"{'用户名':<20}{'显示名':<16}{'状态':<8}{'视频数':<8}创建时间")
        for row in rows:
            count = int(db.scalar(select(func.count()).select_from(Video).where(Video.owner_id == row.id)) or 0)
            state = "启用" if row.is_active else "停用"
            print(f"{row.username_normalized:<20}{row.display_name:<16}{state:<8}{count:<8}{row.created_at}")
        return 0
    finally:
        engine.dispose()


def cmd_create_user(args) -> int:
    engine, factory = _open_session()
    try:
        db = factory()
        if _find_user(db, args.username) is not None:
            print(f"账号 {args.username} 已存在，未做任何修改。")
            return 1
        password = _ask_password(getattr(args, 'password_stdin', False))
        try:
            normalized, display = validate_new_account(args.username, password, args.display_name)
        except Exception as exc:  # AppError
            print(f"输入不合法：{getattr(exc, 'message', exc)}")
            return 1
        print(f"将创建账号：用户名={normalized}，显示名={display}，不会自动获得任何已有视频。")
        if not _confirm("确认创建？", args.yes):
            print("已取消。")
            return 1
        db.add(
            User(
                id=str(uuid4()),
                username_normalized=normalized,
                display_name=display,
                password_hash=hash_password(password),
                is_active=1,
                created_at=utc_now(),
            )
        )
        db.commit()
        print(f"已创建账号 {normalized}。")
        return 0
    finally:
        engine.dispose()


def cmd_reset_password(args) -> int:
    engine, factory = _open_session()
    try:
        db = factory()
        user = _find_user(db, args.username)
        if user is None:
            print(f"账号 {args.username} 不存在，未做任何修改。")
            return 1
        sessions = int(db.scalar(select(func.count()).select_from(LoginSession).where(LoginSession.user_id == user.id)) or 0)
        print(f"将重置账号 {user.username_normalized} 的密码，并撤销现有 {sessions} 个登录会话。")
        if not _confirm("确认重置？", args.yes):
            print("已取消。")
            return 1
        password = _ask_password(getattr(args, 'password_stdin', False))
        try:
            validate_new_account(user.username_normalized, password, user.display_name)
        except Exception as exc:  # AppError
            print(f"密码不合法：{getattr(exc, 'message', exc)}")
            return 1
        user.password_hash = hash_password(password)
        db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
        db.commit()
        print(f"已重置 {user.username_normalized} 的密码，旧会话全部失效。")
        return 0
    finally:
        engine.dispose()


def cmd_unowned(args) -> int:
    engine, factory = _open_session()
    try:
        db = factory()
        rows = db.scalars(select(Video).where(Video.owner_id.is_(None)).order_by(Video.created_at)).all()
        if not rows:
            print("没有未归属的视频。")
            return 0
        print(f"未归属视频共 {len(rows)} 个（普通账号看不到，需要明确认领）：")
        for row in rows:
            exists = Path(row.local_path).is_file()
            print(f"  {row.id}  {row.created_at}  {row.status:<10} 文件{'在' if exists else '缺失'}  {row.title}")
        return 0
    finally:
        engine.dispose()


def cmd_claim_video(args) -> int:
    engine, factory = _open_session()
    try:
        db = factory()
        user = _find_user(db, args.username)
        if user is None:
            print(f"账号 {args.username} 不存在，未做任何修改。")
            return 1
        video = db.get(Video, args.video_id)
        if video is None:
            print(f"视频 {args.video_id} 不存在，未做任何修改。")
            return 1
        if video.owner_id is not None:
            owner = db.get(User, video.owner_id)
            print(f"该视频已归属 {owner.username_normalized if owner else video.owner_id}，拒绝覆盖。")
            return 1
        if not Path(video.local_path).is_file():
            print(f"该视频的媒体文件不存在：{video.local_path}，拒绝认领。")
            return 1
        print(f"将把视频 {video.id}（{video.title}）认领给账号 {user.username_normalized}。")
        if not _confirm("确认认领？", args.yes):
            print("已取消。")
            return 1
        video.owner_id = user.id
        video.updated_at = utc_now()
        db.commit()
        print("已完成认领。")
        return 0
    finally:
        engine.dispose()


def cmd_check(args) -> int:
    """只读检查：不输出密码哈希或会话值。"""
    engine, factory = _open_session()
    try:
        db = factory()
        users = int(db.scalar(select(func.count()).select_from(User)) or 0)
        videos = int(db.scalar(select(func.count()).select_from(Video)) or 0)
        unowned = int(db.scalar(select(func.count()).select_from(Video).where(Video.owner_id.is_(None))) or 0)
        orphan_sessions = int(
            db.scalar(
                select(func.count()).select_from(LoginSession).where(
                    ~LoginSession.user_id.in_(select(User.id))
                )
            )
            or 0
        )
        question_total = int(db.scalar(select(func.count()).select_from(Question)) or 0)
        legacy_questions = int(
            db.scalar(select(func.count()).select_from(Question).where(Question.retrieval_mode.is_(None))) or 0
        )
        progress_total = int(db.scalar(select(func.count()).select_from(PlaybackProgress)) or 0)
        review_total = int(db.scalar(select(func.count()).select_from(ReviewRecord)) or 0)
        duplicate_reviews = db.execute(
            select(
                ReviewRecord.user_id,
                ReviewRecord.video_id,
                ReviewRecord.source_attempt,
                ReviewRecord.chapter_id_snapshot,
                func.count().label("n"),
            )
            .group_by(
                ReviewRecord.user_id,
                ReviewRecord.video_id,
                ReviewRecord.source_attempt,
                ReviewRecord.chapter_id_snapshot,
            )
            .having(func.count() > 1)
        ).all()

        print("== 账号与数据完整性（只读）==")
        print(f"账号数            {users}")
        print(f"视频数            {videos}（未归属 {unowned}）")
        print(f"登录会话          {int(db.scalar(select(func.count()).select_from(LoginSession)) or 0)}（孤儿 {orphan_sessions}）")
        print(f"问答记录          {question_total}（旧记录未标检索模式 {legacy_questions}）")
        print(f"播放进度记录      {progress_total}")
        print(f"复习标记记录      {review_total}")
        print(f"重复标记组合      {len(duplicate_reviews)}")

        missing: list[str] = []
        for row in db.scalars(select(Video)).all():
            if not Path(row.local_path).is_file():
                missing.append(f"{row.id} {row.title}")
        print(f"媒体文件缺失      {len(missing)}")
        for item in missing[:10]:
            print(f"  - {item}")

        try:
            from modules.retriever.tables import RagIndex

            statuses = db.execute(select(RagIndex.status, func.count()).group_by(RagIndex.status)).all()
            summary = ", ".join(f"{status}={count}" for status, count in statuses) or "无"
            print(f"RAG 索引状态      {summary}")
        except Exception:  # noqa: BLE001 RAG 表尚未建立
            print("RAG 索引状态      未建立（首次启动或索引关闭）")

        problems = unowned or orphan_sessions or duplicate_reviews or missing
        print("结论              " + ("发现待处理项，见上方明细" if problems else "未发现异常"))
        return 0
    finally:
        engine.dispose()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="课程视频复习助手：账号与数据维护")
    parser.add_argument("--yes", action="store_true", help="跳过交互确认（仅用于脚本化演示）")
    sub = parser.add_subparsers(dest="command", required=True)
    # --yes 放在子命令后面也能用；SUPPRESS 保证不会覆盖全局已取到的值。
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--yes", action="store_true", default=argparse.SUPPRESS, help="跳过交互确认")
    common.add_argument(
        "--password-stdin",
        action="store_true",
        default=argparse.SUPPRESS,
        help="从标准输入读两行密码（自动化演示用，避免交互阻塞）",
    )

    sub.add_parser("list-users", help="列出账号与各自视频数", parents=[common]).set_defaults(func=cmd_list_users)
    sub.add_parser("unowned", help="列出未归属视频", parents=[common]).set_defaults(func=cmd_unowned)
    sub.add_parser("check", help="只读完整性检查", parents=[common]).set_defaults(func=cmd_check)

    create = sub.add_parser("create-user", help="创建演示账号（密码交互输入）", parents=[common])
    create.add_argument("--username", required=True)
    create.add_argument("--display-name", required=True)
    create.set_defaults(func=cmd_create_user)

    reset = sub.add_parser("reset-password", help="重置密码并撤销旧会话", parents=[common])
    reset.add_argument("--username", required=True)
    reset.set_defaults(func=cmd_reset_password)

    claim = sub.add_parser("claim-video", help="把未归属视频认领给指定账号", parents=[common])
    claim.add_argument("--video-id", required=True)
    claim.add_argument("--username", required=True)
    claim.set_defaults(func=cmd_claim_video)
    return parser


def main(argv: list[str] | None = None) -> int:
    _setup_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
