"""Periodic check for finished export jobs nobody has downloaded yet.

Complements ExportSettings.cleanup_mode (see app/services/export_job_service.py):
in TIME_BASED mode this is the early warning before an undownloaded job
gets auto-deleted; in AFTER_DOWNLOAD mode there's no scheduled deletion at
all to warn ahead of, so this is the *only* thing that ever surfaces a
forgotten export in that mode.

Off by default (warn_undownloaded_after_hours is None until an admin sets
one via PUT /api/export-settings) -- a fresh deployment shouldn't start
generating anomalies for a check nobody asked for.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.insights.base import Anomaly, AnomalySeverity
from app.models.anomaly_event import AnomalyEvent
from app.models.db import AsyncSessionLocal
from app.models.export_job import ExportJob, ExportJobStatus
from app.services import export_settings_service, insights_service
from app.services.alerting import maybe_alert
from app.services.interval_job import IntervalJob

logger = logging.getLogger(__name__)

ANOMALY_TITLE = "Export not downloaded"

# Once flagged, the same job won't be flagged again for this long -- an
# hourly check would otherwise re-warn about the same still-undownloaded
# job every single hour, which is noise, not a reminder.
_RE_FLAG_COOLDOWN_HOURS = 24


class UndownloadedExportMonitorJob(IntervalJob):
    job_name = "undownloaded-export-monitor"
    failure_source_tag = "undownloaded_export_monitor"
    failure_log_message = "Undownloaded-export check failed; will retry next interval"

    def __init__(self, interval_seconds: int = 3600) -> None:
        super().__init__(interval_seconds)

    async def run(self) -> None:
        now = datetime.now(UTC)

        async with AsyncSessionLocal() as session:
            settings_row = await export_settings_service.get_settings_row(session)
            warn_after_hours = settings_row.warn_undownloaded_after_hours
            if not warn_after_hours or warn_after_hours <= 0:
                return

            cutoff = now - timedelta(hours=warn_after_hours)
            candidates = (
                await session.execute(
                    select(ExportJob).where(
                        ExportJob.status == ExportJobStatus.DONE,
                        ExportJob.downloaded_at.is_(None),
                        ExportJob.created_at <= cutoff,
                    )
                )
            ).scalars().all()
            if not candidates:
                return

            anomalies: list[Anomaly] = []
            for job in candidates:
                if await self._recently_flagged(session, job.id, now):
                    continue
                age_hours = (now - job.created_at).total_seconds() / 3600
                anomalies.append(
                    Anomaly(
                        title=ANOMALY_TITLE,
                        description=(
                            f"Export job {job.id} ({job.format}, {job.since.isoformat()} to "
                            f"{job.until.isoformat()}) finished {age_hours:.0f}h ago and has never "
                            f"been downloaded (threshold: {warn_after_hours}h)."
                        ),
                        severity=AnomalySeverity.LOW,
                        branch=job.branch,
                        generated_at=now,
                    )
                )

            if not anomalies:
                return

            rows = insights_service.persist(session, anomalies)
            await session.commit()

        for row in rows:
            await maybe_alert(row)

    async def _recently_flagged(self, session: AsyncSession, job_id: str, now: datetime) -> bool:
        cutoff = now - timedelta(hours=_RE_FLAG_COOLDOWN_HOURS)
        existing = (
            await session.execute(
                select(AnomalyEvent.id)
                .where(
                    AnomalyEvent.title == ANOMALY_TITLE,
                    AnomalyEvent.description.contains(f"Export job {job_id} "),
                    AnomalyEvent.generated_at >= cutoff,
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        return existing is not None
