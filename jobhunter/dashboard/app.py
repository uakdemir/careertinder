"""JobHunter Dashboard — Streamlit entry point.

Launch: streamlit run jobhunter/dashboard/app.py
"""

import logging
from datetime import UTC, datetime
from pathlib import Path

import streamlit as st
from sqlalchemy import func
from sqlalchemy.orm import Session

from jobhunter.config.loader import load_config
from jobhunter.config.schema import ConfigurationError
from jobhunter.db.session import create_engine

logger = logging.getLogger(__name__)


def _init_db() -> None:
    """Initialize DB engine and config on first run."""
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


# ---------------------------------------------------------------------------
# D1: Funnel Home Page
# ---------------------------------------------------------------------------


def _get_funnel_counts(session: Session) -> dict[str, int]:
    """Query pipeline stage counts from ProcessedJob.status + DS7."""
    from jobhunter.dashboard.components.status_actions import latest_user_status_subquery
    from jobhunter.db.models import ProcessedJob, RawJobPosting

    scraped = session.query(func.count(RawJobPosting.raw_id)).scalar() or 0

    filtered = (
        session.query(func.count(ProcessedJob.job_id))
        .filter(ProcessedJob.status != "new")
        .scalar()
        or 0
    )

    evaluated = (
        session.query(func.count(ProcessedJob.job_id))
        .filter(ProcessedJob.status == "evaluated")
        .scalar()
        or 0
    )

    # Shortlisted / Applied from DS7
    ds7 = latest_user_status_subquery()
    shortlisted = (
        session.query(func.count(ds7.c.job_id))
        .filter(ds7.c.user_status == "shortlisted")
        .scalar()
        or 0
    )
    applied = (
        session.query(func.count(ds7.c.job_id))
        .filter(ds7.c.user_status == "applied")
        .scalar()
        or 0
    )

    return {
        "scraped": scraped,
        "filtered": filtered,
        "evaluated": evaluated,
        "shortlisted": shortlisted,
        "applied": applied,
    }


def _get_attention_items(session: Session) -> list[dict[str, str]]:
    """Identify items needing user attention."""
    from jobhunter.dashboard.components.status_actions import latest_user_status_subquery
    from jobhunter.db.models import (
        MatchEvaluation,
        ProcessedJob,
        RawJobPosting,
        ResumeProfile,
    )
    from jobhunter.db.settings import get_ai_cost_config

    items: list[dict[str, str]] = []

    # 1. Unfiltered raw jobs (those without a FilterResult)
    from jobhunter.db.models import FilterResult

    unfiltered = (
        session.query(func.count(RawJobPosting.raw_id))
        .outerjoin(FilterResult, RawJobPosting.raw_id == FilterResult.raw_id)
        .filter(FilterResult.filter_id.is_(None))
        .scalar()
        or 0
    )
    if unfiltered > 0:
        items.append({
            "icon": "warning",
            "message": f"{unfiltered} new jobs need filtering",
            "priority": "high",
        })

    # 2. Filtered jobs awaiting evaluation
    awaiting_eval = (
        session.query(func.count(ProcessedJob.job_id))
        .filter(ProcessedJob.status.in_(["tier1_pass", "tier1_ambiguous"]))
        .scalar()
        or 0
    )
    if awaiting_eval > 0:
        items.append({
            "icon": "warning",
            "message": f"{awaiting_eval} filtered jobs awaiting AI evaluation",
            "priority": "high",
        })

    # 3. Evaluated jobs not yet reviewed
    ds7 = latest_user_status_subquery()
    needs_review = (
        session.query(func.count(ProcessedJob.job_id))
        .outerjoin(ds7, ProcessedJob.job_id == ds7.c.job_id)
        .filter(
            ProcessedJob.status == "evaluated",
            (ds7.c.user_status.is_(None)) | (ds7.c.user_status.in_(["new", "reviewed"])),
        )
        .scalar()
        or 0
    )
    if needs_review > 0:
        items.append({
            "icon": "star",
            "message": f"{needs_review} evaluated jobs need your review",
            "priority": "high",
        })

    # 4. Cost cap check
    cost_config = get_ai_cost_config(session)
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    today_spend = (
        session.query(func.coalesce(func.sum(MatchEvaluation.cost_usd), 0.0))
        .filter(MatchEvaluation.evaluated_at >= today_start)
        .scalar()
    ) or 0.0

    if cost_config.daily_cap_usd > 0:
        pct = today_spend / cost_config.daily_cap_usd
        if pct >= 1.0:
            items.append({
                "icon": "error",
                "message": "Daily AI cost cap reached — evaluation paused",
                "priority": "high",
            })
        elif pct >= cost_config.warn_at_percent:
            remaining = cost_config.daily_cap_usd - today_spend
            items.append({
                "icon": "info",
                "message": f"AI budget at {pct:.0%} — ${remaining:.2f} remaining today",
                "priority": "medium",
            })

    # 5. No resumes
    resume_count = session.query(func.count(ResumeProfile.resume_id)).scalar() or 0
    if resume_count == 0:
        items.append({
            "icon": "warning",
            "message": "No resumes found — upload resumes before running evaluation",
            "priority": "high",
        })

    return items


