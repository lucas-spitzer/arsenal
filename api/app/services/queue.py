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


def enqueue_knowledge_run(settings: Settings, production_run_id: str, job: str) -> str:
    names = {
        "structure": "app.worker.jobs.structure_knowledge",
        "draft": "app.worker.jobs.draft_knowledge",
        "attach": "app.worker.jobs.attach_knowledge_visuals",
    }
    try:
        function_name = names[job]
    except KeyError as exc:
        raise ValueError(f"Unknown knowledge job {job}.") from exc
    queue = get_task_queue(settings)
    queued = queue.enqueue(
        function_name,
        production_run_id,
        job_timeout=settings.production_run_job_timeout,
    )
    return queued.id


def enqueue_production_run(settings: Settings, production_run_id: str) -> str:
    queue = get_task_queue(settings)
    job = queue.enqueue(
        "app.worker.jobs.orchestrate_production_run",
        production_run_id,
        job_timeout=settings.production_run_job_timeout,
    )
    return job.id


def cancel_queued_jobs_for_run(settings: Settings, production_run_id: str) -> None:
    """Drop queued jobs whose first argument is this production run.

    A job already executing keeps running until it next loads the run.
    """
    queue = get_task_queue(settings)
    for job in list(queue.jobs):
        args = job.args or ()
        if args and str(args[0]) == production_run_id:
            job.cancel()
