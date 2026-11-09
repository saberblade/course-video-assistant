from types import SimpleNamespace

from app.chapters import build_chapters, replace_chapters


def piece(segment_id: str, start: float, end: float, text: str):
    return SimpleNamespace(id=segment_id, start_sec=start, end_sec=end, text=text)


def test_groups_original_sentences_by_minute():
    segments = [
        piece("a", 1, 5, "精确率等于真正例除以真正例与假正例之和。"),
        piece("b", 70, 80, "召回率等于真正例除以真正例与假反例之和。"),
    ]
    chapters = build_chapters(segments, 90)
    assert [(item.start_sec, item.end_sec, item.title) for item in chapters] == [
        (0, 60, "00:00 章节提要"),
        (60, 90, "01:00 章节提要"),
    ]
    assert chapters[0].text == "精确率等于真正例除以真正例与假正例之和。"
    assert chapters[0].segment_ids == ["a"]
    assert chapters[1].segment_ids == ["b"]


def test_skips_empty_minute_and_keeps_every_source_id():
    first = "第一句。"
    second = "第二句。"
    segments = [
        piece("late", 10, 12, second),
        piece("early", 2, 4, first),
        piece("far", 130, 140, "后面的句子。"),
    ]
    chapters = build_chapters(segments, 150)
    assert [item.start_sec for item in chapters] == [0, 120]
    assert chapters[0].text == first + second
    assert chapters[0].segment_ids == ["early", "late"]


def test_stops_before_a_sentence_that_would_pass_120_characters():
    first = "句" * 80
    second = "句" * 50
    chapters = build_chapters([piece("a", 0, 1, first), piece("b", 2, 3, second)], 30)
    assert chapters[0].text == first
    assert len(chapters[0].text) <= 120
    assert chapters[0].segment_ids == ["a", "b"]


def test_long_single_sentence_is_truncated_with_ellipsis():
    sentence = "句" * 130
    chapters = build_chapters([piece("a", 0, 1, sentence)], 30)
    assert len(chapters[0].text) == 120
    assert chapters[0].text.endswith("…")
    assert chapters[0].segment_ids == ["a"]


def test_blank_window_does_not_invent_a_chapter():
    assert build_chapters([piece("a", 0, 1, "   ")], 30) == []
    assert build_chapters([], 30) == []


def test_saved_chapters_are_returned_by_summary(client, make_video):
    video_id = make_video("ready")
    db = client.app.state.session_factory()
    from app.models import Segment

    segments = [
        Segment(id="11111111-1111-4111-8111-111111111111", video_id=video_id, start_sec=32.5, end_sec=39, text="精确率等于真正例除以真正例与假正例之和。"),
        Segment(id="22222222-2222-4222-8222-222222222222", video_id=video_id, start_sec=62, end_sec=70, text="召回率等于真正例除以真正例与假反例之和。"),
    ]
    db.add_all(segments)
    replace_chapters(db, video_id, segments, 180)
    db.commit()
    db.close()

    response = client.get(f"/api/videos/{video_id}/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "extractive"
    assert body["chapters"][0]["title"] == "00:00 章节提要"
    assert body["chapters"][0]["segment_ids"] == ["11111111-1111-4111-8111-111111111111"]
    assert body["chapters"][1]["title"] == "01:00 章节提要"
    assert body["chapters"][1]["start_sec"] == 60
    assert body["chapters"][1]["end_sec"] == 120
