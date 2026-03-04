"""Filter Results Browser — paginated view of DS10 FilterResult records.

Shows Tier 1 filtering decisions with rule-by-rule breakdowns.
"""

import json
import logging
from datetime import UTC, datetime, timedelta

import streamlit as st
from sqlalchemy import func
from sqlalchemy.orm import Session

from jobhunter.dashboard.components.job_table import paginated_controls
from jobhunter.dashboard.components.status_badge import source_badge
from jobhunter.db.models import FilterResult, RawJobPosting
from jobhunter.db.session import get_session

logger = logging.getLogger(__name__)

PAGE_TITLE = "Filter Results"
DEFAULT_PAGE_SIZE = 25

# Decision display mapping
_DECISION_DISPLAY: dict[str, tuple[str, str]] = {
    "pass": ("✓ Pass", "green"),
    "fail": ("✗ Fail", "red"),
    "ambiguous": ("? Ambiguous", "orange"),
}

_DATE_FILTERS: dict[str, timedelta | None] = {
    "All time": None,
    "Last 24 hours": timedelta(hours=24),
    "Last 7 days": timedelta(days=7),
    "Last 30 days": timedelta(days=30),
}

_DECISION_FILTERS = ["All", "pass", "fail", "ambiguous"]


def _get_page_size() -> int:
    """Read page size from config if available."""
    config = st.session_state.get("config")
    if config is not None:
        page_size: int = config.dashboard.page_size
        return page_size
    return DEFAULT_PAGE_SIZE


def _get_summary_counts(session: Session) -> dict[str, int]:
    """Get counts by decision type."""
    results = (
        session.query(FilterResult.decision, func.count(FilterResult.filter_id))
        .group_by(FilterResult.decision)
        .all()
    )
    counts = {"total": 0, "pass": 0, "fail": 0, "ambiguous": 0}
    for decision, count in results:
        counts[decision] = count
        counts["total"] += count
    return counts


def _build_query(session: Session, decision: str, date_filter: str, search: str):
    """Build filtered query for FilterResult with joined RawJobPosting."""
    query = session.query(FilterResult).join(RawJobPosting)

    if decision != "All":
        query = query.filter(FilterResult.decision == decision)

    delta = _DATE_FILTERS.get(date_filter)
    if delta is not None:
        cutoff = datetime.now(UTC) - delta
        query = query.filter(FilterResult.filtered_at >= cutoff)

    if search.strip():
        pattern = f"%{search.strip()}%"
        query = query.filter(
            (RawJobPosting.title.ilike(pattern)) | (RawJobPosting.company.ilike(pattern))
        )

    return query.order_by(FilterResult.filtered_at.desc())


def _decision_badge(decision: str) -> str:
    """Return styled decision badge."""
    display, _color = _DECISION_DISPLAY.get(decision, ("?", "gray"))
    return display


def _render_summary(counts: dict[str, int]) -> None:
    """Render summary metrics."""
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total", counts["total"])
    with col2:
        st.metric("Passed", counts["pass"])
    with col3:
        st.metric("Failed", counts["fail"])
    with col4:
        st.metric("Ambiguous", counts["ambiguous"])


def _render_filters() -> tuple[str, str, str]:
    """Render filter controls."""
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        decision = st.selectbox("Decision", _DECISION_FILTERS, key="fr_decision")
    with col2:
        date_filter = st.selectbox("Date range", list(_DATE_FILTERS.keys()), key="fr_date")
    with col3:
        search = st.text_input("Search title or company", key="fr_search")
    return decision, date_filter, search


def _render_result_row(result: FilterResult) -> None:
    """Render a single filter result as an expander."""
    raw_job = result.raw_posting
    badge = _decision_badge(result.decision)
    source = source_badge(raw_job.source)

    # Parse rules for display
    rules_failed = json.loads(result.rules_failed) if result.rules_failed else []
    rules_passed = json.loads(result.rules_passed) if result.rules_passed else []

    failed_display = ", ".join(rules_failed) if rules_failed else "—"
    header = f"**{badge}** | {source} | {raw_job.title} @ {raw_job.company} | Failed: {failed_display}"

    with st.expander(header, expanded=False):
        # Basic info
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Decision:** {badge}")
            st.markdown(f"**Filtered at:** {result.filtered_at.strftime('%Y-%m-%d %H:%M')}")
        with col2:
            st.markdown(f"**Source:** {raw_job.source}")
            if raw_job.salary_raw:
                st.markdown(f"**Salary:** {raw_job.salary_raw}")

        # Rules breakdown
        st.markdown("---")
        st.markdown("**Rules Applied:**")

        rules_applied = json.loads(result.rules_applied) if result.rules_applied else []
        rule_details = json.loads(result.rule_details) if result.rule_details else {}

        for rule_name in rules_applied:
            if rule_name in rules_failed:
                icon = "❌"
            elif rule_name in rules_passed:
                icon = "✅"
            else:
                icon = "⚠️"  # Ambiguous

            st.markdown(f"  {icon} **{rule_name}**")

            # Show details if available
            if rule_name in rule_details:
                details = rule_details[rule_name]
                if details:
                    with st.container():
                        st.json(details)

        # Link to source
        if raw_job.source_url:
            st.markdown("---")
            st.markdown(f"[View original posting]({raw_job.source_url})")


def main() -> None:
    """Filter Results page entry point."""
    st.header(PAGE_TITLE)

    try:
        with get_session() as session:
            # Summary metrics
            counts = _get_summary_counts(session)
            _render_summary(counts)

            st.markdown("---")

            # Filters
            decision, date_filter, search = _render_filters()
            query = _build_query(session, decision, date_filter, search)

            total = query.count()
            if total == 0:
                st.info("No filter results found. Run `python run.py filter` to filter jobs.")
                return

            page_size = _get_page_size()
            offset, limit = paginated_controls(total, page_size, "filter_results")

            results = query.offset(offset).limit(limit).all()
            for result in results:
                _render_result_row(result)

    except RuntimeError:
        st.warning("Database not initialized. Run `python run.py init-db` first.")


main()
