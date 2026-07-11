from __future__ import annotations

import asyncio
import logging
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)


async def auto_watch_loop(
    capture_fn: Callable[[], bytes],
    analyze_fn: Callable[[bytes], Awaitable[dict]],
    broadcast_fn: Callable[[dict], Awaitable[None]],
    interval: float = 5.0,
) -> None:
    """Poll camera every `interval` seconds and broadcast Claude analysis."""
    while True:
        await asyncio.sleep(interval)
        try:
            jpeg = capture_fn()
            result = await analyze_fn(jpeg)
            await broadcast_fn(result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Auto-watch error: %s", exc)
