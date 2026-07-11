from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


MARKERS = [
    (0, "table top-left"),
    (1, "table top-right"),
    (2, "table bottom-right"),
    (3, "table bottom-left"),
    (10, "study object"),
    (20, "electronics object"),
    (30, "tabletop object"),
]


def draw_marker(marker_id: int, label: str, size: int = 220) -> np.ndarray:
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    if hasattr(cv2.aruco, "generateImageMarker"):
        marker = cv2.aruco.generateImageMarker(dictionary, marker_id, size)
    else:
        marker = cv2.aruco.drawMarker(dictionary, marker_id, size)

    tile = np.full((size + 72, size + 28), 255, dtype=np.uint8)
    tile[14 : 14 + size, 14 : 14 + size] = marker
    cv2.putText(tile, f"ID {marker_id}", (14, size + 42), cv2.FONT_HERSHEY_SIMPLEX, 0.8, 0, 2, cv2.LINE_AA)
    cv2.putText(tile, label, (14, size + 66), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 0, 1, cv2.LINE_AA)
    return tile


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "markers"
    out_dir.mkdir(exist_ok=True)

    tiles = []
    for marker_id, label in MARKERS:
        tile = draw_marker(marker_id, label)
        cv2.imwrite(str(out_dir / f"marker_{marker_id}.png"), tile)
        tiles.append(tile)

    cols = 2
    rows = int(np.ceil(len(tiles) / cols))
    tile_h, tile_w = tiles[0].shape
    sheet = np.full((rows * tile_h, cols * tile_w), 255, dtype=np.uint8)
    for index, tile in enumerate(tiles):
        row = index // cols
        col = index % cols
        sheet[row * tile_h : (row + 1) * tile_h, col * tile_w : (col + 1) * tile_w] = tile

    cv2.imwrite(str(out_dir / "markers_sheet.png"), sheet)
    print(f"Wrote markers to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

