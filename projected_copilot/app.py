from __future__ import annotations

import argparse
import math
import os
import queue
import threading
import time
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple

import cv2
import numpy as np
import requests as _http

# GestureDetector (gesture.py) kept as camera-based fallback — not used while glove is active
from projected_copilot.glove_input import GloveInput
from projected_copilot.simon import SimonRenderer
from projected_copilot.speech_bubble import SpeechBubble
from projected_copilot.ws_client import ProjectorWSClient


BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# All backend posts go through one daemon worker draining a queue over a shared
# Session — the render loop never blocks on HTTP, and a slow backend can't pile
# up unbounded threads.
_post_session = _http.Session()
_post_queue: "queue.Queue[tuple[str, dict]]" = queue.Queue()


def _post_worker() -> None:
    while True:
        path, kwargs = _post_queue.get()
        try:
            _post_session.post(f"{BACKEND_URL}{path}", **kwargs)
        except Exception:
            pass


threading.Thread(target=_post_worker, daemon=True).start()


def _post_async(path: str, **kwargs) -> None:
    _post_queue.put((path, kwargs))


def _post_gesture(gtype: str, marker_context: str | None = None) -> None:
    _post_async("/gesture", json={"type": gtype, "marker_context": marker_context}, timeout=3)


def _post_context(context: str | None) -> None:
    _post_async("/context", json={"mode": context}, timeout=2)


def _post_projector_status(payload: dict) -> None:
    _post_async("/projector/status", json=payload, timeout=1)


def mask_markers(frame: np.ndarray, markers: Dict[int, np.ndarray]) -> np.ndarray:
    masked = frame.copy()
    for corners in markers.values():
        pts = corners.astype(np.int32).reshape((-1, 1, 2))
        cv2.fillPoly(masked, [pts], (0, 0, 0))
    return masked


def _post_scan(jpeg: bytes, context: str | None, want_position: bool = False) -> None:
    _post_async(
        "/scan",
        data=jpeg,
        headers={
            "Content-Type": "image/jpeg",
            "X-Context": context or "",
            "X-Point": "true" if want_position else "false",
        },
        timeout=15,
    )


def request_scan_from_projector(capture, markers: Dict[int, np.ndarray], config: ProjectorConfig, context: str | None, want_position: bool) -> None:
    black = np.zeros((config.height, config.width, 3), dtype=np.uint8)
    cv2.imshow("Projected Copilot - Projector", black)
    cv2.waitKey(100)  # let the display actually go black before capturing
    blank_time = time.time()
    # Wait for a frame captured *after* the blank (projector→camera→stream
    # latency varies), so the scan image doesn't still show projected overlays.
    if hasattr(capture, "read_after"):
        ok, scan_frame = capture.read_after(blank_time, timeout=1.5)
    else:
        cv2.waitKey(200)
        ok, scan_frame = capture.read()
    if not ok:
        return
    masked = mask_markers(scan_frame, markers)
    _, jpeg_buf = cv2.imencode(".jpg", masked, [cv2.IMWRITE_JPEG_QUALITY, 85])
    _post_scan(jpeg_buf.tobytes(), context, want_position)


def classify_command(cmd: dict) -> str:
    """Return how the projector should treat a broadcast command:
    'ask', 'reveal', 'scan_request', 'scan_status', 'error',
    'scan' (a Claude scan result with no action key), or 'ignore'."""
    action = cmd.get("action")
    if action == "ask":
        return "ask"
    if action == "reveal":
        return "reveal"
    if action == "scan_request":
        return "scan_request"
    if action == "scan_status":
        return "scan_status"
    if action == "error":
        return "error"
    if action is None:
        return "scan"
    return "ignore"


ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "simon")


TABLE_MARKERS = {
    0: "top_left",
    1: "top_right",
    2: "bottom_right",
    3: "bottom_left",
}

OBJECT_MARKERS = {
    10: "study",
    20: "electronics",
    30: "tabletop",
}

@dataclass(frozen=True)
class ProjectorConfig:
    width: int = 1280
    height: int = 720
    margin: int = 80


SIMON_SIZE = 160
SIMON_MARGIN = 20


