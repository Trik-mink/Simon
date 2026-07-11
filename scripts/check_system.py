from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_URL = os.getenv("PROJECTED_COPILOT_BACKEND", "http://127.0.0.1:8000")


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def check(label: str, ok: bool, detail: str, *, warn: bool = False) -> bool:
    if ok:
        status = "WARN" if warn else "PASS"
    else:
        status = "FAIL"
    print(f"[{status}] {label}: {detail}")
    return ok or warn


def fetch_status() -> tuple[dict | None, str | None]:
    try:
        with urllib.request.urlopen(f"{BACKEND_URL}/status", timeout=2) as response:
            return json.loads(response.read().decode("utf-8")), None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return None, str(exc)


def main() -> int:
    failures = 0

    env_path = ROOT / "server" / ".env"
    env = read_env(env_path)
    failures += not check("server/.env", env_path.exists(), str(env_path))

    api_key = env.get("ANTHROPIC_API_KEY", "")
    failures += not check(
        "Anthropic key",
        bool(api_key and api_key != "your_key_here" and not api_key.endswith("your-key...")),
        "configured" if api_key else "missing ANTHROPIC_API_KEY",
    )

    camera_index = env.get("CAMERA_INDEX")
    failures += not check(
        "Camera index",
        camera_index is not None,
        f"CAMERA_INDEX={camera_index}" if camera_index is not None else "missing CAMERA_INDEX",
    )

    failures += not check(
        "Web dependencies",
        (ROOT / "web" / "node_modules").exists(),
        "installed" if (ROOT / "web" / "node_modules").exists() else "run npm install in web/",
    )

    failures += not check(
        "Markers sheet",
        (ROOT / "markers" / "markers_sheet.png").exists(),
        "markers/markers_sheet.png",
    )

    status, error = fetch_status()
    failures += not check(
        "Backend /status",
        status is not None,
        "reachable" if status is not None else f"unreachable at {BACKEND_URL} ({error})",
    )

    if status:
        camera = status.get("camera", {})
        claude = status.get("claude", {})
        connections = status.get("connections", {})
        pointing = status.get("pointing", {})

        failures += not check(
            "Backend camera",
            bool(camera.get("ready")),
            f"index {camera.get('index')}" if camera.get("ready") else camera.get("error") or "not ready",
        )
        failures += not check(
            "Backend Claude",
            bool(claude.get("configured")),
            claude.get("model", "not configured"),
        )
        check(
            "Projector link",
            bool(connections.get("projector")),
            f"{connections.get('projector', 0)} projector connection(s)",
            warn=True,
        )
        check(
            "Pointing",
            bool(pointing.get("ready")),
            "ready" if pointing.get("ready") else f"{pointing.get('table_markers_found', 0)}/4 markers, point {'on' if pointing.get('point_enabled') else 'off'}",
            warn=True,
        )

    if failures:
        print(f"\nSystem check failed: {failures} required check(s) need attention.")
        return 1

    print("\nSystem check passed. Warnings may still need attention before a real scan.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
