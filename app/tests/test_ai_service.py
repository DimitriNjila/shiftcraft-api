import pytest
from unittest.mock import MagicMock, patch

from app.tests.conftest import SCHEDULE_ID, RESTAURANT_ID, EMPLOYEE_ID, EMPLOYEE_ID_2

SAMPLE_SCHEDULE = {
    "id": SCHEDULE_ID,
    "restaurant_id": RESTAURANT_ID,
    "week_start": "2026-04-21",
}

SAMPLE_SHIFTS = [
    {
        "id": "aaa",
        "schedule_id": SCHEDULE_ID,
        "employee_id": EMPLOYEE_ID,
        "employee_name": "Alice",
        "role": "Server",
        "shift_date": "2026-04-22",
        "start_time": "09:00:00",
        "end_time": "17:00:00",
    },
    {
        "id": "bbb",
        "schedule_id": SCHEDULE_ID,
        "employee_id": EMPLOYEE_ID_2,
        "employee_name": "Bob",
        "role": "Cook",
        "shift_date": "2026-04-23",
        "start_time": "11:00:00",
        "end_time": "20:00:00",
    },
]

SAMPLE_EMPLOYEES = [
    {"id": EMPLOYEE_ID, "name": "Alice", "role": "Server", "is_active": True},
    {"id": EMPLOYEE_ID_2, "name": "Bob", "role": "Cook", "is_active": True},
]

VALID_ANALYSIS = {
    "summary": "A balanced week with good role coverage.",
    "fairness": {"score": "good", "details": "Hours are evenly distributed across roles."},
    "coverage": {"score": "fair", "details": "Thursday is lightly staffed."},
    "workload": {"score": "good", "details": "No employee is over- or under-worked."},
    "patterns": ["Alice works back-to-back closing shifts Tuesday–Wednesday."],
    "recommendations": ["Add one Server on Thursday evening."],
}


def _make_ai_service():
    """Build an AIService with a mocked Groq client."""
    from app.services.ai_service import AIService
    with patch("app.services.ai_service.settings") as mock_settings, \
         patch("app.services.ai_service.groq.Groq"):
        mock_settings.GROQ_API_KEY = "test-key"
        return AIService()


def _mock_groq_response(svc, content: str) -> None:
    """Wire the Groq client mock to return a specific content string."""
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    svc._client.chat.completions.create.return_value = mock_response


# === AIService init ===

def test_ai_service_raises_when_no_api_key():
    from app.services.ai_service import AIService, AIServiceUnavailableError
    with patch("app.services.ai_service.settings") as mock_settings:
        mock_settings.GROQ_API_KEY = None
        with pytest.raises(AIServiceUnavailableError, match="GROQ_API_KEY"):
            AIService()


def test_ai_service_creates_client_when_key_present():
    from app.services.ai_service import AIService
    with patch("app.services.ai_service.settings") as mock_settings, \
         patch("app.services.ai_service.groq.Groq") as mock_groq:
        mock_settings.GROQ_API_KEY = "test-key"
        AIService()
        mock_groq.assert_called_once_with(api_key="test-key")


# === analyze_schedule — happy path ===

def test_analyze_schedule_returns_structured_dict():
    import json
    svc = _make_ai_service()
    _mock_groq_response(svc, json.dumps(VALID_ANALYSIS))

    result = svc.analyze_schedule(SAMPLE_SCHEDULE, SAMPLE_SHIFTS)

    assert isinstance(result, dict)
    assert "summary" in result
    assert "fairness" in result
    assert "coverage" in result
    assert "workload" in result
    assert "patterns" in result
    assert "recommendations" in result


def test_analyze_schedule_scores_are_valid_values():
    import json
    svc = _make_ai_service()
    _mock_groq_response(svc, json.dumps(VALID_ANALYSIS))

    result = svc.analyze_schedule(SAMPLE_SCHEDULE, SAMPLE_SHIFTS)

    for dim in ("fairness", "coverage", "workload"):
        assert result[dim]["score"] in ("good", "fair", "poor")


def test_analyze_schedule_calls_correct_model():
    import json
    svc = _make_ai_service()
    _mock_groq_response(svc, json.dumps(VALID_ANALYSIS))

    svc.analyze_schedule(SAMPLE_SCHEDULE, SAMPLE_SHIFTS)

    call_kwargs = svc._client.chat.completions.create.call_args[1]
    assert call_kwargs["model"] == "llama-3.3-70b-versatile"


def test_analyze_schedule_requests_json_output():
    import json
    svc = _make_ai_service()
    _mock_groq_response(svc, json.dumps(VALID_ANALYSIS))

    svc.analyze_schedule(SAMPLE_SCHEDULE, SAMPLE_SHIFTS)

    call_kwargs = svc._client.chat.completions.create.call_args[1]
    assert call_kwargs["response_format"] == {"type": "json_object"}


def test_analyze_schedule_passes_system_prompt():
    import json
    svc = _make_ai_service()
    _mock_groq_response(svc, json.dumps(VALID_ANALYSIS))

    svc.analyze_schedule(SAMPLE_SCHEDULE, SAMPLE_SHIFTS)

    messages = svc._client.chat.completions.create.call_args[1]["messages"]
    system_msg = next((m for m in messages if m["role"] == "system"), None)
    assert system_msg is not None
    assert "json" in system_msg["content"].lower()


def test_analyze_schedule_patterns_and_recommendations_are_lists():
    import json
    svc = _make_ai_service()
    _mock_groq_response(svc, json.dumps(VALID_ANALYSIS))

    result = svc.analyze_schedule(SAMPLE_SCHEDULE, SAMPLE_SHIFTS)

    assert isinstance(result["patterns"], list)
    assert isinstance(result["recommendations"], list)


