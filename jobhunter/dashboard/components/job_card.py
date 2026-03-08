"""Reusable job card component for Pipeline Review and other pages."""

import json

import streamlit as st

from jobhunter.dashboard.components.score_display import (
    fit_category_label,
    score_color,
)
from jobhunter.dashboard.components.status_badge import source_badge
from jobhunter.db.models import MatchEvaluation, ProcessedJob, RawJobPosting


def _format_salary(job: ProcessedJob) -> str:
    """Format salary range for display."""
    if job.salary_min and job.salary_max:
        return f"${job.salary_min:,}–${job.salary_max:,}"
    elif job.salary_min:
        return f"${job.salary_min:,}+"
    elif job.salary_max:
        return f"Up to ${job.salary_max:,}"
    return "Salary N/A"


def _format_location(job: ProcessedJob) -> str:
    """Format location policy for display."""
    labels = {
        "remote_worldwide": "Remote Worldwide",
        "remote_regional": "Remote Regional",
        "remote_country_specific": "Remote (Country)",
        "hybrid": "Hybrid",
        "onsite": "On-site",
        "unclear": "Location unclear",
    }
    return labels.get(job.location_policy, job.location_policy)


def render_tier3_card(
    job: ProcessedJob,
    raw_job: RawJobPosting,
    best_eval: MatchEvaluation,
    resume_label: str | None,
    current_status: str | None,
) -> None:
    """Render a job card for a Tier 3 evaluated job."""
    score = best_eval.overall_score or 0
    color = score_color(score)
    fit = fit_category_label(best_eval.fit_category)
    source = source_badge(raw_job.source)
    salary = _format_salary(job)
    location = _format_location(job)

    # Status badge
    status_prefix = ""
    if current_status == "shortlisted":
        status_prefix = "**[SHORTLISTED]** "
    elif current_status == "rejected_by_user":
        status_prefix = "~~SKIPPED~~ "
    elif current_status == "applied":
        status_prefix = "**[APPLIED]** "

    # Card header
    header = (
        f"{status_prefix}"
        f"**:{color}[{score}]** | {fit} | {source} | "
        f"{raw_job.title} @ {raw_job.company}"
    )

    with st.container(border=True):
        st.markdown(header)
        st.caption(f"{resume_label or '—'} | {location} | {salary}")

        # Score bars
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            _score_bar("Skills", best_eval.skill_match_score)
        with col2:
            _score_bar("Seniority", best_eval.seniority_match_score)
        with col3:
            _score_bar("Remote", best_eval.remote_compatibility_score)
        with col4:
            _score_bar("Salary", best_eval.salary_alignment_score)

        # Strengths / Weaknesses
        strengths = json.loads(best_eval.strengths) if best_eval.strengths else []
        weaknesses = json.loads(best_eval.weaknesses) if best_eval.weaknesses else []
        hints = []
        for s in strengths[:2]:
            hints.append(f"+ {s}")
        for w in weaknesses[:2]:
            hints.append(f"- {w}")
        if hints:
            st.caption("  |  ".join(hints))

        # Action buttons
        _render_card_actions(job.job_id, current_status)


def render_tier2_card(
    job: ProcessedJob,
    raw_job: RawJobPosting,
    best_eval: MatchEvaluation,
    current_status: str | None,
) -> None:
    """Render a job card for a Tier 2 only job (no deep eval)."""
    decision_map = {"yes": "PASS", "no": "FAIL", "maybe": "MAYBE"}
    decision = decision_map.get(best_eval.decision or "", best_eval.decision or "?")
    confidence = best_eval.confidence or 0.0
    source = source_badge(raw_job.source)
    salary = _format_salary(job)
    location = _format_location(job)

    with st.container(border=True):
        st.markdown(
            f"**{decision}** ({confidence:.0%}) | {source} | "
            f"{raw_job.title} @ {raw_job.company}"
        )
        st.caption(f"Tier 2 only | {location} | {salary}")

        if best_eval.reasoning:
            st.caption(f'"{best_eval.reasoning}"')

        _render_card_actions(job.job_id, current_status)


def _score_bar(label: str, score: int | None) -> None:
    """Render a labeled score with color."""
    if score is None:
        st.markdown(f"**{label}:** —")
        return
    color = score_color(score)
    st.markdown(f"**{label}:** :{color}[{score}]")


def _render_card_actions(job_id: int, current_status: str | None) -> None:
    """Render Details / Shortlist / Skip action buttons."""
    from jobhunter.dashboard.components.status_actions import (
        transition_job_status,
    )
    from jobhunter.db.session import get_session

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Details", key=f"detail_{job_id}", use_container_width=True):
            st.session_state["detail_job_id"] = job_id
            st.switch_page("pages/2_job_detail.py")

    with col2:
        if current_status == "shortlisted":
            if st.button("Remove Shortlist", key=f"unshort_{job_id}", use_container_width=True):
                with get_session() as session:
                    transition_job_status(session, job_id, "reviewed")
                st.rerun()
        else:
            if st.button("Shortlist", key=f"short_{job_id}", type="primary", use_container_width=True):
                with get_session() as session:
                    transition_job_status(session, job_id, "shortlisted")
                st.rerun()

    with col3:
        if current_status == "rejected_by_user":
            if st.button("Undo Skip", key=f"unskip_{job_id}", use_container_width=True):
                with get_session() as session:
                    transition_job_status(session, job_id, "reviewed")
                st.rerun()
        else:
            if st.button("Skip", key=f"skip_{job_id}", use_container_width=True):
                with get_session() as session:
                    transition_job_status(session, job_id, "rejected_by_user")
                st.rerun()
