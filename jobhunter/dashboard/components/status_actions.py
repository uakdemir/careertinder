"""DS7 ApplicationStatus transition helpers.

Provides functions for creating status records and querying current user status.
ProcessedJob.status tracks pipeline stages; DS7 tracks user actions (shortlist/skip/apply).
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from jobhunter.db.models import ApplicationStatus

logger = logging.getLogger(__name__)


def transition_job_status(
    session: Session,
    job_id: int,
    new_status: str,
    notes: str | None = None,
) -> None:
    """Create a DS7 ApplicationStatus record for a job status transition.

    Args:
        session: DB session
        job_id: The job to transition
        new_status: Target status (e.g., 'shortlisted', 'rejected_by_user', 'applied')
        notes: Optional free-text notes
    """
    status_record = ApplicationStatus(
        job_id=job_id,
        status=new_status,
        notes=notes,
        updated_by="user",
    )
    session.add(status_record)
    session.flush()
    logger.info("Job %d status → %s", job_id, new_status)


def get_current_status(session: Session, job_id: int) -> str | None:
    """Get the most recent DS7 status for a job, or None if no status exists."""
    latest = (
        session.query(ApplicationStatus)
        .filter_by(job_id=job_id)
        .order_by(ApplicationStatus.status_id.desc())
        .first()
    )
    return latest.status if latest else None


def latest_user_status_subquery():
    """Subquery returning the latest DS7 status per job_id.

    Returns a subquery with columns: job_id, user_status.
    Usage: left-join to this subquery to get current user status per job.

    Uses DISTINCT ON (PostgreSQL) to efficiently pick the latest record per job.
    """
    return (
        select(
            ApplicationStatus.job_id,
            ApplicationStatus.status.label("user_status"),
        )
        .distinct(ApplicationStatus.job_id)
        .order_by(ApplicationStatus.job_id, ApplicationStatus.status_id.desc())
        .subquery("latest_ds7")
    )
