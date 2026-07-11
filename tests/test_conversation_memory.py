import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from server.claude_client import analyze_desk, reset_history, _history, _MAX_HISTORY

_FAKE_RESPONSE = '{"emotion": "study", "guidance": "check step 2", "answer": "42"}'


@pytest.fixture(autouse=True)
def clear_history():
    reset_history()
    yield
    reset_history()


def test_history_starts_empty():
    assert _history == []


def test_reset_clears_history():
    _history.append({"role": "user", "content": "test"})
    reset_history()
    assert _history == []


async def test_analyze_desk_appends_user_and_assistant():
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=_FAKE_RESPONSE)]
    with patch("server.claude_client._client.messages.create", new=AsyncMock(return_value=mock_resp)):
        await analyze_desk(b"fake_jpeg")
    assert len(_history) == 2
    assert _history[0]["role"] == "user"
    assert _history[1]["role"] == "assistant"


async def test_history_accumulates_across_scans():
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=_FAKE_RESPONSE)]
    with patch("server.claude_client._client.messages.create", new=AsyncMock(return_value=mock_resp)):
        await analyze_desk(b"jpeg_1")
        await analyze_desk(b"jpeg_2")
    assert len(_history) == 4


async def test_history_capped_at_max():
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=_FAKE_RESPONSE)]
    with patch("server.claude_client._client.messages.create", new=AsyncMock(return_value=mock_resp)):
        for _ in range(10):
            await analyze_desk(b"fake_jpeg")
    assert len(_history) <= _MAX_HISTORY


async def test_messages_sent_to_api_include_full_history():
    mock_create = AsyncMock()
    mock_create.return_value = MagicMock(content=[MagicMock(text=_FAKE_RESPONSE)])
    with patch("server.claude_client._client.messages.create", new=mock_create):
        await analyze_desk(b"jpeg_1")
        await analyze_desk(b"jpeg_2")
    second_call_messages = mock_create.call_args_list[1].kwargs["messages"]
    assert len(second_call_messages) == 3  # 2 from first exchange + new user message


async def test_only_newest_message_keeps_its_image():
    mock_create = AsyncMock()
    mock_create.return_value = MagicMock(content=[MagicMock(text=_FAKE_RESPONSE)])
    with patch("server.claude_client._client.messages.create", new=mock_create):
        await analyze_desk(b"jpeg_1")
        await analyze_desk(b"jpeg_2")
        await analyze_desk(b"jpeg_3")

    def image_blocks(msg):
        content = msg["content"]
        if not isinstance(content, list):
            return []
        return [b for b in content if b.get("type") == "image"]

    third_call_messages = mock_create.call_args_list[2].kwargs["messages"]
    user_messages = [m for m in third_call_messages if m["role"] == "user"]
    assert len(user_messages) == 3
    # Older user messages carry a placeholder, only the newest has the image
    assert all(not image_blocks(m) for m in user_messages[:-1])
    assert len(image_blocks(user_messages[-1])) == 1
