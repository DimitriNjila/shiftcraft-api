import pytest
from unittest.mock import MagicMock, patch

from app.tests.conftest import SCHEDULE_ID, RESTAURANT_ID

SAMPLE_SCHEDULE = {
    "id": SCHEDULE_ID,
    "restaurant_id": RESTAURANT_ID,
    "week_start": "2026-04-21",
}

SAMPLE_SHIFTS = [
    {
        "id": "aaa",
        "schedule_id": SCHEDULE_ID,
        "employee_id": "emp-1",
        "employee_name": "Alice",
        "role": "Server",
        "shift_date": "2026-04-22",
        "start_time": "09:00:00",
        "end_time": "17:00:00",
    },
    {
        "id": "bbb",
        "schedule_id": SCHEDULE_ID,
        "employee_id": "emp-2",
        "employee_name": "Bob",
        "role": "Cook",
        "shift_date": "2026-04-23",
        "start_time": "11:00:00",
        "end_time": "20:00:00",
    },
]


# === AIService init ===

def test_ai_service_raises_when_no_api_key():
    from app.services.ai_service import AIService, AIServiceUnavailableError
    with patch("app.services.ai_service.settings") as mock_settings:
        mock_settings.ANTHROPIC_API_KEY = None
        with pytest.raises(AIServiceUnavailableError, match="ANTHROPIC_API_KEY"):
            AIService()


def test_ai_service_creates_client_when_key_present():
    from app.services.ai_service import AIService
    with patch("app.services.ai_service.settings") as mock_settings, \
         patch("app.services.ai_service.anthropic.Anthropic") as mock_anthropic:
        mock_settings.ANTHROPIC_API_KEY = "test-key"
        svc = AIService()
        mock_anthropic.assert_called_once_with(api_key="test-key")


# === analyze_schedule ===

def _make_ai_service():
    from app.services.ai_service import AIService
    with patch("app.services.ai_service.settings") as mock_settings, \
         patch("app.services.ai_service.anthropic.Anthropic"):
        mock_settings.ANTHROPIC_API_KEY = "test-key"
        return AIService()


def test_analyze_schedule_returns_string():
    from app.services.ai_service import AIService
    with patch("app.services.ai_service.settings") as mock_settings, \
         patch("app.services.ai_service.anthropic.Anthropic") as mock_anthropic_cls:
        mock_settings.ANTHROPIC_API_KEY = "test-key"
        svc = AIService()

    # Mock the messages.create response
    mock_text_block = MagicMock()
    mock_text_block.type = "text"
    mock_text_block.text = "Schedule looks good. Hours are balanced."
    mock_response = MagicMock()
    mock_response.content = [mock_text_block]
    svc._client.messages.create.return_value = mock_response

    result = svc.analyze_schedule(SAMPLE_SCHEDULE, SAMPLE_SHIFTS)

    assert isinstance(result, str)
    assert "Schedule looks good" in result


def test_analyze_schedule_calls_correct_model():
    from app.services.ai_service import AIService
    with patch("app.services.ai_service.settings") as mock_settings, \
         patch("app.services.ai_service.anthropic.Anthropic"):
        mock_settings.ANTHROPIC_API_KEY = "test-key"
        svc = AIService()

    mock_text_block = MagicMock()
    mock_text_block.type = "text"
    mock_text_block.text = "Analysis"
    mock_response = MagicMock()
    mock_response.content = [mock_text_block]
    svc._client.messages.create.return_value = mock_response

    svc.analyze_schedule(SAMPLE_SCHEDULE, SAMPLE_SHIFTS)

    call_kwargs = svc._client.messages.create.call_args[1]
    assert call_kwargs["model"] == "claude-opus-4-6"


def test_analyze_schedule_uses_cached_system_prompt():
    from app.services.ai_service import AIService
    with patch("app.services.ai_service.settings") as mock_settings, \
         patch("app.services.ai_service.anthropic.Anthropic"):
        mock_settings.ANTHROPIC_API_KEY = "test-key"
        svc = AIService()

    mock_text_block = MagicMock()
    mock_text_block.type = "text"
    mock_text_block.text = "Analysis"
    mock_response = MagicMock()
    mock_response.content = [mock_text_block]
    svc._client.messages.create.return_value = mock_response

    svc.analyze_schedule(SAMPLE_SCHEDULE, SAMPLE_SHIFTS)

    call_kwargs = svc._client.messages.create.call_args[1]
    system = call_kwargs["system"]
    assert isinstance(system, list)
    assert system[0]["type"] == "text"
    assert system[0]["cache_control"] == {"type": "ephemeral"}


# === _build_analysis_prompt ===

def test_build_analysis_prompt_includes_week_start():
    from app.services.ai_service import AIService
    prompt = AIService._build_analysis_prompt(SAMPLE_SCHEDULE, SAMPLE_SHIFTS)
    assert "2026-04-21" in prompt


def test_build_analysis_prompt_includes_employee_names():
    from app.services.ai_service import AIService
    prompt = AIService._build_analysis_prompt(SAMPLE_SCHEDULE, SAMPLE_SHIFTS)
    assert "Alice" in prompt
    assert "Bob" in prompt


def test_build_analysis_prompt_includes_shift_dates():
    from app.services.ai_service import AIService
    prompt = AIService._build_analysis_prompt(SAMPLE_SCHEDULE, SAMPLE_SHIFTS)
    assert "2026-04-22" in prompt
    assert "2026-04-23" in prompt


def test_build_analysis_prompt_empty_shifts():
    from app.services.ai_service import AIService
    prompt = AIService._build_analysis_prompt(SAMPLE_SCHEDULE, [])
    assert "2026-04-21" in prompt
    assert "no shifts" in prompt.lower() or "no employees" in prompt.lower()
