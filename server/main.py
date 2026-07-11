from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
from typing import List

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from server.camera import Camera, mjpeg_generator
from server.claude_client import MODEL, analyze_desk, reset_history
from server.auto_watch import auto_watch_loop

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "1"))
AUTO_WATCH = os.getenv("AUTO_WATCH", "false").lower() == "true"

camera: Camera | None = None
camera_error: str | None = None
projector_connections: List[WebSocket] = []
web_connections: List[WebSocket] = []
state = {"emotion": "dance", "last_guidance": "", "calibrated": False, "mode": None}
scan_state = {
    "phase": "idle",
    "message": "Ready",
    "in_flight": False,
    "last_error": None,
    "point_requested": False,
    "point_returned": False,
    "point_warning": None,
}
projector_state = {
    "calibrated": False,
    "table_markers_found": 0,
    "point_enabled": False,
    "test_point_enabled": False,
    "last_point": None,
}


def _set_scan_state(
    phase: str,
    message: str,
    *,
    in_flight: bool = False,
    error: str | None = None,
    point_requested: bool = False,
    point_returned: bool = False,
    point_warning: str | None = None,
) -> None:
    scan_state.update(
        {
            "phase": phase,
            "message": message,
            "in_flight": in_flight,
            "last_error": error,
            "point_requested": point_requested,
            "point_returned": point_returned,
            "point_warning": point_warning,
        }
    )


def _finish_scan_state(result: dict, want_position: bool) -> None:
    point_returned = bool(result.get("position"))
    point_warning = (
        "Claude did not return a point."
        if want_position and not point_returned
        else None
    )
    _set_scan_state(
        "answer-ready",
        "Answer ready - no point" if point_warning else "Answer ready",
        point_requested=want_position,
        point_returned=point_returned,
        point_warning=point_warning,
    )


def _set_projector_state(
    *,
    calibrated: bool,
    table_markers_found: int,
    point_enabled: bool,
    test_point_enabled: bool,
    last_point: dict | None,
) -> None:
    found = max(0, min(4, int(table_markers_found)))
    projector_state.update(
        {
            "calibrated": calibrated,
            "table_markers_found": found,
            "point_enabled": point_enabled,
            "test_point_enabled": test_point_enabled,
            "last_point": last_point,
        }
    )
    state["calibrated"] = calibrated


def current_status() -> dict:
    pointing = {
        **projector_state,
        "ready": bool(projector_state["calibrated"] and projector_state["point_enabled"]),
    }
    return {
        **state,
        "auto_watch": AUTO_WATCH,
        "camera": {
            "ready": camera is not None and camera_error is None,
            "index": CAMERA_INDEX,
            "error": camera_error,
        },
        "claude": {
            "configured": bool(os.getenv("ANTHROPIC_API_KEY")),
            "model": MODEL,
        },
        "connections": {
            "projector": len(projector_connections),
            "web": len(web_connections),
        },
        "scan": scan_state.copy(),
        "pointing": pointing,
    }


def _remove_connection(ws_list: List[WebSocket], ws: WebSocket) -> None:
    # Both broadcast() and the disconnect handlers may try to remove the same
    # socket — the second attempt must not raise.
    if ws in ws_list:
        ws_list.remove(ws)