@dataclass
class Calibration:
    camera_to_projector: Optional[np.ndarray] = None
    projector_to_camera: Optional[np.ndarray] = None
    last_calibrated_at: Optional[float] = None

    @property
    def ready(self) -> bool:
        return self.camera_to_projector is not None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Projected Copilot MVP")
    parser.add_argument("--camera", type=int, default=0, help="OpenCV camera index")
    parser.add_argument("--projector-width", type=int, default=1280)
    parser.add_argument("--projector-height", type=int, default=720)
    parser.add_argument("--windowed", action="store_true", help="Do not force fullscreen projector window")
    return parser.parse_args()


def create_aruco_detector():
    aruco = cv2.aruco
    dictionary = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    parameters = aruco.DetectorParameters()
    if hasattr(aruco, "ArucoDetector"):
        return aruco.ArucoDetector(dictionary, parameters)
    return dictionary, parameters


def detect_markers(frame: np.ndarray, detector) -> Dict[int, np.ndarray]:
    if hasattr(detector, "detectMarkers"):
        corners, ids, _ = detector.detectMarkers(frame)
    else:
        dictionary, parameters = detector
        corners, ids, _ = cv2.aruco.detectMarkers(frame, dictionary, parameters=parameters)

    found: Dict[int, np.ndarray] = {}
    if ids is None:
        return found

    for marker_corners, marker_id in zip(corners, ids.flatten()):
        found[int(marker_id)] = marker_corners.reshape(4, 2).astype(np.float32)
    return found


def marker_center(corners: np.ndarray) -> np.ndarray:
    return corners.mean(axis=0).astype(np.float32)


def table_projector_points(config: ProjectorConfig) -> np.ndarray:
    m = float(config.margin)
    return np.array(
        [
            [m, m],
            [config.width - m, m],
            [config.width - m, config.height - m],
            [m, config.height - m],
        ],
        dtype=np.float32,
    )


def calibrate(markers: Dict[int, np.ndarray], config: ProjectorConfig) -> Calibration:
    if not all(marker_id in markers for marker_id in TABLE_MARKERS):
        return Calibration()

    camera_points = np.array(
        [marker_center(markers[0]), marker_center(markers[1]), marker_center(markers[2]), marker_center(markers[3])],
        dtype=np.float32,
    )
    projector_points = table_projector_points(config)
    camera_to_projector = cv2.getPerspectiveTransform(camera_points, projector_points)
    projector_to_camera = cv2.getPerspectiveTransform(projector_points, camera_points)
    return Calibration(camera_to_projector, projector_to_camera, time.time())


def transform_points(points: Iterable[Tuple[float, float]], homography: np.ndarray) -> np.ndarray:
    source = np.array(list(points), dtype=np.float32).reshape(-1, 1, 2)
    transformed = cv2.perspectiveTransform(source, homography)
    return transformed.reshape(-1, 2)


def object_anchor(mode: str, markers: Dict[int, np.ndarray], calibration: Calibration, config: ProjectorConfig) -> Tuple[int, int]:
    marker_id = {"study": 10, "electronics": 20, "tabletop": 30}[mode]
    if calibration.ready and marker_id in markers:
        projected = transform_points([tuple(marker_center(markers[marker_id]))], calibration.camera_to_projector)
        x, y = projected[0]
        return int(x), int(y)

    fallbacks = {
        "study": (int(config.width * 0.25), int(config.height * 0.48)),
        "electronics": (int(config.width * 0.52), int(config.height * 0.5)),
        "tabletop": (int(config.width * 0.76), int(config.height * 0.48)),
    }
    return fallbacks[mode]


def draw_glow_line(canvas: np.ndarray, start: Tuple[int, int], end: Tuple[int, int], color: Tuple[int, int, int], thickness: int) -> None:
    for scale, alpha in [(5, 0.18), (3, 0.28), (1, 1.0)]:
        overlay = canvas.copy()
        cv2.line(overlay, start, end, color, thickness * scale, cv2.LINE_AA)
        cv2.addWeighted(overlay, alpha, canvas, 1 - alpha, 0, canvas)


