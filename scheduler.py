"""
APScheduler-based periodic job that sends the business-health WhatsApp
survey to every registered loan, on an interval controlled entirely by
the SURVEY_INTERVAL_MINUTES environment variable (no hardcoded interval).

This lets the "3 months in production" concept be compressed down to a
few minutes for a live hackathon demo.
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app import health_checks

logger = logging.getLogger("scheduler")

JOB_ID = "periodic_survey_broadcast"

_scheduler: BackgroundScheduler | None = None


def _broadcast_surveys_job() -> None:
    """Send the survey to every loan currently in the database."""
    loans = health_checks.list_all_loans()
    for loan in loans:
        try:
            health_checks.send_survey(loan["loan_id"])
        except Exception:  # noqa: BLE001 - keep the scheduler alive even if one send fails
            logger.exception("Failed to send periodic survey for loan %s", loan["loan_id"])
    logger.info("Periodic survey broadcast complete for %d loan(s).", len(loans))


def start_scheduler() -> BackgroundScheduler:
    """
    Start (or return the already-running) background scheduler.
    Guards against duplicate job registration if called more than once.
    """
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        logger.info("Scheduler already running - skipping duplicate start.")
        return _scheduler

    _scheduler = BackgroundScheduler(timezone="UTC")

    if _scheduler.get_job(JOB_ID) is None:
        _scheduler.add_job(
            _broadcast_surveys_job,
            trigger="interval",
            minutes=settings.SURVEY_INTERVAL_MINUTES,
            id=JOB_ID,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )

    _scheduler.start()
    logger.info(
        "Scheduler started. Survey broadcast will run every %s minute(s).",
        settings.SURVEY_INTERVAL_MINUTES,
    )
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down.")
    _scheduler = None


def get_scheduler() -> BackgroundScheduler | None:
    return _scheduler
