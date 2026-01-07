"""
Scheduler Service for running background jobs.

Uses APScheduler for cron-like scheduling of automated tasks
such as the daily intervention check.
"""

import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.database import AsyncSessionLocal


logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = AsyncIOScheduler()


async def run_daily_intervention_check():
    """
    Daily job to run intervention checks at midnight.

    This job:
    1. Gets all active intervention thresholds
    2. Checks all active students against those thresholds
    3. Creates alerts for students meeting intervention criteria
    4. Notifies teachers of new alerts
    5. Logs results to audit trail
    """
    logger.info(f"[Scheduler] Starting daily intervention check at {datetime.now()}")

    try:
        async with AsyncSessionLocal() as db:
            from app.services.intervention_service import InterventionService

            service = InterventionService(db)
            alerts = await service.run_intervention_check()

            logger.info(
                f"[Scheduler] Intervention check complete. "
                f"Created {len(alerts)} new alerts."
            )

            # Log to audit trail
            try:
                from app.services.audit_service import AuditService
                from app.models.intervention import AuditAction

                audit_service = AuditService(db)
                await audit_service.create_audit_log(
                    user_id=None,  # System-generated
                    action=AuditAction.CREATE,
                    entity_type="scheduled_job",
                    entity_id="daily_intervention_check",
                    entity_name="Daily Intervention Check",
                    description=f"Scheduled intervention check created {len(alerts)} new alerts",
                    new_values={
                        "alerts_created": len(alerts),
                        "alert_ids": [str(a.id) for a in alerts] if alerts else [],
                        "run_time": datetime.now().isoformat()
                    }
                )
            except Exception as audit_error:
                logger.warning(f"[Scheduler] Failed to log audit entry: {str(audit_error)}")

            return len(alerts)

    except Exception as e:
        logger.error(f"[Scheduler] Error in daily intervention check: {str(e)}")
        raise


def init_scheduler():
    """
    Initialize the scheduler with all scheduled jobs.

    Jobs:
    - Daily intervention check at midnight (Europe/London timezone)
    """
    # Daily intervention check at midnight UK time
    scheduler.add_job(
        run_daily_intervention_check,
        CronTrigger(hour=0, minute=0, timezone='Europe/London'),
        id='daily_intervention_check',
        name='Daily Intervention Check',
        replace_existing=True,
        misfire_grace_time=3600  # Allow up to 1 hour misfire grace
    )

    scheduler.start()
    logger.info(
        "[Scheduler] Initialized with daily intervention check at midnight (Europe/London)"
    )


def shutdown_scheduler():
    """Shutdown the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Shutdown complete")


def get_scheduler_status() -> dict:
    """
    Get the current status of the scheduler and its jobs.

    Returns:
        Dictionary with scheduler status and job information
    """
    jobs = scheduler.get_jobs()
    return {
        "running": scheduler.running,
        "jobs": [
            {
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger)
            }
            for job in jobs
        ]
    }
