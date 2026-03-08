"""Operations — pipeline trigger control panel (D4).

Lets the user trigger scrape, filter, and evaluate from the dashboard.
Each section shows pending item counts and action buttons.
Output is streamed live via subprocess.
"""

import logging

import streamlit as st
from sqlalchemy import func
from sqlalchemy.orm import Session

from jobhunter.dashboard.components.pipeline_runner import run_pipeline_command
from jobhunter.db.models import FilterResult, ProcessedJob, RawJobPosting
from jobhunter.db.session import get_session

logger = logging.getLogger(__name__)


def _get_pending_counts(session: Session) -> dict[str, int]:
    """Get counts of jobs pending each pipeline stage."""
    raw_total = session.query(func.count(RawJobPosting.raw_id)).scalar() or 0

    # Unfiltered = raw jobs that have no FilterResult yet (matches filter service query)
    unfiltered = (
        session.query(func.count(RawJobPosting.raw_id))
        .outerjoin(FilterResult, RawJobPosting.raw_id == FilterResult.raw_id)
        .filter(FilterResult.filter_id.is_(None))
        .scalar()
        or 0
    )

    awaiting_eval = (
        session.query(func.count(ProcessedJob.job_id))
        .filter(ProcessedJob.status.in_(["tier1_pass", "tier1_ambiguous"]))
        .scalar()
        or 0
    )

    awaiting_t3 = (
        session.query(func.count(ProcessedJob.job_id))
        .filter(ProcessedJob.status.in_(["tier2_pass", "tier2_maybe"]))
        .scalar()
        or 0
    )

    return {
        "unfiltered": unfiltered,
        "awaiting_eval": awaiting_eval,
        "awaiting_t3": awaiting_t3,
        "raw_total": raw_total,
    }


def _run_command(args: list[str], label: str) -> None:
    """Execute a pipeline command with spinner and live output."""
    st.session_state["op_running"] = True
    output_placeholder = st.empty()

    with st.spinner(f"Running {label}..."):
        exit_code = run_pipeline_command(args, output_placeholder)

    st.session_state["op_running"] = False

    if exit_code == 0:
        st.success(f"{label} completed successfully.")
    else:
        st.error(f"{label} failed (exit code {exit_code}).")


def _render_scraping_section(session: Session) -> None:
    """Scraping controls."""
    st.subheader("Scraping")

    counts = _get_pending_counts(session)
    st.caption(f"{counts['raw_total']} total raw jobs in database")

    is_running = st.session_state.get("op_running", False)

    col1, col2 = st.columns(2)
    with col1:
        if st.button(
            "Run All Scrapers",
            disabled=is_running,
            use_container_width=True,
            type="primary",
        ):
            _run_command(["scrape"], "Scrape (all)")
    with col2:
        if st.button(
            "LinkedIn Only",
            disabled=is_running,
            use_container_width=True,
        ):
            _run_command(["scrape", "--scraper", "linkedin"], "Scrape (LinkedIn)")


def _render_filtering_section(session: Session) -> None:
    """Filtering controls."""
    st.subheader("Filtering")

    counts = _get_pending_counts(session)
    st.caption(f"{counts['unfiltered']} jobs pending filtering")

    is_running = st.session_state.get("op_running", False)

    col1, col2 = st.columns(2)
    with col1:
        if st.button(
            "Run Filter",
            disabled=is_running,
            use_container_width=True,
            type="primary",
        ):
            _run_command(["filter"], "Filter")
    with col2:
        if st.button(
            "Re-filter All (--force)",
            disabled=is_running,
            use_container_width=True,
        ):
            _run_command(["filter", "--force"], "Re-filter (force)")


