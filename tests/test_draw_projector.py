import numpy as np
from projected_copilot.app import draw_projector, draw_test_target, ProjectorConfig, Calibration


def _blank_canvas(config):
    return np.zeros((config.height, config.width, 3), dtype=np.uint8)


def test_draw_projector_clears_canvas():
    config = ProjectorConfig(width=320, height=240)
    canvas = np.ones((240, 320, 3), dtype=np.uint8) * 255
    draw_projector(canvas, config, None, Calibration(), {}, None, 0.0)
    assert canvas.max() == 0


def test_draw_projector_draws_something_when_active():
    config = ProjectorConfig(width=320, height=240)
    canvas = _blank_canvas(config)
    draw_projector(canvas, config, "study", Calibration(), {}, None, 0.0)
    assert canvas.max() > 0


def test_draw_projector_returns_none():
    config = ProjectorConfig(width=320, height=240)
    canvas = _blank_canvas(config)
    result = draw_projector(canvas, config, None, Calibration(), {}, None, 0.0)
    assert result is None


def test_draw_test_target_draws_center_marker():
    config = ProjectorConfig(width=320, height=240)
    canvas = _blank_canvas(config)
    draw_test_target(canvas, config, 0.5)
    assert canvas.max() > 0
