import pytest
from unittest.mock import MagicMock, patch
import numpy as np
from server.camera import Camera


def test_capture_jpeg_returns_bytes():
    fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    with patch("cv2.VideoCapture") as mock_cap:
        instance = mock_cap.return_value
        instance.isOpened.return_value = True
        instance.read.return_value = (True, fake_frame)
        cam = Camera(index=0)
        result = cam.capture_jpeg()
        assert isinstance(result, bytes)
        assert len(result) > 0
        cam.release()


def test_capture_jpeg_raises_on_failed_read():
    with patch("cv2.VideoCapture") as mock_cap:
        instance = mock_cap.return_value
        instance.isOpened.return_value = True
        instance.read.return_value = (False, None)
        cam = Camera(index=0)
        with pytest.raises(RuntimeError):
            cam.capture_jpeg()
        cam.release()
