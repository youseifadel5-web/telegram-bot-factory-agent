"""Simple priority async job queue — limits concurrent heavy work."""
from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, Optional, Dict
from enum import IntEnum

logger = logging.getLogger(__name__)


class Priority(IntEnum):
    LOW = 10
    NORMAL = 5
    HIGH = 1  # admin
    CRITICAL = 0


@dataclass(order=True)
class Job:
    priority: int
    created: float = field(compare=True)
    job_id: str = field(compare=False)
    coro_factory: Callable[[], Awaitable[Any]] = field(compare=False, repr=False)
    name: str = field(compare=False, default="")
    user_id: int = field(compare=False, default=0)


class TaskQueue:
    def __init__(self, max_concurrent: int = 2, name: str = "default"):
        self.max_concurrent = max_concurrent
        self.name = name
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._workers: list = []
        self._running = False
        self._active = 0
        self._done = 0
        self._failed = 0
        self._lock = asyncio.Lock()

    async def start(self, n_workers: int = None):
        if self._running:
            return
        self._running = True
        n = n_workers or self.max_concurrent
        for i in range(n):
            self._workers.append(asyncio.create_task(self._worker(i)))
        logger.info("Queue[%s] started with %s workers", self.name, n)

    async def stop(self):
        self._running = False
        for w in self._workers:
            w.cancel()
        self._workers.clear()

    async def submit(
        self,
        coro_factory: Callable[[], Awaitable[Any]],
        *,
        name: str = "",
        user_id: int = 0,
        priority: Priority = Priority.NORMAL,
        is_admin: bool = False,
    ) -> str:
        if is_admin:
            priority = Priority.HIGH
        job_id = f"{self.name}-{int(time.time() * 1000)}-{self._done + self._active}"
        job = Job(
            priority=int(priority),
            created=time.time(),
            job_id=job_id,
            coro_factory=coro_factory,
            name=name or job_id,
            user_id=user_id,
        )
        await self._queue.put(job)
        logger.info("Queue[%s] submitted %s prio=%s", self.name, job.name, priority)
        return job_id

    async def _worker(self, wid: int):
        while self._running:
            try:
                job: Job = await self._queue.get()
            except asyncio.CancelledError:
                break
            self._active += 1
            try:
                await job.coro_factory()
                self._done += 1
            except Exception as e:
                self._failed += 1
                logger.exception("Queue[%s] job %s failed: %s", self.name, job.name, e)
            finally:
                self._active -= 1
                self._queue.task_done()

    def stats(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "active": self._active,
            "queued": self._queue.qsize(),
            "done": self._done,
            "failed": self._failed,
            "max_concurrent": self.max_concurrent,
        }


# Global queues
upload_queue = TaskQueue(max_concurrent=2, name="upload")
stream_queue = TaskQueue(max_concurrent=1, name="stream")


async def start_queues():
    await upload_queue.start()
    await stream_queue.start()


async def stop_queues():
    await upload_queue.stop()
    await stream_queue.stop()