def _render_evaluation_section(session: Session) -> None:
    """Evaluation controls."""
    st.subheader("AI Evaluation")

    counts = _get_pending_counts(session)
    st.caption(
        f"{counts['awaiting_eval']} jobs awaiting Tier 2 | "
        f"{counts['awaiting_t3']} awaiting Tier 3"
    )

    is_running = st.session_state.get("op_running", False)

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button(
            "Run Evaluation",
            disabled=is_running,
            use_container_width=True,
            type="primary",
        ):
            _run_command(["evaluate"], "Evaluate (Tier 2 + 3)")
    with col2:
        if st.button(
            "Tier 2 Only",
            disabled=is_running,
            use_container_width=True,
        ):
            _run_command(["evaluate", "--tier2-only"], "Evaluate (Tier 2 only)")
    with col3:
        if st.button(
            "Dry Run",
            disabled=is_running,
            use_container_width=True,
        ):
            _run_command(["evaluate", "--dry-run"], "Evaluate (dry run)")


def _render_generation_section(session: Session) -> None:
    """Content generation controls."""
    st.subheader("Content Generation")

    # Count shortlisted jobs without content
    from sqlalchemy import and_, exists

    from jobhunter.dashboard.components.status_actions import latest_user_status_subquery
    from jobhunter.db.models import CoverLetter, WhyCompany

    latest_ds7 = latest_user_status_subquery()

    shortlisted_count = (
        session.query(func.count(ProcessedJob.job_id))
        .join(latest_ds7, ProcessedJob.job_id == latest_ds7.c.job_id)
        .filter(latest_ds7.c.user_status == "shortlisted")
        .scalar()
        or 0
    )

    # Count those with complete content (both CL and WC active)
    cl_exists = exists().where(
        and_(CoverLetter.job_id == ProcessedJob.job_id, CoverLetter.is_active == True)  # noqa: E712
    )
    wc_exists = exists().where(
        and_(WhyCompany.job_id == ProcessedJob.job_id, WhyCompany.is_active == True)  # noqa: E712
    )
    with_both = (
        session.query(func.count(ProcessedJob.job_id))
        .join(latest_ds7, ProcessedJob.job_id == latest_ds7.c.job_id)
        .filter(latest_ds7.c.user_status == "shortlisted", cl_exists, wc_exists)
        .scalar()
        or 0
    )

    pending = shortlisted_count - with_both
    st.caption(f"{pending} shortlisted jobs pending generation | {with_both} fully generated")

    is_running = st.session_state.get("op_running", False)

    col1, col2 = st.columns(2)
    with col1:
        if st.button(
            "Generate Content",
            disabled=is_running,
            use_container_width=True,
            type="primary",
        ):
            _run_command(["generate"], "Generate Content")
    with col2:
        if st.button(
            "Regenerate All (--force)",
            disabled=is_running,
            use_container_width=True,
        ):
            _run_command(["generate", "--force"], "Regenerate Content (force)")


def _render_full_pipeline_section() -> None:
    """Full pipeline button."""
    st.subheader("Full Pipeline")
    st.caption("Run scrape → filter → evaluate in sequence.")

    is_running = st.session_state.get("op_running", False)
    st.warning("Full pipeline runs all stages sequentially. This may take several minutes.")

    if st.button(
        "Run Full Pipeline",
        disabled=is_running,
        use_container_width=True,
    ):
        for label, args in [
            ("Scrape", ["scrape"]),
            ("Filter", ["filter"]),
            ("Evaluate", ["evaluate"]),
        ]:
            st.markdown(f"**Stage: {label}**")
            _run_command(args, label)


def main() -> None:
    """Operations page entry point."""
    st.header("Operations")

    # Handle preselect from Home quick actions
    preselect = st.session_state.pop("op_preselect", None)
    if preselect:
        st.info(f"Ready to run: **{preselect}**. Click the button below to start.")

    try:
        with get_session() as session:
            _render_scraping_section(session)
            st.divider()
            _render_filtering_section(session)
            st.divider()
            _render_evaluation_section(session)
            st.divider()
            _render_generation_section(session)
            st.divider()
            _render_full_pipeline_section()

    except RuntimeError:
        st.warning("Database not initialized. Run `python run.py init-db` first.")


main()
