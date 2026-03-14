"""Pipeline Review — card-based job worklist with inline triage actions (D2).

Primary page for reviewing evaluated jobs. Cards show scores, strengths/weaknesses,
and inline Shortlist/Skip buttons. Filters by stage, fit category, sort order, and search.
"""

import logging

import streamlit as st
from sqlalchemy.orm import Session

from jobhunter.dashboard.components.job_card import render_tier2_card, render_tier3_card
from jobhunter.dashboard.components.job_table import paginated_controls
from jobhunter.dashboard.components.status_actions import latest_user_status_subquery
from jobhunter.db.models import MatchEvaluation, ProcessedJob, RawJobPosting, ResumeProfile
from jobhunter.db.session import get_session

logger = logging.getLogger(__name__)

DEFAULT_PAGE_SIZE = 25

_STAGE_OPTIONS = [
    "Needs Review",
    "Show All",
    "All Evaluated",
    "Tier 2 Only",
    "Tier 3 Only",
    "Shortlisted",
    "Skipped",
    "Applied",
]

_FIT_OPTIONS = ["All", "Exceptional", "Strong", "Moderate", "Weak", "Poor"]
_FIT_MAP = {
    "Exceptional": "exceptional_match",
    "Strong": "strong_match",
    "Moderate": "moderate_match",
    "Weak": "weak_match",
    "Poor": "poor_match",
}

_SORT_OPTIONS = ["Score (high to low)", "Score (low to high)", "Newest first", "Company A-Z"]


def _get_page_size() -> int:
    config = st.session_state.get("config")
    if config is not None:
        return int(config.dashboard.page_size)
    return DEFAULT_PAGE_SIZE


def _get_source_options(session: Session) -> list[str]:
    """Query distinct job sources from the database."""
    rows = session.query(RawJobPosting.source).distinct().order_by(RawJobPosting.source).all()
    return [row[0] for row in rows]


def _render_filters(session: Session) -> tuple[str, str, str, str, str]:
    """Render filter controls. Returns (stage, fit, sort, search, source)."""
    sources = _get_source_options(session)
    source_options = ["All Sources"] + sources

    col1, col2, col3, col4, col5 = st.columns([1.5, 1, 1, 1.5, 2])
    with col1:
        stage = st.selectbox("Stage", _STAGE_OPTIONS, key="pr_stage")
    with col2:
        fit = st.selectbox("Fit", _FIT_OPTIONS, key="pr_fit")
    with col3:
        source = st.selectbox("Source", source_options, key="pr_source")
    with col4:
        sort = st.selectbox("Sort", _SORT_OPTIONS, key="pr_sort")
    with col5:
        search = st.text_input("Search title or company", key="pr_search")
    return stage, fit, sort, search, source


