"""
In-process event bus for streaming cycle events to SSE subscribers.

Architecture:
- Each journalist has a list of asyncio.Queue instances (one per SSE subscriber).
- Agent nodes call emit() as they run. The SSE endpoint drains the queues.
- This is process-local: works for Cloud Run with a single active cycle per instance.
  For multi-instance deployments, replace with a Pub/Sub push to a streaming service.
"""
import asyncio
import datetime
import json
from collections import defaultdict
from typing import AsyncIterator

# journalist_id → list of subscriber queues
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
    Async generator that yields SSE-formatted strings for a journalist's events.
    Yields a heartbeat comment every 15 s to keep the connection alive through
    proxies and load balancers.
    """
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    _subscribers[journalist_id].append(q)
    try:
        while True:
            try:
                payload = await asyncio.wait_for(q.get(), timeout=15.0)
                yield f"data: {json.dumps(payload)}\n\n"
            except asyncio.TimeoutError:
                # Heartbeat — keeps the connection alive
                yield ": heartbeat\n\n"
    finally:
        try:
            _subscribers[journalist_id].remove(q)
        except ValueError:
            pass
