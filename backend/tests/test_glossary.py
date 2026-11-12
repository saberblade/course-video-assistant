"""专业术语纠正在转写落库前后的行为。"""

from __future__ import annotations

import pytest

from app.glossary import apply_terms, apply_terms_with_count


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("这个项目为什么选择SaoCAT？", "这个项目为什么选择SQLite？"),
        ("锁印也不是越多越好", "索引也不是越多越好"),
        ("因为它是单经运行", "因为它是单机运行"),
        ("部属成本地", "部署成本低"),  # 只纠「部属」→「部署」，其余保持原样
        ("很适合课程演示这种单实力场景", "很适合课程演示这种单实例场景"),
        ("也就是video下滑线id", "也就是video_id"),
        ("今天的数据库涉及就讲到这里", "今天的数据库设计就讲到这里"),
    ],
)
def test_known_misrecognitions_are_fixed(raw: str, expected: str) -> None:
    assert apply_terms(raw) == expected


def test_longer_pattern_wins_over_shorter_one() -> None:
    # 「video 下滑线 id」与「video下滑线id」都应收敛到同一个写法
    assert apply_terms("关注 video 下滑线 id 字段") == "关注 video_id 字段"
    assert apply_terms("关注 video下滑线id 字段") == "关注 video_id 字段"


def test_normal_sentence_is_untouched() -> None:
    text = "同学们好，这节课我们讲数据库设计，先说主键和外键。"
    assert apply_terms(text) == text
    assert apply_terms_with_count(text) == (text, 0)


def test_apply_twice_is_idempotent() -> None:
    once = apply_terms("锁印本身占空间")
    assert apply_terms(once) == once


def test_hit_count_is_reported() -> None:
    fixed, hits = apply_terms_with_count("锁印占空间，锁印也要维护")
    assert fixed == "索引占空间，索引也要维护"
    assert hits == 2


def test_empty_text_is_safe() -> None:
    assert apply_terms("") == ""
    assert apply_terms_with_count("") == ("", 0)