def _get_review_jobs(
    session: Session, stage: str, fit: str, sort: str, search: str, source: str = "All Sources"
) -> list[dict]:
    """Query jobs with their best evaluation for the review list.

    Returns a list of dicts with keys: job, raw_job, best_eval, user_status.
    """
    ds7 = latest_user_status_subquery()

    query = (
        session.query(ProcessedJob, RawJobPosting, MatchEvaluation, ds7.c.user_status)
        .join(RawJobPosting, ProcessedJob.raw_id == RawJobPosting.raw_id)
        .outerjoin(
            MatchEvaluation,
            (MatchEvaluation.job_id == ProcessedJob.job_id)
            & (MatchEvaluation.is_current == True),  # noqa: E712
        )
        .outerjoin(ds7, ProcessedJob.job_id == ds7.c.job_id)
    )

    # Stage filter
    if stage == "Needs Review":
        query = query.filter(
            ProcessedJob.status.in_(["tier2_pass", "tier2_maybe", "evaluated"]),
            (ds7.c.user_status.is_(None)) | (ds7.c.user_status.in_(["new", "reviewed"])),
        )
    elif stage == "All Evaluated":
        query = query.filter(
            ProcessedJob.status.in_(["tier2_pass", "tier2_maybe", "tier2_fail", "evaluated"])
        )
    elif stage == "Tier 2 Only":
        query = query.filter(
            ProcessedJob.status.in_(["tier2_pass", "tier2_maybe", "tier2_fail"]),
            MatchEvaluation.tier_evaluated == 2,
        )
    elif stage == "Tier 3 Only":
        query = query.filter(
            ProcessedJob.status == "evaluated",
            MatchEvaluation.tier_evaluated == 3,
        )
    elif stage == "Shortlisted":
        query = query.filter(ds7.c.user_status == "shortlisted")
    elif stage == "Skipped":
        query = query.filter(ds7.c.user_status == "rejected_by_user")
    elif stage == "Applied":
        query = query.filter(ds7.c.user_status == "applied")

    # Fit filter
    if fit != "All" and fit in _FIT_MAP:
        query = query.filter(MatchEvaluation.fit_category == _FIT_MAP[fit])

    # Source filter
    if source != "All Sources":
        query = query.filter(RawJobPosting.source == source)

    # Search filter
    if search.strip():
        pattern = f"%{search.strip()}%"
        query = query.filter(
            (RawJobPosting.title.ilike(pattern)) | (RawJobPosting.company.ilike(pattern))
        )

    # Sort
    if sort == "Score (high to low)":
        query = query.order_by(MatchEvaluation.overall_score.desc().nullslast())
    elif sort == "Score (low to high)":
        query = query.order_by(MatchEvaluation.overall_score.asc().nullslast())
    elif sort == "Newest first":
        query = query.order_by(ProcessedJob.first_seen.desc())
    elif sort == "Company A-Z":
        query = query.order_by(RawJobPosting.company.asc())

    # Deduplicate: pick the best eval per job (highest tier, then highest score)
    # Use distinct on job_id for PostgreSQL
    seen_jobs: set[int] = set()
    results: list[dict] = []
    for job, raw_job, evaluation, user_status in query.all():
        if job.job_id in seen_jobs:
            continue
        seen_jobs.add(job.job_id)
        results.append({
            "job": job,
            "raw_job": raw_job,
            "best_eval": evaluation,
            "user_status": user_status,
        })

    return results


def main() -> None:
    """Pipeline Review page entry point."""
    st.header("Pipeline Review")

    try:
        with get_session() as session:
            stage, fit, sort, search, source = _render_filters(session)

            # Build resume label lookup
            resumes = session.query(ResumeProfile).all()
            resume_map: dict[int, str] = {r.resume_id: r.label for r in resumes}

            jobs = _get_review_jobs(session, stage, fit, sort, search, source)
            total = len(jobs)

            if total == 0:
                if stage == "Needs Review":
                    st.info("No jobs need review. Run the pipeline or change filters.")
                else:
                    st.info("No jobs match your filters.")
                return

            st.caption(f"Showing {total} jobs")

            page_size = _get_page_size()
            offset, limit = paginated_controls(total, page_size, "pr")

            for item in jobs[offset : offset + limit]:
                job: ProcessedJob = item["job"]
                raw_job: RawJobPosting = item["raw_job"]
                best_eval: MatchEvaluation | None = item["best_eval"]
                user_status: str | None = item["user_status"]

                if best_eval is None:
                    # Job with no evaluation — shouldn't normally appear, but handle gracefully
                    with st.container(border=True):
                        st.markdown(f"**{raw_job.title}** @ {raw_job.company}")
                        st.caption(f"Status: {job.status} — not yet evaluated")
                    continue

                if best_eval.tier_evaluated == 3:
                    resume_label = resume_map.get(best_eval.recommended_resume_id or 0)
                    render_tier3_card(job, raw_job, best_eval, resume_label, user_status)
                else:
                    render_tier2_card(job, raw_job, best_eval, user_status)

    except RuntimeError:
        st.warning("Database not initialized. Run `python run.py init-db` first.")


main()
