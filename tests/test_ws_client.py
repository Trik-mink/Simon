import queue

from projected_copilot.ws_client import ProjectorWSClient


def _client():
    client = ProjectorWSClient.__new__(ProjectorWSClient)
    client._commands = queue.Queue()
    return client


def test_get_command_returns_none_initially():
    assert _client().get_command() is None


def test_get_command_pops_value():
    client = _client()
    client._commands.put({"emotion": "thinking", "guidance": "hello", "position": None})
    cmd = client.get_command()
    assert cmd["emotion"] == "thinking"
    assert client.get_command() is None


def test_two_messages_between_polls_are_both_delivered():
    # Regression: a projector_status echo must not clobber a scan result.
    client = _client()
    client._commands.put({"action": "projector_status", "calibrated": True})
    client._commands.put({"emotion": "happy", "guidance": "found it", "position": {"x": 0.5, "y": 0.5}})
    first = client.get_command()
    second = client.get_command()
    assert first["action"] == "projector_status"
    assert second["guidance"] == "found it"
    assert client.get_command() is None
