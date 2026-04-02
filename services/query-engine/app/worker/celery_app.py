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
    worker_concurrency=1,
    worker_prefetch_multiplier=1,
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
