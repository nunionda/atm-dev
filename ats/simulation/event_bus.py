"""
SSE 이벤트 버스: asyncio.Queue 기반 fan-out 패턴.
각 SSE 클라이언트는 자신만의 Queue를 할당받아 이벤트를 비동기로 수신한다.
"""

import asyncio
import json
from typing import Any, Dict, Set
from datetime import datetime


class SSEEventBus:

    def __init__(self):
        self._queues: Set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue):
        self._queues.discard(queue)

    async def publish(self, event_type: str, data: Any):
        message: Dict[str, Any] = {
            "event": event_type,
            "data": data,
            "timestamp": datetime.now().isoformat(),
        }
        dead_queues = []
        for queue in self._queues:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                    queue.put_nowait(message)
                except Exception:
                    dead_queues.append(queue)
        for q in dead_queues:
            self._queues.discard(q)

    @property
    def client_count(self) -> int:
        return len(self._queues)
