from __future__ import annotations

import queue
import threading
from typing import Optional

VALID_GESTURES = {"stop", "ask", "speak", "scan", "reveal"}

# BLE identifiers — must match the values in firmware/glove/*.ino
DEVICE_NAME = "ProjectedGlove"
SERVICE_UUID = "a1c00001-5b1e-4b3a-9f00-d3c0ffee0001"
CHAR_UUID = "a1c00002-5b1e-4b3a-9f00-d3c0ffee0002"


class GloveInput:
    """Gesture input from glove hardware (BLE) or keyboard simulation.

    Two backends share one thread-safe queue:
      - Keyboard/test stub: call simulate() to inject a gesture. Always available.
      - BLE (opt-in, enable_ble=True): start() spawns a daemon thread that runs a
        bleak client, connects to the glove, subscribes to the gesture
        characteristic, and enqueues each notified gesture name.

    get() is non-blocking and identical for both backends, so app.py never needs
    to know which one is active.
    """

    def __init__(
        self,
        enable_ble: bool = False,
        device_name: str = DEVICE_NAME,
        char_uuid: str = CHAR_UUID,
    ) -> None:
        self._queue: queue.Queue[str] = queue.Queue()
        self._enable_ble = enable_ble
        self._device_name = device_name
        self._char_uuid = char_uuid
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Begin the BLE backend if enabled. No-op in stub mode."""
        if not self._enable_ble or self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_ble, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signal the BLE thread to disconnect and exit. No-op in stub mode."""
        self._stop_event.set()

    def simulate(self, gesture: str) -> None:
        """Inject a gesture directly (keyboard stub / tests)."""
        self._enqueue(gesture)

    def get(self) -> Optional[str]:
        """Return the next queued gesture name, or None if none pending."""
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    # --- internals ---------------------------------------------------------

    def _enqueue(self, gesture: str) -> None:
        if gesture in VALID_GESTURES:
            self._queue.put(gesture)

    def _run_ble(self) -> None:
        # bleak is imported lazily so the module (and the test suite) load
        # without it installed — only the BLE backend requires it.
        import asyncio

        try:
            import bleak  # noqa: F401
        except ImportError:
            print(
                "[glove] bleak not installed — glove disabled, keyboard 1-5 still works.\n"
                "        Install it with: pip install bleak"
            )
            return

        asyncio.run(self._ble_loop())

    async def _ble_loop(self) -> None:
        from bleak import BleakClient, BleakScanner

        import asyncio

        print(f"[glove] scanning for '{self._device_name}' over Bluetooth…")
        while not self._stop_event.is_set():
            try:
                device = await BleakScanner.find_device_by_name(
                    self._device_name, timeout=10.0
                )
                if device is None:
                    print("[glove] not found, still scanning… (is it powered on?)")
                    continue  # keep scanning until the glove powers on / comes in range

                def _on_notify(_sender, data: bytearray) -> None:
                    self._enqueue(data.decode("utf-8", errors="ignore").strip())

                async with BleakClient(device) as client:
                    await client.start_notify(self._char_uuid, _on_notify)
                    print("[glove] connected ✓  make a gesture to test")
                    while client.is_connected and not self._stop_event.is_set():
                        await asyncio.sleep(0.2)
                print("[glove] disconnected, retrying…")
            except Exception as exc:
                # Disconnects, timeouts, adapter hiccups: wait briefly and retry.
                print(f"[glove] connection error ({exc}), retrying…")
                await asyncio.sleep(2.0)
