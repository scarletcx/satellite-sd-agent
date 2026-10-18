"""进程内事件总线（SSE 推送，docs/07 §1.6）。单进程演示级。

保留每任务最近 HISTORY_LIMIT 条事件，支持按 Last-Event-ID 断线重放（前端重连不丢不重）。
"""
from __future__ import annotations

import asyncio
from collections import defaultdict

HISTORY_LIMIT = 500


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._seq: dict[str, int] = defaultdict(int)
        self._history: dict[str, list[dict]] = defaultdict(list)

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
        history = self._history[task_id]
        history.append(payload)
        if len(history) > HISTORY_LIMIT:
            del history[:-HISTORY_LIMIT]
        for queue in list(self._subs.get(task_id, [])):
            queue.put_nowait(payload)

    def history_since(self, task_id: str, last_event_id: int) -> list[dict]:
        """断线重放：返回 id 大于 last_event_id 的历史事件（顺序与发布一致）。"""
        return [item for item in self._history.get(task_id, []) if item["id"] > last_event_id]

    def forget(self, task_id: str) -> None:
        """任务删除时清理内存事件，避免任务号复用后重放旧事件。"""
        self._history.pop(task_id, None)
        self._seq.pop(task_id, None)


bus = EventBus()