def draw_label(canvas: np.ndarray, text: str, origin: Tuple[int, int], color: Tuple[int, int, int]) -> None:
    x, y = origin
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.85
    thickness = 2
    (tw, th), baseline = cv2.getTextSize(text, font, scale, thickness)
    pad = 14
    cv2.rectangle(canvas, (x - pad, y - th - pad), (x + tw + pad, y + baseline + pad), (8, 10, 14), -1)
    cv2.rectangle(canvas, (x - pad, y - th - pad), (x + tw + pad, y + baseline + pad), color, 2)
    cv2.putText(canvas, text, (x, y), font, scale, color, thickness, cv2.LINE_AA)


def draw_arrow(canvas: np.ndarray, start: Tuple[int, int], end: Tuple[int, int], color: Tuple[int, int, int]) -> None:
    draw_glow_line(canvas, start, end, color, 4)
    cv2.arrowedLine(canvas, start, end, color, 4, cv2.LINE_AA, tipLength=0.18)


def draw_study_overlay(canvas: np.ndarray, anchor: Tuple[int, int], pulse: float) -> None:
    x, y = anchor
    color = (255, 170, 40)
    cv2.rectangle(canvas, (x - 165, y - 105), (x + 165, y + 105), color, 3, cv2.LINE_AA)
    draw_arrow(canvas, (x + 210, y - 95), (x + 80, y - 25), color)
    draw_label(canvas, "Hint: check step 2", (x + 190, y - 115), color)
    radius = int(12 + 8 * pulse)
    cv2.circle(canvas, (x + 80, y - 25), radius, color, 2, cv2.LINE_AA)


def draw_electronics_overlay(canvas: np.ndarray, anchor: Tuple[int, int], pulse: float) -> None:
    x, y = anchor
    color = (40, 60, 255)
    radius = int(68 + 10 * pulse)
    cv2.circle(canvas, (x, y), radius, color, 5, cv2.LINE_AA)
    draw_arrow(canvas, (x + 230, y - 110), (x + 55, y - 25), color)
    draw_label(canvas, "Issue: check ground rail", (x + 210, y - 130), color)


def draw_tabletop_overlay(canvas: np.ndarray, anchor: Tuple[int, int], pulse: float) -> None:
    x, y = anchor
    blue = (255, 120, 40)
    red = (40, 45, 255)
    green = (80, 255, 120)
    cv2.circle(canvas, (x - 85, y + 10), 115, blue, 4, cv2.LINE_AA)
    overlay = canvas.copy()
    cv2.ellipse(overlay, (x + 105, y - 35), (135, 80), -18, 0, 360, red, -1, cv2.LINE_AA)
    cv2.addWeighted(overlay, 0.22 + 0.1 * pulse, canvas, 0.78 - 0.1 * pulse, 0, canvas)
    cv2.rectangle(canvas, (x + 15, y + 110), (x + 165, y + 190), green, 4, cv2.LINE_AA)
    draw_label(canvas, "Move range", (x - 180, y - 130), blue)
    draw_label(canvas, "Danger zone", (x + 155, y - 135), red)
    draw_label(canvas, "Objective", (x + 10, y + 235), green)


def draw_ai_overlay(canvas: np.ndarray, point: Tuple[int, int], pulse: float) -> None:
    """Draw AI-generated guidance at a projector-pixel point (x, y)."""
    x, y = point
    color = (40, 106, 255)  # orange BGR
    radius = int(18 + 8 * pulse)
    cv2.circle(canvas, (x, y), radius, color, 3, cv2.LINE_AA)
    draw_arrow(canvas, (x + 120, y - 60), (x + radius, y), color)


def draw_test_target(canvas: np.ndarray, config: ProjectorConfig, pulse: float) -> None:
    """Draw a fixed target at the center of the calibrated projector table area."""
    color = (80, 255, 120)
    x = config.width // 2
    y = config.height // 2
    radius = int(22 + 8 * pulse)
    cv2.circle(canvas, (x, y), radius, color, 3, cv2.LINE_AA)
    cv2.line(canvas, (x - 58, y), (x + 58, y), color, 3, cv2.LINE_AA)
    cv2.line(canvas, (x, y - 58), (x, y + 58), color, 3, cv2.LINE_AA)
    draw_label(canvas, "TEST TARGET", (x + 42, y - 42), color)


