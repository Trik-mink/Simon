import numpy as np
import pytest
from projected_copilot.simon import SimonRenderer


ASSETS_DIR = "assets/simon"


def test_loads_all_emotions():
    renderer = SimonRenderer(ASSETS_DIR)
    for emotion in ("dance", "thinking", "study", "nonchalant", "sad"):
        renderer.set_emotion(emotion)


def test_renders_onto_canvas():
    renderer = SimonRenderer(ASSETS_DIR)
    canvas = np.zeros((720, 1280, 3), dtype=np.uint8)
    renderer.render(canvas, x=1080, y=520, size=160)
    # Canvas should have been modified (Simon drawn)
    assert canvas.sum() > 0


def test_invalid_emotion_raises():
    renderer = SimonRenderer(ASSETS_DIR)
    with pytest.raises(ValueError):
        renderer.set_emotion("unknown")
