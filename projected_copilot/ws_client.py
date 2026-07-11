from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
from typing import Optional

import websockets

logger = logging.getLogger(__name__)


class ProjectorWSClient:
    def __init__(self, uri: str = "ws://localhost:8000/ws/projector") -> None:
        self._uri = uri
        # Queue, not a single slot: frequent broadcasts (e.g. projector_status
        # echoes) must not overwrite a scan result before the app polls it.
        self._commands: queue.Queue[dict] = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def get_command(self) -> Optional[dict]:
        try:
            return self._commands.get_nowait()
        except queue.Empty:
            return None

    def _run(self) -> None:
        asyncio.run(self._connect())

    async def _connect(self) -> None:
        while True:
            try:
                async with websockets.connect(self._uri) as ws:
                    logger.info("Projector WS connected to %s", self._uri)
                    async for message in ws:
                        try:
                            self._commands.put(json.loads(message))
                        except json.JSONDecodeError:
                            pass
            except Exception as exc:
                logger.debug("WS connection failed (%s), retrying in 2s", exc)
                await asyncio.sleep(2)
