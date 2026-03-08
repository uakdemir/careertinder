"""Raw Jobs Browser page — paginated, filterable view of DS1 RawJobPosting records."""

import logging
from datetime import UTC, datetime, timedelta

import streamlit as st
from sqlalchemy.orm import Session

from jobhunter.dashboard.components.job_table import paginated_controls
from jobhunter.dashboard.components.status_badge import source_badge
from jobhunter.db.models import RawJobPosting
from jobhunter.db.session import get_session

logger = logging.getLogger(__name__)

PAGE_TITLE = "Raw Jobs Browser"
DEFAULT_PAGE_SIZE = 25

_DATE_FILTERS: dict[str, timedelta | None] = {
    "All time": None,
    "Last 24 hours": timedelta(hours=24),
    "Last 7 days": timedelta(days=7),
    "Last 30 days": timedelta(days=30),
}

_SOURCES = ["All", "linkedin", "wellfound", "remote_io", "remote_rocketship"]


def _get_page_size() -> int:
    """Read page size from config if available, else use default."""
    config = st.session_state.get("config")
    if config is not None:
        page_size: int = config.dashboard.page_size
        return page_size
    return DEFAULT_PAGE_SIZE


def _build_query(session: Session, source: str, date_filter: str, search: str):
    """Build a filtered SQLAlchemy query for RawJobPosting."""
    query = session.query(RawJobPosting)

    if source != "All":
        query = query.filter(RawJobPosting.source == source)

    delta = _DATE_FILTERS.get(date_filter)
    if delta is not None:
        cutoff = datetime.now(UTC) - delta
        query = query.filter(RawJobPosting.scraped_at >= cutoff)

    if search.strip():
        pattern = f"%{search.strip()}%"
        query = query.filter(
            (RawJobPosting.title.ilike(pattern)) | (RawJobPosting.company.ilike(pattern))
        )

    return query.order_by(RawJobPosting.scraped_at.desc())


def _render_filters() -> tuple[str, str, str]:
    """Render the filter bar. Returns (source, date_filter, search_text)."""
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        source = st.selectbox("Source", _SOURCES, key="rj_source")
    with col2:
        date_filter = st.selectbox("Date range", list(_DATE_FILTERS.keys()), key="rj_date")
    with col3:
        search = st.text_input("Search title or company", key="rj_search")
    return source, date_filter, search


def _render_job_row(job: RawJobPosting) -> None:
    """Render a single job as an expander with detail content."""
    badge = source_badge(job.source)
    salary_display = job.salary_raw or "—"
    header = f"**{badge}** | {job.title} @ {job.company} | {salary_display}"

    with st.expander(header, expanded=False):
        if job.source_url:
            st.markdown(f"**Source URL:** [{job.source_url}]({job.source_url})")
        if job.location_raw:
            st.markdown(f"**Location:** {job.location_raw}")
        st.markdown(f"**Fingerprint:** `{job.fingerprint_hash[:12]}...`")
        st.markdown(f"**Scraped:** {job.scraped_at.strftime('%Y-%m-%d %H:%M')}")

        if job.description:
            st.markdown("---")
            st.markdown("**Description:**")
            st.text_area(
                "Description",
                value=job.description[:5000],
                height=200,
                disabled=True,
                key=f"desc_{job.raw_id}",
                label_visibility="collapsed",
            )

        if job.raw_html:
            if st.checkbox("Show raw HTML", key=f"html_{job.raw_id}"):
                st.code(job.raw_html[:3000], language="html")


def main() -> None:
    """Raw Jobs Browser page entry point."""
    st.header(PAGE_TITLE)

    try:
        with get_session() as session:
            source, date_filter, search = _render_filters()
            query = _build_query(session, source, date_filter, search)

            total = query.count()
            if total == 0:
                st.info("No jobs found matching your filters. Run a scrape to get started.")
                return

            page_size = _get_page_size()
            offset, limit = paginated_controls(total, page_size, "raw_jobs")

            jobs = query.offset(offset).limit(limit).all()
            for job in jobs:
                _render_job_row(job)
    except RuntimeError:
        st.warning("Database not initialized. Run `python run.py init-db` first.")


main()
