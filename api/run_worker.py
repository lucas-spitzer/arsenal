#!/usr/bin/env python3
"""Start the Arsenal RQ worker."""

import os

# macOS's Objective-C runtime (pulled in via SSL/httpx when calling Supabase and
# OpenAI) is not safe to use after fork(). The default RQ worker forks a
# work-horse per job, so the child crashes with signal 6 before the pipeline can
# run. Disabling the fork-safety guard is a belt-and-suspenders for any code path
# that still forks; the SimpleWorker below avoids forking entirely on macOS.
os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")

import sys

from redis import Redis
from rq import Queue, SimpleWorker, Worker

from app.config import get_settings
from app.logging_config import configure_logging


def main() -> None:
    configure_logging()
    settings = get_settings()
    redis_conn = Redis.from_url(settings.redis_url)
    queues = [Queue(settings.rq_queue_name, connection=redis_conn)]

    # SimpleWorker runs each job inside the worker process (no fork), which is
    # reliable for local single-user development on macOS. On Linux we keep the
    # default forking Worker for per-job process isolation.
    worker_cls = SimpleWorker if sys.platform == "darwin" else Worker
    worker = worker_cls(queues, connection=redis_conn)
    # The scheduler runs jobs queued with enqueue_at, such as narration that
    # paused on a provider quota.
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
