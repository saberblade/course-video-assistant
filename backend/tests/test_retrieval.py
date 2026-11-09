from types import SimpleNamespace

from app.retrieval import search_segments


def piece(segment_id: str, start: float, end: float, text: str):
    return SimpleNamespace(id=segment_id, start_sec=start, end_sec=end, text=text)


def test_finds_the_sentence_containing_the_term():
    segments = [
        piece("precision", 2, 8, "精确率等于真正例除以真正例与假正例之和。"),
        piece("recall", 70, 80, "召回率等于真正例除以真正例与假反例之和。"),
    ]
    hits = search_segments(segments, "召回率怎样计算？", 90)
    assert hits[0].segment_ids == ["recall"]
    assert "召回率" in hits[0].text
    assert "精确率" not in hits[0].text


def test_synonym_finds_the_documented_pair():
    segments = [piece("recall", 10, 20, "召回率等于真正例除以真正例与假反例之和。")]
    hits = search_segments(segments, "查全率怎样计算？", 60)
    assert hits[0].segment_ids == ["recall"]


def test_unrelated_question_returns_nothing():
    segments = [piece("recall", 10, 20, "召回率等于真正例除以真正例与假反例之和。")]
    assert search_segments(segments, "这段课程建议早餐吃什么？", 60) == []


def test_returns_at_most_five_blocks():
    segments = [piece(f"s{index}", index * 60, index * 60 + 5, f"知识点{index}需要复习。") for index in range(7)]
    hits = search_segments(segments, "知识点", 7 * 60)
    assert len(hits) == 5


def test_drops_a_whole_segment_instead_of_cutting_it():
    first = "召回率" + ("字" * 5000)
    second = "召回率" + ("字" * 2000)
    hits = search_segments(
        [piece("long", 1, 2, first), piece("next", 3, 4, second)],
        "召回率",
        60,
        max_chars=6000,
    )
    assert hits[0].segment_ids == ["long"]
    assert hits[0].text == first
    assert len(hits[0].text) <= 6000


def test_english_case_does_not_change_the_match():
    segments = [piece("http", 1, 5, "HTTP 请求通常包含方法、路径和请求头。")]
    hits = search_segments(segments, "http 请求包含什么？", 30)
    assert hits[0].segment_ids == ["http"]
