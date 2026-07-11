from __future__ import annotations

import asyncio
import threading
import time
from typing import AsyncGenerator, Optional

import cv2
import numpy as np


class Camera:
    """Single owner of the physical camera.

    macOS allows only one process to hold a camera, and even within this process
    a cv2.VideoCapture must not be read concurrently. So one background thread is
    the *only* reader; it keeps the latest frame (and its JPEG) in memory. Every
    consumer — the web MJPEG stream, /ask, /scan — serves from that cache without
    touching the device, so they never contend or starve each other.
    """

    def __init__(self, index: int = 0) -> None:
        self._cap = cv2.VideoCapture(index)
        if not self._cap.isOpened():
            raise RuntimeError(f"Could not open camera index {index}")

        self._lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_jpeg: Optional[bytes] = None
        self._stop = threading.Event()

        # Prime one frame synchronously so the first consumer isn't racing the
        # reader thread (and so a dead camera surfaces right away).
        self._grab_once()

        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def _grab_once(self, quality: int = 80) -> bool:
        ok, frame = self._cap.read()
        if not ok or frame is None:
            return False
        enc_ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not enc_ok:
            return False
        with self._lock:
            self._latest_frame = frame
            self._latest_jpeg = buf.tobytes()
        return True

    def _reader(self) -> None:
        while not self._stop.is_set():
            if not self._grab_once():
                time.sleep(0.05)  # transient read failure — retry, don't die
                continue
            time.sleep(0.01)

    def capture_jpeg(self, quality: int = 80) -> bytes:
        """Return the most recent JPEG frame (from cache, non-blocking)."""
        with self._lock:
            if self._latest_jpeg is None:
                raise RuntimeError("Camera frame read failed")
            return self._latest_jpeg

    def capture_frame(self) -> np.ndarray:
        """Return a copy of the most recent BGR frame (from cache)."""
        with self._lock:
            if self._latest_frame is None:
                raise RuntimeError("Camera frame read failed")
            return self._latest_frame.copy()

    def release(self) -> None:
        self._stop.set()
        self._cap.release()


async def mjpeg_generator(camera: Camera) -> AsyncGenerator[bytes, None]:
    while True:
        try:
            jpeg = camera.capture_jpeg()
        except RuntimeError:
            # No frame yet or a transient hiccup — wait and keep the stream open
            # instead of ending it (a closed MJPEG stream breaks the <img> tag
            # and won't recover without a page reload).
            await asyncio.sleep(0.1)
            continue
        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
        await asyncio.sleep(0.033)
