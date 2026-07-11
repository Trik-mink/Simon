from __future__ import annotations

import argparse

import cv2


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview a camera index for Projected Copilot")
    parser.add_argument("--camera", type=int, default=0)
    args = parser.parse_args()

    capture = cv2.VideoCapture(args.camera)
    if not capture.isOpened():
        print(f"ERROR: could not open camera index {args.camera}")
        return 1

    print("Press q or esc to quit.")
    while True:
        ok, frame = capture.read()
        if not ok:
            print("ERROR: camera frame read failed")
            break
        cv2.imshow(f"Camera {args.camera}", frame)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):
            break

    capture.release()
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

