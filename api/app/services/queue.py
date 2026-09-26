from redis import Redis
from rq import Queue

from app.config import Settings


def get_redis_connection(settings: Settings) -> Redis:
    return Redis.from_url(settings.redis_url)


def get_task_queue(settings: Settings) -> Queue:
    return Queue(
        settings.rq_queue_name,
        connection=get_redis_connection(settings),
    )


def enqueue_study_material_run(settings: Settings, production_run_id: str) -> str:
    queue = get_task_queue(settings)
    job = queue.enqueue(
        "app.worker.jobs.generate_study_material",
        production_run_id,
        job_timeout=settings.study_material.job_timeout,
    )
    return job.id


def enqueue_study_material_finalize(settings: Settings, study_material_id: str) -> str:
    queue = get_task_queue(settings)
    job = queue.enqueue(
        "app.worker.jobs.finalize_study_material",
        study_material_id,
        job_timeout=settings.study_material.job_timeout,
    )
    return job.id


def enqueue_production_run(settings: Settings, production_run_id: str) -> str:
    queue = get_task_queue(settings)
    job = queue.enqueue(
        "app.worker.jobs.orchestrate_production_run",
        production_run_id,
        job_timeout=settings.production_run_job_timeout,
    )
    return job.id
