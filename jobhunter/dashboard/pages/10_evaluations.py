"""Evaluation Results Browser — Tier 2 + Tier 3 AI evaluation results.

Shows scored jobs with fit categories, resume recommendations, and detailed breakdowns.
"""

import json
import logging

import streamlit as st
from sqlalchemy import func
from sqlalchemy.orm import Session

from jobhunter.dashboard.components.job_table import paginated_controls
from jobhunter.dashboard.components.status_badge import source_badge
from jobhunter.db.models import MatchEvaluation, ProcessedJob, RawJobPosting, ResumeProfile
from jobhunter.db.session import get_session

logger = logging.getLogger(__name__)

PAGE_TITLE = "Evaluation Results"
DEFAULT_PAGE_SIZE = 25

_FIT_CATEGORY_DISPLAY: dict[str, tuple[str, str]] = {
    "exceptional_match": ("Exceptional", "green"),
    "strong_match": ("Strong", "green"),
    "moderate_match": ("Moderate", "orange"),
    "weak_match": ("Weak", "red"),
    "poor_match": ("Poor", "red"),
}

_TIER_FILTERS = ["All", "Tier 2", "Tier 3"]
_FIT_FILTERS = ["All", "exceptional_match", "strong_match", "moderate_match", "weak_match", "poor_match"]


def _get_page_size() -> int:
    config = st.session_state.get("config")
    if config is not None:
        page_size: int = config.dashboard.page_size
        return page_size
    return DEFAULT_PAGE_SIZE


def _score_color(score: int) -> str:
    if score >= 75:
        return "green"
    elif score >= 60:
        return "orange"
    return "red"


def _get_summary_counts(session: Session) -> dict[str, int | float]:
    """Get evaluation summary counts and total cost."""
    tier2_counts = (
        session.query(MatchEvaluation.decision, func.count(MatchEvaluation.eval_id))
        .filter(MatchEvaluation.tier_evaluated == 2, MatchEvaluation.is_current == True)  # noqa: E712
        .group_by(MatchEvaluation.decision)
        .all()
    )

    t2_pass = 0
    t2_fail = 0
    t2_maybe = 0
    for decision, count in tier2_counts:
        if decision == "yes":
            t2_pass += count
        elif decision == "no":
            t2_fail += count
        elif decision == "maybe":
            t2_maybe += count

    t3_count = (
        session.query(func.count(func.distinct(MatchEvaluation.job_id)))
        .filter(MatchEvaluation.tier_evaluated == 3, MatchEvaluation.is_current == True)  # noqa: E712
        .scalar()
    ) or 0

    total_cost = (
        session.query(func.coalesce(func.sum(MatchEvaluation.cost_usd), 0.0))
        .filter(MatchEvaluation.is_current == True)  # noqa: E712
        .scalar()
    ) or 0.0

    return {
        "total": t2_pass + t2_fail + t2_maybe + t3_count,
        "pass": t2_pass,
        "fail": t2_fail,
        "maybe": t2_maybe,
        "tier3": t3_count,
        "cost": float(total_cost),
    }


def _render_summary(counts: dict[str, int | float]) -> None:
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Evaluated", counts["total"])
    with col2:
        st.metric("T2 Pass", counts["pass"])
    with col3:
        st.metric("T2 Maybe", counts["maybe"])
    with col4:
        st.metric("T2 Fail", counts["fail"])
    with col5:
        st.metric("Total Cost", f"${counts['cost']:.2f}")


def _render_filters() -> tuple[str, str, str]:
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        tier = st.selectbox("Tier", _TIER_FILTERS, key="eval_tier")
    with col2:
        fit = st.selectbox("Fit Category", _FIT_FILTERS, key="eval_fit")
    with col3:
        search = st.text_input("Search title or company", key="eval_search")
    return tier, fit, search


def _get_tier2_results(session: Session, search: str) -> list[tuple[MatchEvaluation, RawJobPosting]]:
    """Get Tier 2 evaluation results with job info."""
    query = (
        session.query(MatchEvaluation, RawJobPosting)
        .join(ProcessedJob, MatchEvaluation.job_id == ProcessedJob.job_id)
        .join(RawJobPosting, ProcessedJob.raw_id == RawJobPosting.raw_id)
        .filter(MatchEvaluation.tier_evaluated == 2, MatchEvaluation.is_current == True)  # noqa: E712
    )
    if search.strip():
        pattern = f"%{search.strip()}%"
        query = query.filter(
            (RawJobPosting.title.ilike(pattern)) | (RawJobPosting.company.ilike(pattern))
        )
    rows: list[tuple[MatchEvaluation, RawJobPosting]] = query.order_by(MatchEvaluation.evaluated_at.desc()).all()  # type: ignore[assignment]
    return rows


