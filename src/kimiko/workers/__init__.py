"""Background workers — Celery tasks for async embedding and memory jobs.

Broker: Redis (Fix #8 review round 2).
"""

from __future__ import annotations

from celery import Celery

from kimiko.config import get_settings

settings = get_settings()

# ── Celery App ──
celery_app = Celery(
    "kimiko",
    broker=settings.celery_broker_url,
    backend=settings.celery_broker_url,  # Results also in Redis
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minute max per task
    worker_prefetch_multiplier=1,
)