def ai_overlay_point(
    position: dict, calibration: Calibration, frame_shape: Tuple[int, int]
) -> Optional[Tuple[int, int]]:
    """Map a camera-normalized position (0-1) to a projector pixel via calibration.

    Returns None if the position is malformed or calibration is not ready.
    """
    if not calibration.ready or position is None:
        return None
    try:
        cam_h, cam_w = frame_shape[0], frame_shape[1]
        cam_pt = (float(position["x"]) * cam_w, float(position["y"]) * cam_h)
    except (KeyError, TypeError, ValueError):
        return None
    proj = transform_points([cam_pt], calibration.camera_to_projector)[0]
    return int(proj[0]), int(proj[1])


def draw_projector(
    canvas: np.ndarray,
    config: ProjectorConfig,
    active_context: str | None,
    calibration: Calibration,
    markers: Dict[int, np.ndarray],
    pending_cmd: dict | None,
    pulse: float,
    frame_shape: Tuple[int, int] = (720, 1280),
) -> None:
    canvas[:] = 0
    if active_context:
        label = f"[ {active_context.upper()} MODE ]"
        draw_label(canvas, label, (20, 28), (40, 106, 255))
        if calibration.ready:
            anchor = object_anchor(active_context, markers, calibration, config)
            if active_context == "study":
                draw_study_overlay(canvas, anchor, pulse)
            elif active_context == "electronics":
                draw_electronics_overlay(canvas, anchor, pulse)
            elif active_context == "tabletop":
                draw_tabletop_overlay(canvas, anchor, pulse)
    if pending_cmd and pending_cmd.get("position"):
        point = ai_overlay_point(pending_cmd["position"], calibration, frame_shape)
        if point is not None:
            draw_ai_overlay(canvas, point, pulse)


