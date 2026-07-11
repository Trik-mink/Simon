import numpy as np

from server.claude_client import _build_prompt
from projected_copilot.app import ai_overlay_point, Calibration, calibrate, ProjectorConfig


def test_prompt_omits_position_by_default():
    prompt = _build_prompt(None, want_position=False)
    assert '"position"' not in prompt


def test_prompt_includes_position_when_requested():
    prompt = _build_prompt(None, want_position=True)
    assert '"position"' in prompt


def test_overlay_point_none_when_not_calibrated():
    cal = Calibration()  # not ready
    assert ai_overlay_point({"x": 0.5, "y": 0.5}, cal, (720, 1280)) is None


def test_overlay_point_none_for_malformed_position():
    # A ready calibration (identity-ish) — malformed position should still yield None.
    config = ProjectorConfig(width=1280, height=720)
    markers = {
        0: np.array([[0, 0], [10, 0], [10, 10], [0, 10]], dtype=np.float32),
        1: np.array([[100, 0], [110, 0], [110, 10], [100, 10]], dtype=np.float32),
        2: np.array([[100, 100], [110, 100], [110, 110], [100, 110]], dtype=np.float32),
        3: np.array([[0, 100], [10, 0], [10, 110], [0, 110]], dtype=np.float32),
    }
    cal = calibrate(markers, config)
    assert cal.ready
    assert ai_overlay_point({"x": "oops"}, cal, (720, 1280)) is None
    assert ai_overlay_point(None, cal, (720, 1280)) is None


def test_overlay_point_maps_through_calibration():
    # Build a calibration from 4 known table markers, then confirm a normalized
    # camera position maps to an integer projector pixel inside the canvas.
    config = ProjectorConfig(width=1280, height=720)
    markers = {
        0: np.array([[64, 36], [80, 36], [80, 52], [64, 52]], dtype=np.float32),
        1: np.array([[1200, 36], [1216, 36], [1216, 52], [1200, 52]], dtype=np.float32),
        2: np.array([[1200, 668], [1216, 668], [1216, 684], [1200, 684]], dtype=np.float32),
        3: np.array([[64, 668], [80, 668], [80, 684], [64, 684]], dtype=np.float32),
    }
    cal = calibrate(markers, config)
    assert cal.ready
    point = ai_overlay_point({"x": 0.5, "y": 0.5}, cal, (720, 1280))
    assert point is not None
    x, y = point
    assert isinstance(x, int) and isinstance(y, int)
    assert 0 <= x <= config.width
    assert 0 <= y <= config.height
