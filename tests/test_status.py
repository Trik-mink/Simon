from types import SimpleNamespace

import server.main as main


def test_current_status_reports_camera_and_claude(monkeypatch):
    monkeypatch.setattr(main, "camera", SimpleNamespace())
    monkeypatch.setattr(main, "camera_error", None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    status = main.current_status()

    assert status["camera"]["ready"] is True
    assert status["camera"]["index"] == main.CAMERA_INDEX
    assert status["claude"]["configured"] is True
    assert status["claude"]["model"]


def test_current_status_reports_camera_error(monkeypatch):
    monkeypatch.setattr(main, "camera", None)
    monkeypatch.setattr(main, "camera_error", "camera failed")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    status = main.current_status()

    assert status["camera"]["ready"] is False
    assert status["camera"]["error"] == "camera failed"
    assert status["claude"]["configured"] is False


def test_set_scan_state_updates_status():
    main._set_scan_state("thinking", "Analyzing desk", in_flight=True)

    status = main.current_status()

    assert status["scan"]["phase"] == "thinking"
    assert status["scan"]["message"] == "Analyzing desk"
    assert status["scan"]["in_flight"] is True

    main._set_scan_state("idle", "Ready")


def test_finish_scan_state_records_returned_point():
    main._finish_scan_state({"position": {"x": 0.4, "y": 0.6}}, want_position=True)

    status = main.current_status()

    assert status["scan"]["phase"] == "answer-ready"
    assert status["scan"]["point_requested"] is True
    assert status["scan"]["point_returned"] is True
    assert status["scan"]["point_warning"] is None


def test_finish_scan_state_warns_when_point_requested_but_missing():
    main._finish_scan_state({"position": None}, want_position=True)

    status = main.current_status()

    assert status["scan"]["phase"] == "answer-ready"
    assert status["scan"]["message"] == "Answer ready - no point"
    assert status["scan"]["point_requested"] is True
    assert status["scan"]["point_returned"] is False
    assert status["scan"]["point_warning"] == "Claude did not return a point."


def test_current_status_includes_default_pointing_state():
    main._set_projector_state(
        calibrated=False,
        table_markers_found=0,
        point_enabled=False,
        test_point_enabled=False,
        last_point=None,
    )

    status = main.current_status()

    assert status["pointing"]["ready"] is False
    assert status["pointing"]["calibrated"] is False
    assert status["pointing"]["table_markers_found"] == 0
    assert status["pointing"]["point_enabled"] is False
    assert status["pointing"]["test_point_enabled"] is False
    assert status["pointing"]["last_point"] is None


async def test_projector_status_update_sets_pointing_state():
    body = main.ProjectorStatusRequest(
        calibrated=True,
        table_markers_found=4,
        point_enabled=True,
        test_point_enabled=True,
        last_point={"x": 0.5, "y": 0.25},
    )

    result = await main.projector_status_update(body)
    status = main.current_status()

    assert result == {"ok": True}
    assert status["calibrated"] is True
    assert status["pointing"]["ready"] is True
    assert status["pointing"]["table_markers_found"] == 4
    assert status["pointing"]["point_enabled"] is True
    assert status["pointing"]["test_point_enabled"] is True
    assert status["pointing"]["last_point"] == {"x": 0.5, "y": 0.25}
