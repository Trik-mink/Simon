from __future__ import annotations

import os
import time
from typing import Dict, List

import numpy as np
from PIL import Image


EMOTION_FILES = {
    "dance": "dragon_dance_true_frames.gif",
    "thinking": "simon_thinking.gif",
    "study": "simon_study_with_me.gif",
    "nonchalant": "simon_nonchalant.gif",
    "sad": "simon_sad.gif",
}


def _load_gif_frames(path: str) -> List[np.ndarray]:
    """Load all frames from a GIF as RGBA numpy arrays, removing white backgrounds."""
    gif = Image.open(path)
    frames = []
    try:
        while True:
            frame = gif.copy().convert("RGBA")
            arr = np.array(frame)
            white = (arr[:, :, 0] > 240) & (arr[:, :, 1] > 240) & (arr[:, :, 2] > 240)
            arr[white, 3] = 0
            frames.append(arr)
            gif.seek(gif.tell() + 1)
    except EOFError:
        pass
    return frames if frames else [np.array(gif.convert("RGBA"))]


class SimonRenderer:
    def __init__(self, assets_dir: str) -> None:
        self._frames: Dict[str, List[np.ndarray]] = {}
        for emotion, filename in EMOTION_FILES.items():
            path = os.path.join(assets_dir, filename)
            self._frames[emotion] = _load_gif_frames(path)
        self._emotion = "dance"
        self._frame_index = 0
        self._last_advance = time.time()
        self._fps = 10.0

    def set_emotion(self, emotion: str) -> None:
        if emotion not in EMOTION_FILES:
            raise ValueError(f"Unknown emotion: {emotion}. Valid: {list(EMOTION_FILES)}")
        if emotion != self._emotion:
            self._emotion = emotion
            self._frame_index = 0

    def render(self, canvas: np.ndarray, x: int, y: int, size: int) -> None:
        """Draw current animated frame onto canvas at top-left corner (x, y)."""
        now = time.time()
        frames = self._frames[self._emotion]
        if now - self._last_advance >= 1.0 / self._fps:
            self._frame_index = (self._frame_index + 1) % len(frames)
            self._last_advance = now

        frame_rgba = frames[self._frame_index]
        pil_frame = Image.fromarray(frame_rgba).resize((size, size), Image.NEAREST)
        frame = np.array(pil_frame)

        bgr = frame[:, :, :3][:, :, ::-1]
        alpha = frame[:, :, 3:4] / 255.0

        h, w = bgr.shape[:2]
        # x, y is top-left corner of Simon
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(canvas.shape[1], x + w), min(canvas.shape[0], y + h)
        if x2 <= x1 or y2 <= y1:
            return

        bx1, by1 = x1 - x, y1 - y
        bx2, by2 = bx1 + (x2 - x1), by1 + (y2 - y1)

        roi = canvas[y1:y2, x1:x2].astype(np.float32)
        src = bgr[by1:by2, bx1:bx2].astype(np.float32)
        a = alpha[by1:by2, bx1:bx2]
        canvas[y1:y2, x1:x2] = np.clip(a * src + (1 - a) * roi, 0, 255).astype(np.uint8)