# === analyze_schedule — error handling ===

def test_analyze_schedule_raises_on_invalid_json():
    svc = _make_ai_service()
    _mock_groq_response(svc, "this is not json at all")

    with pytest.raises(ValueError, match="malformed JSON"):
        svc.analyze_schedule(SAMPLE_SCHEDULE, SAMPLE_SHIFTS)


def test_analyze_schedule_raises_on_missing_fields():
    import json
    svc = _make_ai_service()
    incomplete = {"summary": "ok", "fairness": {"score": "good", "details": "fine"}}
    _mock_groq_response(svc, json.dumps(incomplete))

    with pytest.raises(ValueError, match="missing required fields"):
        svc.analyze_schedule(SAMPLE_SCHEDULE, SAMPLE_SHIFTS)


def test_analyze_schedule_raises_on_invalid_score():
    import json
    svc = _make_ai_service()
    bad_score = {
        **VALID_ANALYSIS,
        "fairness": {"score": "excellent", "details": "great"},  # not in good|fair|poor
    }
    _mock_groq_response(svc, json.dumps(bad_score))

    with pytest.raises(ValueError, match="Invalid score value"):
        svc.analyze_schedule(SAMPLE_SCHEDULE, SAMPLE_SHIFTS)


def test_analyze_schedule_raises_on_malformed_dimension():
    import json
    svc = _make_ai_service()
    missing_details = {
        **VALID_ANALYSIS,
        "coverage": {"score": "good"},  # missing 'details'
    }
    _mock_groq_response(svc, json.dumps(missing_details))

    with pytest.raises(ValueError, match="malformed 'coverage'"):
        svc.analyze_schedule(SAMPLE_SCHEDULE, SAMPLE_SHIFTS)


# === _build_analysis_prompt ===

def test_build_analysis_prompt_includes_week_start():
    from app.services.ai_service import AIService
    prompt = AIService._build_analysis_prompt(SAMPLE_SCHEDULE, SAMPLE_SHIFTS, [])
    assert "2026-04-21" in prompt


def test_build_analysis_prompt_includes_employee_names():
    from app.services.ai_service import AIService
    prompt = AIService._build_analysis_prompt(SAMPLE_SCHEDULE, SAMPLE_SHIFTS, [])
    assert "Alice" in prompt
    assert "Bob" in prompt


def test_build_analysis_prompt_includes_shift_dates():
    from app.services.ai_service import AIService
    prompt = AIService._build_analysis_prompt(SAMPLE_SCHEDULE, SAMPLE_SHIFTS, [])
    assert "2026-04-22" in prompt
    assert "2026-04-23" in prompt


def test_build_analysis_prompt_flags_zero_shift_employees():
    """Employees on the roster but absent from shifts appear in the prompt."""
    from app.services.ai_service import AIService
    roster = [
        {"id": EMPLOYEE_ID, "name": "Alice", "role": "Server"},
        {"id": "new-emp-id", "name": "Charlie", "role": "Cook"},  # has no shifts
    ]
    # Only Alice has shifts
    alice_shift = [s for s in SAMPLE_SHIFTS if s["employee_id"] == EMPLOYEE_ID]
    prompt = AIService._build_analysis_prompt(SAMPLE_SCHEDULE, alice_shift, roster)
    assert "Charlie" in prompt
    assert "0 hours" in prompt


def test_build_analysis_prompt_no_zero_shift_section_when_all_assigned():
    """When every roster employee has at least one shift, no zero-shift section appears."""
    from app.services.ai_service import AIService
    prompt = AIService._build_analysis_prompt(SAMPLE_SCHEDULE, SAMPLE_SHIFTS, SAMPLE_EMPLOYEES)
    assert "NO shifts" not in prompt


def test_build_analysis_prompt_empty_shifts():
    from app.services.ai_service import AIService
    prompt = AIService._build_analysis_prompt(SAMPLE_SCHEDULE, [], [])
    assert "2026-04-21" in prompt
    assert "no shifts" in prompt.lower()


# === _validate_analysis_shape ===

def test_validate_analysis_shape_passes_valid_data():
    from app.services.ai_service import _validate_analysis_shape
    _validate_analysis_shape(VALID_ANALYSIS)  # should not raise


def test_validate_analysis_shape_fails_missing_key():
    from app.services.ai_service import _validate_analysis_shape
    bad = {k: v for k, v in VALID_ANALYSIS.items() if k != "recommendations"}
    with pytest.raises(ValueError, match="missing required fields"):
        _validate_analysis_shape(bad)


def test_validate_analysis_shape_fails_patterns_not_list():
    from app.services.ai_service import _validate_analysis_shape
    bad = {**VALID_ANALYSIS, "patterns": "should be a list"}
    with pytest.raises(ValueError, match="patterns"):
        _validate_analysis_shape(bad)


# === get_ai_service singleton ===

def test_get_ai_service_returns_same_instance():
    """get_ai_service() must return the same object on repeated calls."""
    import app.services.ai_service as ai_module
    with patch("app.services.ai_service.settings") as mock_settings, \
         patch("app.services.ai_service.groq.Groq"):
        mock_settings.GROQ_API_KEY = "test-key"
        # Reset singleton for clean test
        ai_module._ai_service = None
        svc1 = ai_module.get_ai_service()
        svc2 = ai_module.get_ai_service()
        assert svc1 is svc2
        # Clean up so other tests aren't affected
        ai_module._ai_service = None
