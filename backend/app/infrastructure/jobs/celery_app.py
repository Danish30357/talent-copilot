"""
Celery application instance — broker and task configuration.
"""

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "talent_copilot",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    # Serialisation
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Retry policy
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,

    # Result expiry
    result_expires=3600,  # 1 hour

    # Default queue
    task_default_queue="default",

    # Task routes
    task_routes={
        "app.infrastructure.jobs.tasks.ingest_github_repo": {"queue": "ingestion"},
        "app.infrastructure.jobs.tasks.parse_cv_file": {"queue": "parsing"},
        "app.infrastructure.jobs.tasks.save_candidate_profile": {"queue": "default"},
    },
)

# Auto-discover tasks
celery_app.autodiscover_tasks(["app.infrastructure.jobs"])