async def broadcast(data: dict) -> None:
    state["emotion"] = data.get("emotion", state["emotion"])
    if "guidance" in data:
        state["last_guidance"] = data.get("guidance") or ""
    if data.get("action") == "context":
        state["mode"] = data.get("mode")
    payload = json.dumps(data)
    for ws_list in (projector_connections, web_connections):
        dead = []
        for ws in ws_list:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            try:
                await ws.close()
            except Exception:
                pass
            _remove_connection(ws_list, ws)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global camera, camera_error
    try:
        camera = Camera(index=CAMERA_INDEX)
        camera_error = None
    except Exception as exc:
        camera = None
        camera_error = str(exc)
        logger.error("Camera unavailable: %s", exc)
    if AUTO_WATCH:
        if camera:
            asyncio.create_task(
                auto_watch_loop(
                    capture_fn=camera.capture_jpeg,
                    analyze_fn=analyze_desk,
                    broadcast_fn=broadcast,
                    interval=5.0,
                )
            )
        else:
            logger.warning("AUTO_WATCH disabled because camera is unavailable")
    yield
    if camera:
        camera.release()


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/camera/stream")
async def camera_stream():
    if not camera:
        return StreamingResponse(iter([]), media_type="text/plain")
    return StreamingResponse(
        mjpeg_generator(camera),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/status")
async def status():
    return current_status()


class AskRequest(BaseModel):
    question: str


@app.post("/reveal")
async def reveal():
    await broadcast({"action": "reveal"})
    return {"ok": True}


@app.post("/reset")
async def reset_memory():
    reset_history()
    _set_scan_state("idle", "Ready")
    await broadcast({"action": "reset"})
    return {"ok": True}


@app.post("/scan")
async def scan(request: Request):
    # Claim in_flight before the first await so two concurrent scans can't
    # both pass the check.
    if scan_state["in_flight"]:
        return {"error": "scan already in progress", "scan": scan_state.copy()}
    _set_scan_state("thinking", "Analyzing desk", in_flight=True)
    jpeg = await request.body()
    if not jpeg:
        _set_scan_state("failed", "No image provided", error="no image provided")
        await broadcast({"action": "error", "message": "No scan image was provided."})
        return {"error": "no image provided"}
    context = request.headers.get("X-Context") or None
    want_position = request.headers.get("X-Point", "").lower() == "true"
    await broadcast({"action": "scan_status", "scan": scan_state.copy()})
    try:
        result = await analyze_desk(jpeg, marker_context=context, want_position=want_position)
    except Exception as exc:
        logger.exception("Scan failed")
        _set_scan_state("failed", "Scan failed", error=str(exc))
        await broadcast({"action": "error", "message": "Scan failed. Check the backend logs."})
        return {"error": "scan failed", "detail": str(exc), "scan": scan_state.copy()}
    _finish_scan_state(result, want_position=want_position)
    await broadcast(result)
    return result


@app.post("/scan/request")
async def request_projector_scan():
    if scan_state["in_flight"]:
        return {"error": "scan already in progress", "scan": scan_state.copy()}
    await broadcast({"action": "scan_request"})
    return {"ok": True}


class ContextRequest(BaseModel):
    mode: str | None = None


@app.post("/context")
async def context_update(body: ContextRequest):
    await broadcast({"action": "context", "mode": body.mode})
    return {"ok": True}


class ProjectorStatusRequest(BaseModel):
    calibrated: bool = False
    table_markers_found: int = 0
    point_enabled: bool = False
    test_point_enabled: bool = False
    last_point: dict | None = None


@app.post("/projector/status")
async def projector_status_update(body: ProjectorStatusRequest):
    _set_projector_state(
        calibrated=body.calibrated,
        table_markers_found=body.table_markers_found,
        point_enabled=body.point_enabled,
        test_point_enabled=body.test_point_enabled,
        last_point=body.last_point,
    )
    await broadcast({"action": "projector_status", "pointing": current_status()["pointing"]})
    return {"ok": True}


class GestureRequest(BaseModel):
    type: str
    marker_context: str | None = None


@app.post("/gesture")
async def gesture_event(body: GestureRequest):
    if body.type == "stop":
        await broadcast({"action": "stop"})
    elif body.type == "speak":
        await broadcast({"action": "speak"})
    elif body.type == "ask":
        await broadcast({"action": "ask", "guidance": "How can I help you?"})
    elif body.type == "scan":
        pass  # scan now handled by /scan — app.py sends pre-masked frame
    elif body.type == "reveal":
        await broadcast({"action": "reveal"})
    return {"ok": True}


@app.post("/ask")
async def ask(body: AskRequest):
    if scan_state["in_flight"]:
        return {"error": "scan already in progress", "scan": scan_state.copy()}
    if not camera:
        _set_scan_state("failed", "Camera not ready", error=camera_error or "camera not ready")
        await broadcast({"action": "error", "message": "Camera is not ready."})
        return {"error": "camera not ready"}
    try:
        jpeg = camera.capture_jpeg()
    except Exception as exc:
        logger.exception("Camera capture failed")
        _set_scan_state("failed", "Camera capture failed", error=str(exc))
        await broadcast({"action": "error", "message": "Camera capture failed."})
        return {"error": "camera capture failed", "detail": str(exc), "scan": scan_state.copy()}
    _set_scan_state("thinking", "Answering question", in_flight=True)
    await broadcast({"action": "scan_status", "scan": scan_state.copy()})
    try:
        result = await analyze_desk(jpeg, question=body.question)
    except Exception as exc:
        logger.exception("Ask failed")
        _set_scan_state("failed", "Ask failed", error=str(exc))
        await broadcast({"action": "error", "message": "Question failed. Check the backend logs."})
        return {"error": "ask failed", "detail": str(exc), "scan": scan_state.copy()}
    _finish_scan_state(result, want_position=False)
    await broadcast(result)
    return result


@app.websocket("/ws/projector")
async def projector_ws(websocket: WebSocket):
    await websocket.accept()
    projector_connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _remove_connection(projector_connections, websocket)


@app.websocket("/ws/web")
async def web_ws(websocket: WebSocket):
    await websocket.accept()
    web_connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _remove_connection(web_connections, websocket)