def _get_tier3_jobs(
    session: Session, fit_filter: str, search: str
) -> list[tuple[ProcessedJob, RawJobPosting]]:
    """Get jobs that have Tier 3 evaluations."""
    query = (
        session.query(ProcessedJob, RawJobPosting)
        .join(RawJobPosting, ProcessedJob.raw_id == RawJobPosting.raw_id)
        .join(MatchEvaluation, MatchEvaluation.job_id == ProcessedJob.job_id)
        .filter(MatchEvaluation.tier_evaluated == 3, MatchEvaluation.is_current == True)  # noqa: E712
    )
    if fit_filter != "All":
        query = query.filter(MatchEvaluation.fit_category == fit_filter)
    if search.strip():
        pattern = f"%{search.strip()}%"
        query = query.filter(
            (RawJobPosting.title.ilike(pattern)) | (RawJobPosting.company.ilike(pattern))
        )
    rows: list[tuple[ProcessedJob, RawJobPosting]] = query.distinct().order_by(ProcessedJob.updated_at.desc()).all()  # type: ignore[assignment]
    return rows


def _get_tier3_evals(session: Session, job_id: int) -> list[MatchEvaluation]:
    """Get all current Tier 3 evals for a job, recommended resume first."""
    evals = (
        session.query(MatchEvaluation)
        .filter(
            MatchEvaluation.job_id == job_id,
            MatchEvaluation.tier_evaluated == 3,
            MatchEvaluation.is_current == True,  # noqa: E712
        )
        .all()
    )
    # Sort: recommended resume first
    evals.sort(key=lambda e: e.resume_id != e.recommended_resume_id)
    return evals


def _render_score_bar(label: str, score: int | None) -> None:
    """Render a labeled score with color."""
    if score is None:
        st.markdown(f"**{label}:** N/A")
        return
    color = _score_color(score)
    st.markdown(f"**{label}:** :{color}[{score}]")