def _render_funnel(counts: dict[str, int]) -> None:
    """Render the 5-stage funnel with st.columns and st.metric."""
    st.subheader("Pipeline Funnel")

    stages = [
        ("Scraped", counts["scraped"], "total"),
        ("Filtered", counts["filtered"], "passed T1"),
        ("Evaluated", counts["evaluated"], "scored"),
        ("Shortlisted", counts["shortlisted"], "saved"),
        ("Applied", counts["applied"], "done"),
    ]

    cols = st.columns(len(stages))
    for col, (label, value, subtitle) in zip(cols, stages, strict=True):
        col.metric(label, value, help=subtitle)

    # Conversion bar
    if counts["scraped"] > 0:
        pcts = [
            counts["scraped"] / counts["scraped"],
            counts["filtered"] / counts["scraped"],
            counts["evaluated"] / counts["scraped"],
            counts["shortlisted"] / counts["scraped"],
            counts["applied"] / counts["scraped"],
        ]
        labels = ["Scraped", "Filtered", "Evaluated", "Shortlisted", "Applied"]
        bar_text = "  ".join(
            f"{lbl}: {pct:.0%}" for lbl, pct in zip(labels, pcts, strict=True)
        )
        st.caption(bar_text)


def _render_attention(items: list[dict[str, str]]) -> None:
    """Render 'Needs Attention' section."""
    if not items:
        st.success("All clear — no items need attention.")
        return

    st.subheader("Needs Attention")
    for item in items:
        icon = item["icon"]
        msg = item["message"]
        if icon == "error":
            st.error(msg)
        elif icon == "warning":
            st.warning(msg)
        elif icon == "star":
            st.info(msg)
        else:
            st.info(msg)


def _render_quick_actions() -> None:
    """Render quick action buttons that deep-link to Operations page."""
    st.subheader("Quick Actions")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Run Scrape", use_container_width=True):
            st.session_state["op_preselect"] = "scrape"
            st.switch_page("pages/3_operations.py")
    with col2:
        if st.button("Run Filter", use_container_width=True):
            st.session_state["op_preselect"] = "filter"
            st.switch_page("pages/3_operations.py")
    with col3:
        if st.button("Run AI Evaluation", use_container_width=True):
            st.session_state["op_preselect"] = "evaluate"
            st.switch_page("pages/3_operations.py")


def _render_recent_activity(session: Session) -> None:
    """Show recent scraper runs and daily AI spend."""
    from jobhunter.dashboard.components.formatting import format_relative_time
    from jobhunter.db.models import ScraperRun

    st.subheader("Recent Activity")

    runs = (
        session.query(ScraperRun)
        .order_by(ScraperRun.run_id.desc())
        .limit(5)
        .all()
    )

    if not runs:
        st.caption("No scraper runs yet.")
        return

    for run in runs:
        when = format_relative_time(run.started_at)
        status_icon = {"success": "OK", "failed": "FAIL", "running": "..."}.get(
            run.status, run.status
        )
        st.caption(
            f"{when} — {run.scraper_name}: {run.jobs_new} new jobs ({status_icon})"
        )


def home_page() -> None:
    """Home page — pipeline funnel dashboard."""
    from jobhunter.db.session import get_session

    st.title("JobHunter Dashboard")

    try:
        with get_session() as session:
            counts = _get_funnel_counts(session)
            _render_funnel(counts)

            st.divider()

            attention = _get_attention_items(session)
            _render_attention(attention)

            st.divider()

            _render_quick_actions()

            st.divider()

            _render_recent_activity(session)
    except RuntimeError:
        st.warning("Database not initialized. Run `python run.py init-db` first.")


# --- App setup (runs on every Streamlit rerun) ---

st.set_page_config(
    page_title="JobHunter",
    page_icon=":briefcase:",
    layout="wide",
    initial_sidebar_state="expanded",
)

_init_db()

pg = st.navigation(
    {
        "": [
            st.Page(home_page, title="Home", icon=":material/home:", default=True),
        ],
        "Pipeline": [
            st.Page("pages/1_pipeline_review.py", title="Pipeline Review", icon=":material/view_list:"),
            st.Page("pages/2_job_detail.py", title="Job Detail", icon=":material/search:"),
            st.Page("pages/3_operations.py", title="Operations", icon=":material/play_circle:"),
            st.Page("pages/12_ready_to_apply.py", title="Ready to Apply", icon=":material/send:"),
            st.Page("pages/13_applied_jobs.py", title="Applied Jobs", icon=":material/check_circle:"),
        ],
        "Configure": [
            st.Page("pages/4_resume_management.py", title="Resumes", icon=":material/description:"),
            st.Page("pages/5_scraper_config.py", title="Scraper Config", icon=":material/language:"),
            st.Page("pages/6_filter_config.py", title="Filter Rules", icon=":material/filter_alt:"),
            st.Page("pages/7_ai_settings.py", title="AI Settings", icon=":material/smart_toy:"),
        ],
        "History": [
            st.Page("pages/8_scraper_runs.py", title="Scraper Runs", icon=":material/history:"),
            st.Page("pages/9_filter_results.py", title="Filter Results", icon=":material/checklist:"),
            st.Page("pages/10_evaluations.py", title="Evaluation Log", icon=":material/analytics:"),
            st.Page("pages/11_raw_jobs.py", title="Raw Jobs", icon=":material/database:"),
        ],
    }
)

pg.run()
