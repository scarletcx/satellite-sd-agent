"""在任意上下文调度异步任务（API 事件循环内或线程池同步调用均可）。"""
from __future__ import annotations

import asyncio
import threading
from typing import Callable, Coroutine, Any


def schedule(factory: Callable[[], Coroutine[Any, Any, Any]]) -> None:
    """有运行中的事件循环 → create_task；否则起后台线程跑 asyncio.run。"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None and loop.is_running():
        loop.create_task(factory())
        return

    def runner() -> None:
        asyncio.run(factory())

    threading.Thread(target=runner, daemon=True).start()
