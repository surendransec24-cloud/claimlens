"""
Simple in-memory SSE event bus for pipeline status streaming.
Each case_id maps to a list of asyncio.Queue objects (one per SSE connection).
"""
import asyncio
from collections import defaultdict
from typing import Dict, List

# case_id -> list of queues (one per connected SSE client)
_subscribers: Dict[str, List[asyncio.Queue]] = defaultdict(list)


def subscribe(case_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    _subscribers[case_id].append(q)
    return q


def unsubscribe(case_id: str, q: asyncio.Queue) -> None:
    try:
        _subscribers[case_id].remove(q)
    except ValueError:
        pass
    if not _subscribers[case_id]:
        del _subscribers[case_id]


async def publish(case_id: str, event: dict) -> None:
    """Publish an event to all SSE clients watching this case."""
    dead = []
    for q in _subscribers.get(case_id, []):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        unsubscribe(case_id, q)

