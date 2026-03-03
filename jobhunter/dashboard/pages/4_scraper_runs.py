"""Scraper Runs page — audit trail + trigger scrape action (D5+D6)."""

import asyncio
import logging
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import streamlit as st
from sqlalchemy.orm import Session

from jobhunter.dashboard.components.status_badge import source_badge, status_badge
from jobhunter.db.models import ScraperRun
from jobhunter.db.session import get_session

logger = logging.getLogger(__name__)

PAGE_TITLE = "Scraper Runs"

# Threshold in seconds for detecting stale "running" records
_STALE_THRESHOLD_SECONDS = 3600


def _format_relative_time(dt: datetime | None) -> str:
    """Format a datetime as a relative time string."""
    if dt is None:
        return "—"
    now = datetime.now(UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    diff = now - dt
    seconds = int(diff.total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def _get_running_scrapers(session: Session) -> list[ScraperRun]:
    """Return all ScraperRun records with status='running'."""
    return (
        session.query(ScraperRun)
        .filter(ScraperRun.status == "running")
        .all()
    )


def _is_stale(run: ScraperRun) -> bool:
    """Check if a 'running' record is stale (started > threshold ago)."""
    if run.started_at is None:
        return True
    started = run.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    elapsed = (datetime.now(UTC) - started).total_seconds()
    return elapsed > _STALE_THRESHOLD_SECONDS


def _run_scraper_in_thread(scraper_name: str | None) -> None:
    """Entry point for background scraper thread.

    Creates its own DB session and event loop. Runs the orchestrator.
    scraper_name=None means run all enabled scrapers.
    """
    from jobhunter.config.loader import load_config, load_secrets
    from jobhunter.db.session import get_session as get_thread_session
    from jobhunter.db.settings import get_scraping_config
    from jobhunter.scrapers.orchestrator import ScraperOrchestrator

    try:
        config = load_config(Path("config.yaml"))
        secrets = load_secrets()

        with get_thread_session() as session:
            # Load scraping config from DB (overrides YAML)
            db_scraping = get_scraping_config(session)
            config = config.model_copy(update={"scraping": db_scraping})

            orchestrator = ScraperOrchestrator(config, secrets, session)

            if scraper_name is None:
                asyncio.run(orchestrator.run_all())
            else:
                asyncio.run(orchestrator.run_single(scraper_name))
    except Exception:
        logger.exception("Background scraper thread failed")


def _render_trigger_section(session: Session) -> bool:
    """Render the trigger scrape controls. Returns True if jobs are active (needs polling)."""
    st.subheader("Run Scraper")
    running = _get_running_scrapers(session)

    # Detect stale jobs
    for run in running:
        if _is_stale(run):
            st.warning(
                f"Stale running job detected: **{run.scraper_name}** "
                f"(started {_format_relative_time(run.started_at)})"
            )
            if st.button(f"Mark #{run.run_id} as failed", key=f"stale_{run.run_id}"):
                run.status = "failed"
                run.error_message = "Marked as failed (stale) by user"
                run.completed_at = datetime.now(UTC)
                session.flush()
                st.rerun()

    # Show active jobs
    active_names = {r.scraper_name for r in running if not _is_stale(r)}
    if active_names:
        st.info("Active scrapers: " + ", ".join(f"**{n}**" for n in sorted(active_names)))

    scraper_options = ["All enabled", "linkedin", "wellfound", "remote_io", "remote_rocketship"]
    col1, col2 = st.columns([2, 1])
    with col1:
        selected = st.selectbox("Scraper", scraper_options, key="trigger_scraper")
    with col2:
        st.markdown("")  # spacing
        st.markdown("")
        start_disabled = False
        if selected == "All enabled":
            start_disabled = len(active_names) > 0
        else:
            start_disabled = selected in active_names

        if st.button(
            "Start Scrape",
            type="primary",
            key="start_scrape",
            disabled=start_disabled,
        ):
            target_name = None if selected == "All enabled" else selected
            thread = threading.Thread(
                target=_run_scraper_in_thread,
                args=(target_name,),
                daemon=True,
            )
            thread.start()
            st.success(f"Scrape started: **{selected}**")
            time.sleep(1)  # brief pause to let the thread create the run record
            st.rerun()

    if start_disabled and active_names:
        st.caption("Cannot start — a scraper is already running.")

    return len(active_names) > 0


def _render_runs_table(session: Session) -> None:
    """Render the paginated scraper runs table."""
    st.subheader("Run History")

    runs = (
        session.query(ScraperRun)
        .order_by(ScraperRun.run_id.desc())
        .limit(50)
        .all()
    )

    if not runs:
        st.info("No scraper runs yet. Start a scrape to see results here.")
        return

    for run in runs:
        badge = status_badge(run.status)
        scraper = source_badge(run.scraper_name)
        duration = f"{run.duration_seconds:.1f}s" if run.duration_seconds else "—"
        when = _format_relative_time(run.started_at)

        header = (
            f"#{run.run_id} | {scraper} | {badge} | "
            f"Found: {run.jobs_found} | New: {run.jobs_new} | "
            f"{duration} | {when}"
        )

        with st.expander(header, expanded=(run.status in ("failed", "running"))):
            st.markdown(f"**Scraper:** {run.scraper_name}")
            st.markdown(f"**Status:** {badge}")
            if run.started_at:
                st.markdown(f"**Started:** {run.started_at.strftime('%Y-%m-%d %H:%M:%S')}")
            if run.completed_at:
                st.markdown(f"**Completed:** {run.completed_at.strftime('%Y-%m-%d %H:%M:%S')}")
            if run.duration_seconds:
                st.markdown(f"**Duration:** {run.duration_seconds:.1f}s")

            st.markdown(f"**Jobs found:** {run.jobs_found} | **New:** {run.jobs_new} | **Updated:** {run.jobs_updated}")

            if run.error_message:
                st.error(f"**Error:** {run.error_message}")
            if run.error_traceback:
                with st.expander("Traceback", expanded=False):
                    st.code(run.error_traceback, language="python")


def main() -> None:
    """Scraper Runs page entry point."""
    st.header(PAGE_TITLE)

    try:
        with get_session() as session:
            has_active = _render_trigger_section(session)
            st.divider()
            _render_runs_table(session)

        # Auto-refresh while jobs are active
        if has_active:
            time.sleep(5)
            st.rerun()
    except RuntimeError:
        st.warning("Database not initialized. Run `python run.py init-db` first.")


main()
