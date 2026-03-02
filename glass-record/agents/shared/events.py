"""
Shared in-process event bus for SSE streaming.

Both the Editor and Researcher agents (running as subgraphs in the same
Cloud Run instance) import from here so they share one subscriber registry.

For multi-instance Cloud Run deployments (paid tier), replace the Queue-based
bus with a Pub/Sub push to a streaming sidecar.
"""
import asyncio
import datetime
import json
from collections import defaultdict
from typing import AsyncIterator

# journalist_id → list of active subscriber queues
_subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)


def emit(journalist_id: str, event_type: str, data: dict) -> None:
    """Push a cycle event to all active SSE subscribers for this journalist."""
    payload = {
        "event": event_type,
        "data": data,
        "ts": datetime.datetime.utcnow().isoformat(),
    }
    dead: list[asyncio.Queue] = []
    for q in _subscribers[journalist_id]:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _subscribers[journalist_id].remove(q)


async def subscribe(journalist_id: str) -> AsyncIterator[str]:
    """
    Async generator yielding SSE-formatted strings for a journalist's events.
    A heartbeat comment is sent every 15 s to keep the connection alive.
    """
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    _subscribers[journalist_id].append(q)
    try:
        while True:
            try:
                payload = await asyncio.wait_for(q.get(), timeout=15.0)
                yield f"data: {json.dumps(payload)}\n\n"
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"
    finally:
        try:
            _subscribers[journalist_id].remove(q)
        except ValueError:
            pass
