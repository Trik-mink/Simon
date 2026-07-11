import numpy as np
from projected_copilot.app import mask_markers

def test_mask_markers_fills_polygon_with_black():
    frame = np.ones((480, 640, 3), dtype=np.uint8) * 255
    corners = np.array(
        [[100, 100], [200, 100], [200, 200], [100, 200]], dtype=np.float32
    )
    result = mask_markers(frame, {0: corners})
    assert result[150, 150].tolist() == [0, 0, 0], "center of marker should be black"

def test_mask_markers_leaves_outside_untouched():
    frame = np.ones((480, 640, 3), dtype=np.uint8) * 255
    corners = np.array(
        [[100, 100], [200, 100], [200, 200], [100, 200]], dtype=np.float32
    )
    result = mask_markers(frame, {0: corners})
    assert result[50, 50].tolist() == [255, 255, 255], "outside marker should be unchanged"

def test_mask_markers_handles_no_markers():
    frame = np.ones((480, 640, 3), dtype=np.uint8) * 128
    result = mask_markers(frame, {})
    np.testing.assert_array_equal(result, frame)

def test_mask_markers_does_not_modify_original():
    frame = np.ones((480, 640, 3), dtype=np.uint8) * 200
    corners = np.array(
        [[10, 10], [50, 10], [50, 50], [10, 50]], dtype=np.float32
    )
    original = frame.copy()
    mask_markers(frame, {0: corners})
    np.testing.assert_array_equal(frame, original)
