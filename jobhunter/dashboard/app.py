"""JobHunter Dashboard — Streamlit entry point.

Launch: streamlit run jobhunter/dashboard/app.py
"""

import logging
from datetime import UTC, datetime
from pathlib import Path

import streamlit as st

from jobhunter.config.loader import load_config
from jobhunter.config.schema import ConfigurationError
from jobhunter.db.models import RawJobPosting, ResumeProfile, ScraperRun
from jobhunter.db.session import create_engine, get_session

logger = logging.getLogger(__name__)


def init_app() -> None:
    """Initialize Streamlit app: page config, DB engine, sidebar status."""
    st.set_page_config(
        page_title="JobHunter",
        page_icon=":briefcase:",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    if "db_initialized" not in st.session_state:
        try:
            config = load_config(Path("config.yaml"))
        except ConfigurationError as e:
            st.error(f"Configuration error: {e}")
            st.stop()
            return

        create_engine(config.database)
        st.session_state.config = config
        st.session_state.db_initialized = True


def _render_sidebar_status() -> None:
    """Render status indicators in the sidebar."""
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Status**")
    try:
        with get_session() as session:
            job_count = session.query(RawJobPosting).count()
            run_count = session.query(ScraperRun).count()
            resume_count = session.query(ResumeProfile).count()

            last_run = (
                session.query(ScraperRun)
                .order_by(ScraperRun.run_id.desc())
                .first()
            )
            last_scrape_text = _format_relative_time(last_run.started_at) if last_run else "Never"

        st.sidebar.markdown("DB: Connected")
        st.sidebar.markdown(f"Jobs: **{job_count}**")
        st.sidebar.markdown(f"Resumes: **{resume_count}**")
        st.sidebar.markdown(f"Runs: **{run_count}**")
        st.sidebar.markdown(f"Last scrape: {last_scrape_text}")
    except RuntimeError:
        st.sidebar.markdown("DB: Not initialized")


def _format_relative_time(dt: datetime | None) -> str:
    """Format a datetime as a human-readable relative time string."""
    if dt is None:
        return "Never"
    now = datetime.now(UTC)
    # Handle naive datetimes from SQLite
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    diff = now - dt
    seconds = int(diff.total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        minutes = seconds // 60
        return f"{minutes}m ago"
    if seconds < 86400:
        hours = seconds // 3600
        return f"{hours}h ago"
    days = seconds // 86400
    return f"{days}d ago"


def main() -> None:
    """Main dashboard entry point — renders the Home page."""
    init_app()

    st.title("JobHunter Dashboard")
    st.markdown("Job Search Automation Platform")

    # Summary metrics
    try:
        with get_session() as session:
            raw_count = session.query(RawJobPosting).count()
            run_count = session.query(ScraperRun).count()
            resume_count = session.query(ResumeProfile).count()
    except RuntimeError:
        st.warning("Database not initialized. Run `python run.py init-db` first.")
        return

    cols = st.columns(3)
    cols[0].metric("Raw Jobs", raw_count)
    cols[1].metric("Scraper Runs", run_count)
    cols[2].metric("Resumes", resume_count)

    # Sidebar status
    _render_sidebar_status()


if __name__ == "__main__":
    main()
