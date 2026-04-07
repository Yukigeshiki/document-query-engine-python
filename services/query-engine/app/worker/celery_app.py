"""Celery application instance and configuration."""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "agent_query_engine",
    broker=settings.celery_broker_url,
    backend=settings.celery_broker_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=86400,  # 24 hours
    task_track_started=True,
    # Prefork pool (Celery default on Unix). Each worker process has its own
    # KG service, Neo4j driver, postgres engine, GCS client, and LlamaIndex
    # indexes — process isolation makes the lazy singletons safe and avoids
    # races in LlamaIndex internals. Scale horizontally by running more worker
    # containers.
    worker_concurrency=settings.celery_worker_concurrency,
    worker_prefetch_multiplier=1,  # fair distribution for long-running tasks
    worker_max_tasks_per_child=settings.worker_max_tasks_per_child,  # recycle to bound memory leaks
    task_acks_late=True,  # redeliver task if worker crashes mid-execution
    task_reject_on_worker_lost=True,  # pairs with acks_late for crash recovery
    task_soft_time_limit=180,  # 3 minutes
    task_time_limit=240,  # 4 minutes
    beat_schedule={
        "cleanup-uploads-daily": {
            "task": "cleanup_uploads",
            "schedule": crontab(hour=3, minute=0),
        },
    },
)

celery_app.autodiscover_tasks(["app.worker"])
