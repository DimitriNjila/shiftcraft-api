from app.core.template_utils import dedupe_shift_templates


def test_dedupe_no_duplicates_unchanged():
    templates = [
        {"day_of_week": 2, "start_time": "09:00:00", "end_time": "17:00:00", "role": "Server", "count": 1},
        {"day_of_week": 3, "start_time": "11:00:00", "end_time": "20:00:00", "role": "Cook", "count": 2},
    ]
    result = dedupe_shift_templates(templates)
    assert result == templates


def test_dedupe_collapses_exact_duplicates():
    templates = [
        {"day_of_week": 2, "start_time": "09:00:00", "end_time": "17:00:00", "role": "Server", "count": 1},
        {"day_of_week": 2, "start_time": "09:00:00", "end_time": "17:00:00", "role": "Server", "count": 1},
    ]
    result = dedupe_shift_templates(templates)
    assert len(result) == 1
    assert result[0]["count"] == 1


def test_dedupe_keeps_max_count_across_duplicates():
    templates = [
        {"day_of_week": 2, "start_time": "09:00:00", "end_time": "17:00:00", "role": "Server", "count": 1},
        {"day_of_week": 2, "start_time": "09:00:00", "end_time": "17:00:00", "role": "Server", "count": 3},
    ]
    result = dedupe_shift_templates(templates)
    assert len(result) == 1
    assert result[0]["count"] == 3


def test_dedupe_different_role_not_merged():
    templates = [
        {"day_of_week": 2, "start_time": "09:00:00", "end_time": "17:00:00", "role": "Server", "count": 1},
        {"day_of_week": 2, "start_time": "09:00:00", "end_time": "17:00:00", "role": "Cook", "count": 1},
    ]
    result = dedupe_shift_templates(templates)
    assert len(result) == 2


def test_dedupe_different_day_not_merged():
    templates = [
        {"day_of_week": 2, "start_time": "09:00:00", "end_time": "17:00:00", "role": "Server", "count": 1},
        {"day_of_week": 3, "start_time": "09:00:00", "end_time": "17:00:00", "role": "Server", "count": 1},
    ]
    result = dedupe_shift_templates(templates)
    assert len(result) == 2


def test_dedupe_preserves_first_seen_order():
    templates = [
        {"day_of_week": 3, "start_time": "09:00:00", "end_time": "17:00:00", "role": "Cook", "count": 1},
        {"day_of_week": 2, "start_time": "09:00:00", "end_time": "17:00:00", "role": "Server", "count": 1},
        {"day_of_week": 3, "start_time": "09:00:00", "end_time": "17:00:00", "role": "Cook", "count": 2},
    ]
    result = dedupe_shift_templates(templates)
    assert [t["role"] for t in result] == ["Cook", "Server"]
    assert result[0]["count"] == 2


def test_dedupe_empty_list():
    assert dedupe_shift_templates([]) == []