def _render_tier2_row(evaluation: MatchEvaluation, raw_job: RawJobPosting) -> None:
    """Render a Tier 2 evaluation result."""
    decision_map = {"yes": "Pass", "no": "Fail", "maybe": "Maybe"}
    decision_display = decision_map.get(evaluation.decision or "", evaluation.decision or "?")
    confidence = evaluation.confidence or 0.0
    source = source_badge(raw_job.source)

    header = (
        f"**T2 {decision_display}** ({confidence:.0%}) | "
        f"{source} | {raw_job.title} @ {raw_job.company}"
    )

    with st.expander(header, expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Decision:** {decision_display}")
            st.markdown(f"**Confidence:** {confidence:.0%}")
            st.markdown(f"**Model:** {evaluation.model_used}")
        with col2:
            st.markdown(f"**Cost:** ${evaluation.cost_usd:.4f}" if evaluation.cost_usd else "**Cost:** N/A")
            st.markdown(f"**Evaluated:** {evaluation.evaluated_at.strftime('%Y-%m-%d %H:%M')}")

        if evaluation.reasoning:
            st.markdown("---")
            st.markdown(f"**Reasoning:** {evaluation.reasoning}")

        flags = json.loads(evaluation.flags) if evaluation.flags else []
        if flags:
            st.markdown(f"**Flags:** {', '.join(flags)}")

        if raw_job.source_url:
            st.markdown("---")
            st.markdown(f"[View original posting]({raw_job.source_url})")


def _render_tier3_row(
    job: ProcessedJob,
    raw_job: RawJobPosting,
    evals: list[MatchEvaluation],
    resume_map: dict[int, str],
) -> None:
    """Render a Tier 3 evaluation result with multi-resume support."""
    if not evals:
        return

    primary = evals[0]  # Recommended resume eval (sorted first)
    score = primary.overall_score or 0
    color = _score_color(score)
    fit_display, _ = _FIT_CATEGORY_DISPLAY.get(primary.fit_category or "", ("?", "gray"))
    resume_label = resume_map.get(primary.resume_id or 0, "Unknown")
    source = source_badge(raw_job.source)

    header = (
        f"**:{color}[{score}]** | {fit_display} | "
        f"{source} | {raw_job.title} @ {raw_job.company} | "
        f"Resume: {resume_label}"
    )

    with st.expander(header, expanded=False):
        # Primary evaluation detail
        _render_eval_detail(primary, resume_label, is_primary=True)

        # Alternative resume evaluations
        for alt_eval in evals[1:]:
            st.markdown("---")
            alt_label = resume_map.get(alt_eval.resume_id or 0, "Unknown")
            st.markdown(f"### Alternative: {alt_label}")
            _render_eval_detail(alt_eval, alt_label, is_primary=False)

        if raw_job.source_url:
            st.markdown("---")
            st.markdown(f"[View original posting]({raw_job.source_url})")


def _render_eval_detail(evaluation: MatchEvaluation, resume_label: str, *, is_primary: bool) -> None:
    """Render detailed scores for a single Tier 3 evaluation."""
    if is_primary:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            _render_score_bar("Skills", evaluation.skill_match_score)
        with col2:
            _render_score_bar("Seniority", evaluation.seniority_match_score)
        with col3:
            _render_score_bar("Remote", evaluation.remote_compatibility_score)
        with col4:
            _render_score_bar("Salary", evaluation.salary_alignment_score)
    else:
        score = evaluation.overall_score or 0
        color = _score_color(score)
        fit_display, _ = _FIT_CATEGORY_DISPLAY.get(evaluation.fit_category or "", ("?", "gray"))
        st.markdown(f"**Score:** :{color}[{score}] | **Fit:** {fit_display}")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            _render_score_bar("Skills", evaluation.skill_match_score)
        with col2:
            _render_score_bar("Seniority", evaluation.seniority_match_score)
        with col3:
            _render_score_bar("Remote", evaluation.remote_compatibility_score)
        with col4:
            _render_score_bar("Salary", evaluation.salary_alignment_score)

    # Strengths / Weaknesses
    strengths = json.loads(evaluation.strengths) if evaluation.strengths else []
    weaknesses = json.loads(evaluation.weaknesses) if evaluation.weaknesses else []

    if strengths:
        st.markdown("**Strengths:** " + " | ".join(strengths))
    if weaknesses:
        st.markdown("**Weaknesses:** " + " | ".join(weaknesses))

    if evaluation.reasoning:
        st.markdown(f"**Reasoning:** {evaluation.reasoning}")

    hints = json.loads(evaluation.cover_letter_hints) if evaluation.cover_letter_hints else []
    if hints:
        st.markdown("**Cover Letter Hints:** " + " | ".join(hints))

    flags = json.loads(evaluation.flags) if evaluation.flags else []
    if flags:
        st.markdown(f"**Flags:** {', '.join(flags)}")

    # Meta info
    meta_parts = [f"Model: {evaluation.model_used}"]
    if evaluation.cost_usd:
        meta_parts.append(f"Cost: ${evaluation.cost_usd:.4f}")
    meta_parts.append(f"Evaluated: {evaluation.evaluated_at.strftime('%Y-%m-%d %H:%M')}")
    st.caption(" | ".join(meta_parts))


def main() -> None:
    """Evaluation Results page entry point."""
    st.header(PAGE_TITLE)

    try:
        with get_session() as session:
            counts = _get_summary_counts(session)
            _render_summary(counts)

            st.markdown("---")

            tier_filter, fit_filter, search = _render_filters()

            # Build resume label lookup
            resumes = session.query(ResumeProfile).all()
            resume_map: dict[int, str] = {r.resume_id: r.label for r in resumes}

            show_tier2 = tier_filter in ("All", "Tier 2")
            show_tier3 = tier_filter in ("All", "Tier 3")

            # Tier 2 results
            if show_tier2 and fit_filter == "All":
                tier2_results = _get_tier2_results(session, search)
                if tier2_results:
                    st.subheader(f"Tier 2 Results ({len(tier2_results)})")
                    page_size = _get_page_size()
                    offset, limit = paginated_controls(len(tier2_results), page_size, "eval_t2")
                    for evaluation, raw_job in tier2_results[offset : offset + limit]:
                        _render_tier2_row(evaluation, raw_job)
                elif tier_filter == "Tier 2":
                    st.info("No Tier 2 results found. Run `python run.py evaluate` first.")

            # Tier 3 results
            if show_tier3:
                tier3_jobs = _get_tier3_jobs(session, fit_filter, search)
                if tier3_jobs:
                    st.subheader(f"Tier 3 Results ({len(tier3_jobs)})")
                    page_size = _get_page_size()
                    offset, limit = paginated_controls(len(tier3_jobs), page_size, "eval_t3")
                    for job, raw_job in tier3_jobs[offset : offset + limit]:
                        evals = _get_tier3_evals(session, job.job_id)
                        _render_tier3_row(job, raw_job, evals, resume_map)
                elif tier_filter == "Tier 3":
                    st.info("No Tier 3 results found. Run `python run.py evaluate` first.")

            if counts["total"] == 0:
                st.info("No evaluation results yet. Run `python run.py evaluate` to start.")

    except RuntimeError:
        st.warning("Database not initialized. Run `python run.py init-db` first.")


main()
