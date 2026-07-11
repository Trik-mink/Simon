import time
import numpy as np
from projected_copilot.speech_bubble import SpeechBubble


def test_renders_when_active():
    bubble = SpeechBubble()
    canvas = np.zeros((720, 1280, 3), dtype=np.uint8)
    bubble.show("Hello Simon!", duration=5.0)
    bubble.render(canvas, anchor_x=1080, anchor_y=520)
    assert canvas.sum() > 0


def test_no_render_when_inactive():
    bubble = SpeechBubble()
    canvas = np.zeros((720, 1280, 3), dtype=np.uint8)
    bubble.render(canvas, anchor_x=1080, anchor_y=520)
    assert canvas.sum() == 0


def test_expires_after_duration():
    bubble = SpeechBubble()
    bubble.show("expire me", duration=0.01)
    time.sleep(0.05)
    canvas = np.zeros((720, 1280, 3), dtype=np.uint8)
    bubble.render(canvas, anchor_x=1080, anchor_y=520)
    assert canvas.sum() == 0


def test_truncates_at_120_chars():
    bubble = SpeechBubble()
    long_text = "x" * 150
    bubble.show(long_text)
    # Internal text should be capped at 120
    assert len(bubble._text) == 120
