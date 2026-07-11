import inspect
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from server.claude_client import analyze_desk, _build_prompt, _parse_response


def test_analyze_desk_is_coroutine():
    assert inspect.iscoroutinefunction(analyze_desk), (
        "analyze_desk must be async — calling a sync Anthropic client "
        "inside an async FastAPI handler blocks the entire event loop"
    )


def test_build_prompt_without_question():
    prompt = _build_prompt(None)
    assert "JSON" in prompt
    assert "emotion" in prompt


def test_build_prompt_with_question():
    prompt = _build_prompt("What is on this desk?")
    assert "What is on this desk?" in prompt


def test_parse_response_valid():
    raw = '{"emotion": "study", "guidance": "This looks like a worksheet", "position": {"x": 0.3, "y": 0.4}}'
    result = _parse_response(raw)
    assert result["emotion"] == "study"
    assert result["position"]["x"] == 0.3


def test_parse_response_clamps_position_to_normalized_range():
    raw = '{"emotion": "study", "guidance": "Point here", "position": {"x": 1.4, "y": -0.2}}'
    result = _parse_response(raw)
    assert result["position"] == {"x": 1.0, "y": 0.0}


def test_parse_response_malformed_position_becomes_none():
    raw = '{"emotion": "study", "guidance": "Point here", "position": {"x": 0.3}}'
    result = _parse_response(raw)
    assert result["position"] is None


def test_parse_response_missing_position():
    raw = '{"emotion": "nonchalant", "guidance": "Nothing here", "position": null}'
    result = _parse_response(raw)
    assert result["position"] is None


def test_parse_response_invalid_json_returns_fallback():
    result = _parse_response("not json at all")
    assert result["emotion"] == "sad"
    assert "position" in result
