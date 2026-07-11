"""Tests for classify_command helper in projected_copilot/app.py."""
from projected_copilot.app import classify_command


def test_scan_result_no_action_key():
    assert classify_command({"emotion": "study", "guidance": "x", "answer": "y", "position": None}) == "scan"


def test_ask_action():
    assert classify_command({"action": "ask", "guidance": "hi"}) == "ask"


def test_reveal_action():
    assert classify_command({"action": "reveal"}) == "reveal"


def test_scan_request_action():
    assert classify_command({"action": "scan_request"}) == "scan_request"


def test_scan_status_action():
    assert classify_command({"action": "scan_status", "scan": {"in_flight": True}}) == "scan_status"


def test_error_action():
    assert classify_command({"action": "error", "message": "Scan failed"}) == "error"


def test_context_action_is_ignored():
    assert classify_command({"action": "context", "mode": "study"}) == "ignore"


def test_stop_action_is_ignored():
    assert classify_command({"action": "stop"}) == "ignore"


def test_speak_action_is_ignored():
    assert classify_command({"action": "speak"}) == "ignore"


def test_reset_action_is_ignored():
    assert classify_command({"action": "reset"}) == "ignore"
