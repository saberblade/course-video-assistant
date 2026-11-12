"""专业术语纠正（ASR 同音/近音误识别）。

转写模型对课程里的英文缩写和术语容易听错，例如把 SQLite 听成 "SaoCAT"、
把"索引"写成"锁印"。这些错词会同时污染检索（BM25 词面对不上）和回答
（模型据此判断"课程里没有依据"），因此必须在写入转写时统一纠正。

原则：
- 只做**明确的错形 → 正形**替换，不做模糊改写，避免把正常语句改坏；
- 长词优先匹配，避免短词先吃掉长词的一部分；
- 每次命中都计数，便于在日志/证据里如实说明纠正了多少处。
"""

from __future__ import annotations

# 左：模型常见错形；右：课程里正确的写法。
# 只收本项目语料里实际出现过的错形，新增前请先确认不是正常用词。
TERM_FIXES: dict[str, str] = {
    # 英文缩写被音译
    "SaoCAT": "SQLite",
    "saocat": "SQLite",
    "SaoCat": "SQLite",
    "SQLite3": "SQLite",
    "circle CI": "SQLite",
    "my circle": "MySQL",
    "my SQL": "MySQL",
    "POST gres": "PostgreSQL",
    "reids": "Redis",
    "red is": "Redis",
    # 中文术语同音
    "锁印": "索引",
    "所引": "索引",
    "单经运行": "单机运行",
    "单机运行行": "单机运行",
    "部属成本": "部署成本",
    "部属": "部署",
    # 整句错形优先于单词替换（_ORDERED 按长度倒序）
    "部属成本地": "部署成本低",
    "部署成本地": "部署成本低",
    "单实力": "单实例",
    "单实例场景": "单实例场景",
    "数据库涉及": "数据库设计",
    "接口涉及": "接口设计",
    "全表扫苗": "全表扫描",
    "幂等等": "幂等",
    "密等性": "幂等性",
    "召回绿": "召回率",
    "精确绿": "精确率",
    "准确绿": "准确率",
    "反回率": "召回率",
    "视频边号": "视频编号",
    "时间戳记": "时间戳",
    # 英文术语大小写与空格
    "video 下滑线 id": "video_id",
    "video下滑线id": "video_id",
    "video 下划线 id": "video_id",
    "video下滑线 id": "video_id",
    "content range": "Content-Range",
    "content-range": "Content-Range",
    "b m 25": "BM25",
    "B M 25": "BM25",
    "bm 25": "BM25",
}

_ORDERED = sorted(TERM_FIXES.items(), key=lambda item: len(item[0]), reverse=True)


def apply_terms(text: str) -> str:
    """把已知错形替换成正形。无命中时原样返回。"""
    if not text:
        return text
    fixed = text
    for wrong, right in _ORDERED:
        if wrong in fixed:
            fixed = fixed.replace(wrong, right)
    return fixed


def apply_terms_with_count(text: str) -> tuple[str, int]:
    """返回纠正后的文本与命中次数，供日志统计。"""
    if not text:
        return text, 0
    fixed = text
    hits = 0
    for wrong, right in _ORDERED:
        count = fixed.count(wrong)
        if count:
            fixed = fixed.replace(wrong, right)
            hits += count
    return fixed, hits