def draw_dashboard(
    frame: np.ndarray,
    markers: Dict[int, np.ndarray],
    show_debug: bool,
    calibration: Calibration | None = None,
    point_enabled: bool = False,
) -> np.ndarray:
    dashboard = frame.copy()
    if show_debug:
        for marker_id, corners in markers.items():
            pts = corners.astype(np.int32)
            color = (0, 255, 0) if marker_id in TABLE_MARKERS else (255, 180, 0)
            cv2.polylines(dashboard, [pts], True, color, 2, cv2.LINE_AA)
            center = marker_center(corners).astype(int)
            label = f"ID {marker_id}"
            if marker_id in OBJECT_MARKERS:
                label += f" {OBJECT_MARKERS[marker_id]}"
            cv2.putText(dashboard, label, tuple(center), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)

    cv2.rectangle(dashboard, (0, 0), (dashboard.shape[1], 56), (5, 8, 14), -1)
    cv2.putText(dashboard, "Projected Copilot", (20, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(dashboard, "space=reveal  d=debug  f=fullscreen  r=reset  p=point  t=test  q=quit", (20, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (170, 220, 255), 1, cv2.LINE_AA)

    # Status strip (top-right): calibration + pointing — so you can see when
    # the 4 table markers are locked and whether 'p' pointing is armed.
    found_table = sum(1 for mid in TABLE_MARKERS if mid in markers)
    ready = calibration is not None and calibration.ready
    if ready:
        cal_text, cal_color = "CALIBRATED", (80, 255, 120)
    else:
        cal_text, cal_color = f"NEED 4 TABLE MARKERS ({found_table}/4)", (60, 160, 255)
    point_text = "POINT: ON" if point_enabled else "POINT: OFF"
    point_color = (80, 255, 120) if point_enabled else (150, 150, 150)
    cv2.putText(dashboard, cal_text, (dashboard.shape[1] - 360, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, cal_color, 2, cv2.LINE_AA)
    cv2.putText(dashboard, point_text, (dashboard.shape[1] - 360, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.55, point_color, 2, cv2.LINE_AA)
    return dashboard


def set_fullscreen(window_name: str, fullscreen: bool) -> None:
    prop = cv2.WINDOW_FULLSCREEN if fullscreen else cv2.WINDOW_NORMAL
    cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, prop)


class MJPEGFrameReader:
    """Read frames from the backend's MJPEG stream instead of opening the camera.

    macOS only lets one process hold a physical camera, so the backend owns it
    (for the web feed) and the projector engine consumes the same frames over
    http://localhost:8000/camera/stream. A daemon thread pulls the multipart
    stream and keeps the latest decoded frame; read() hands back a copy. Drop-in
    for the cv2.VideoCapture API used by main(): read()/release().
    """

    def __init__(self, url: str) -> None:
        self._url = url
        self._latest: Optional[np.ndarray] = None
        self._latest_at = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                resp = _http.get(self._url, stream=True, timeout=10)
                buf = b""
                for chunk in resp.iter_content(chunk_size=8192):
                    if self._stop.is_set():
                        break
                    buf += chunk
                    start = buf.find(b"\xff\xd8")  # JPEG SOI
                    end = buf.find(b"\xff\xd9")     # JPEG EOI
                    if start != -1 and end != -1 and end > start:
                        jpg = buf[start : end + 2]
                        buf = buf[end + 2 :]
                        frame = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
                        if frame is not None:
                            with self._lock:
                                self._latest = frame
                                self._latest_at = time.time()
            except Exception:
                # Backend not up yet or stream dropped — retry shortly.
                time.sleep(1.0)

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        with self._lock:
            if self._latest is None:
                return False, None
            return True, self._latest.copy()

    def read_after(self, ts: float, timeout: float = 1.5) -> Tuple[bool, Optional[np.ndarray]]:
        """Return the first frame decoded after `ts`, or the latest frame on timeout."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if self._latest is not None and self._latest_at > ts:
                    return True, self._latest.copy()
            time.sleep(0.03)
        return self.read()

    def release(self) -> None:
        self._stop.set()


def main() -> int:
    args = parse_args()
    config = ProjectorConfig(width=args.projector_width, height=args.projector_height)

    # The backend owns the physical camera (one process per camera on macOS) and
    # re-serves it as MJPEG. The projector reads that same stream, so both the
    # web feed and the projector see the desk without fighting over the device.
    # Start the backend first. --camera is now only the backend's concern (.env).
    stream_url = os.getenv("CAMERA_STREAM_URL", "http://localhost:8000/camera/stream")
    print(f"Reading camera from backend stream: {stream_url}")
    print("(Backend must be running. Set the camera via CAMERA_INDEX in server/.env.)")
    capture = MJPEGFrameReader(stream_url)

    detector = create_aruco_detector()
    show_debug = True
    fullscreen = not args.windowed
    guidance_pulse_until = 0.0
    point_enabled = False  # toggle with 'p' — ask Claude where to point
    test_point_enabled = False

    simon = SimonRenderer(ASSETS_DIR)
    bubble = SpeechBubble()
    ws_client = ProjectorWSClient()
    glove = GloveInput(enable_ble=os.getenv("GLOVE_BLE", "false").lower() == "true")
    glove.start()
    pending_cmd: dict | None = None
    last_point: dict | None = None
    last_context: str | None = None
    calibration = Calibration()
    last_projector_status: tuple | None = None
    last_projector_status_sent_at = 0.0
    projector_canvas = np.zeros((config.height, config.width, 3), dtype=np.uint8)

    cv2.namedWindow("Projected Copilot - Dashboard", cv2.WINDOW_NORMAL)
    cv2.namedWindow("Projected Copilot - Projector", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Projected Copilot - Projector", config.width, config.height)
    set_fullscreen("Projected Copilot - Projector", fullscreen)

    while True:
        ok, frame = capture.read()
        if not ok:
            # No frame yet — backend still starting or a stream hiccup. Keep the
            # window responsive and wait for the stream rather than exiting.
            if cv2.waitKey(30) & 0xFF in (ord("q"), 27):
                break
            continue

        markers = detect_markers(frame, detector)
        new_cal = calibrate(markers, config)
        if new_cal.ready:
            calibration = new_cal

        gesture = glove.get()
        if gesture:
            active_ctx = next((OBJECT_MARKERS[mid] for mid in OBJECT_MARKERS if mid in markers), None)
            if gesture == "scan":
                request_scan_from_projector(capture, markers, config, active_ctx, point_enabled)
            else:
                _post_gesture(gesture, active_ctx)

        cmd = ws_client.get_command()
        if cmd:
            kind = classify_command(cmd)
            if kind == "ask":
                # Simon immediately speaks — no pending
                bubble.show(cmd.get("guidance", "How can I help you?"))
                guidance_pulse_until = time.time() + 4.0
                simon.set_emotion("dance")
            elif kind == "reveal":
                if pending_cmd:
                    simon.set_emotion(pending_cmd.get("emotion", "dance"))
                    if pending_cmd.get("guidance"):
                        bubble.show(pending_cmd["guidance"])
                        guidance_pulse_until = time.time() + 5.0
                    pending_cmd = None
            elif kind == "scan_request":
                active_ctx = next((OBJECT_MARKERS[mid] for mid in OBJECT_MARKERS if mid in markers), None)
                request_scan_from_projector(capture, markers, config, active_ctx, point_enabled)
            elif kind == "scan_status":
                if cmd.get("scan", {}).get("in_flight"):
                    simon.set_emotion("thinking")
            elif kind == "error":
                pending_cmd = None
                simon.set_emotion("sad")
                bubble.show(cmd.get("message", "Something went wrong."))
                guidance_pulse_until = time.time() + 5.0
            elif kind == "scan":
                # Scan result — store silently, update emotion as a hint
                simon.set_emotion(cmd.get("emotion", "dance"))
                pending_cmd = cmd
                last_point = cmd.get("position")
            # kind == "ignore": context/stop/speak/reset — not for projector

        active = next((OBJECT_MARKERS[mid] for mid in OBJECT_MARKERS if mid in markers), None)
        if active != last_context:
            last_context = active
            _post_context(active)

        found_table = sum(1 for mid in TABLE_MARKERS if mid in markers)
        projector_status = (
            calibration.ready,
            found_table,
            point_enabled,
            test_point_enabled,
            str(last_point),
        )
        now = time.time()
        if projector_status != last_projector_status or now - last_projector_status_sent_at >= 2.0:
            last_projector_status = projector_status
            last_projector_status_sent_at = now
            _post_projector_status(
                {
                    "calibrated": calibration.ready,
                    "table_markers_found": found_table,
                    "point_enabled": point_enabled,
                    "test_point_enabled": test_point_enabled,
                    "last_point": last_point,
                }
            )

        pulse = math.sin(time.time() * 4) * 0.5 + 0.5
        active_pulse = pulse if time.time() < guidance_pulse_until else 0.0
        dashboard = draw_dashboard(frame, markers, show_debug, calibration, point_enabled)
        draw_projector(
            projector_canvas, config, active, calibration, markers,
            pending_cmd, active_pulse, frame.shape[:2],
        )
        if test_point_enabled:
            draw_test_target(projector_canvas, config, pulse)

        simon_x = config.width - SIMON_SIZE - SIMON_MARGIN
        simon_y = config.height - SIMON_SIZE - SIMON_MARGIN
        simon.render(projector_canvas, simon_x, simon_y, SIMON_SIZE)
        bubble.render(projector_canvas, simon_x + SIMON_SIZE // 2, simon_y)

        cv2.imshow("Projected Copilot - Dashboard", dashboard)
        cv2.imshow("Projected Copilot - Projector", projector_canvas)

        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):
            break
        if key == ord(" "):
            if pending_cmd:
                simon.set_emotion(pending_cmd.get("emotion", "dance"))
                if pending_cmd.get("guidance"):
                    bubble.show(pending_cmd["guidance"])
                    guidance_pulse_until = time.time() + 5.0
                pending_cmd = None
        elif key == ord("d"):
            show_debug = not show_debug
        elif key == ord("f"):
            fullscreen = not fullscreen
            set_fullscreen("Projected Copilot - Projector", fullscreen)
        elif key == ord("r"):
            _post_async("/reset", timeout=2)
        elif key == ord("p"):
            point_enabled = not point_enabled
            print(f"Pointing {'ON' if point_enabled else 'OFF'}")
        elif key == ord("t"):
            test_point_enabled = not test_point_enabled
            print(f"Test target {'ON' if test_point_enabled else 'OFF'}")
        # Keyboard stub for glove gestures (until hardware is built)
        _GLOVE_KEYS = {ord("1"): "stop", ord("2"): "ask", ord("3"): "speak", ord("4"): "scan", ord("5"): "reveal"}
        if key in _GLOVE_KEYS:
            glove.simulate(_GLOVE_KEYS[key])

    glove.stop()
    capture.release()
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
