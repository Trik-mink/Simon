from __future__ import annotations

import time
from typing import Optional

import cv2
import numpy as np

ORANGE = (40, 106, 255)   # BGR for #ff6a00
BLACK = (10, 10, 10)
MAX_CHARS_PER_LINE = 28
FONT = cv2.FONT_HERSHEY_SIMPLEX
FONT_SCALE = 0.55
FONT_THICKNESS = 1
PAD = 14


def _wrap_text(text: str, max_chars: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if len(current) + len(word) + (1 if current else 0) <= max_chars:
            current = f"{current} {word}".strip()
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


class SpeechBubble:
    def __init__(self) -> None:
        self._text: Optional[str] = None
        self._expires_at: float = 0.0

    def show(self, text: str, duration: float = 5.0) -> None:
        self._text = text[:120]
        self._expires_at = time.time() + duration

    def render(self, canvas: np.ndarray, anchor_x: int, anchor_y: int) -> None:
        if self._text is None or time.time() > self._expires_at:
            return

        lines = _wrap_text(self._text, MAX_CHARS_PER_LINE)
        line_heights = []
        line_widths = []
        for line in lines:
            (w, h), _ = cv2.getTextSize(line, FONT, FONT_SCALE, FONT_THICKNESS)
            line_heights.append(h)
            line_widths.append(w)

        box_w = max(line_widths) + PAD * 2
        line_h = max(line_heights) if line_heights else 16
        box_h = line_h * len(lines) + PAD * 2 + (len(lines) - 1) * 4

        # Place bubble above anchor
        bx = max(0, anchor_x - box_w // 2)
        by = max(0, anchor_y - box_h - 20)

        # Clamp to canvas
        bx = min(bx, canvas.shape[1] - box_w - 2)
        by = max(by, 2)

        cv2.rectangle(canvas, (bx, by), (bx + box_w, by + box_h), BLACK, -1)
        cv2.rectangle(canvas, (bx, by), (bx + box_w, by + box_h), ORANGE, 2, cv2.LINE_AA)

        y_cursor = by + PAD + line_h
        for line in lines:
            cv2.putText(canvas, line, (bx + PAD, y_cursor), FONT, FONT_SCALE, ORANGE, FONT_THICKNESS, cv2.LINE_AA)
            y_cursor += line_h + 4

        # Tail pointing down toward Simon
        tail_x = anchor_x
        tail_top = by + box_h
        cv2.line(canvas, (tail_x, tail_top), (tail_x, anchor_y - 4), ORANGE, 2, cv2.LINE_AA)
