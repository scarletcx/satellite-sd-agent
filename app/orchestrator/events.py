"""进程内事件总线（SSE 推送，docs/07 §1.6）。单进程演示级。"""
from __future__ import annotations

import asyncio
from collections import defaultdict


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._seq: dict[str, int] = defaultdict(int)

    def subscribe(self, task_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subs[task_id].append(queue)
        return queue

    def unsubscribe(self, task_id: str, queue: asyncio.Queue) -> None:
        subs = self._subs.get(task_id, [])
        if queue in subs:
            subs.remove(queue)

    def publish(self, task_id: str, event: str, data: dict) -> None:
        self._seq[task_id] += 1
        payload = {"id": self._seq[task_id], "event": event, "data": data}
        for queue in list(self._subs.get(task_id, [])):
            queue.put_nowait(payload)


bus = EventBus()
