"""Job Detail — full evaluation context with resume comparison (D3).

Accessed via Pipeline Review "Details" button or direct URL with ?job_id=N.
Shows header, score breakdown, resume comparison, AI analysis, filter journey,
action bar, and full job description.
"""

import json
import logging

import pandas as pd
import streamlit as st
from sqlalchemy.orm import Session

from jobhunter.dashboard.components.job_card import _format_location, _format_salary
from jobhunter.dashboard.components.score_display import (
    fit_category_label,
    score_color,
)
from jobhunter.dashboard.components.status_actions import (
    get_current_status,
    transition_job_status,
)
from jobhunter.dashboard.components.status_badge import source_badge
from jobhunter.db.models import (
    FilterResult,
    MatchEvaluation,
    ProcessedJob,
    RawJobPosting,
    ResumeProfile,
)
from jobhunter.db.session import get_session

logger = logging.getLogger(__name__)


def _get_job_id() -> int | None:
    """Get job_id from session state or query params."""
    # Session state (from Pipeline Review card click)
    if "detail_job_id" in st.session_state:
        return int(st.session_state["detail_job_id"])
    # Query params (deep link)
    params = st.query_params
    job_id_str = params.get("job_id")
    if job_id_str:
        try:
            return int(job_id_str)
        except ValueError:
            return None
    return None


def _render_header(
    job: ProcessedJob,
    raw_job: RawJobPosting,
    best_eval: MatchEvaluation | None,
    resume_map: dict[int, str],
) -> None:
    """Render title, company, salary, overall score, fit category."""
    st.subheader(raw_job.title)

    source = source_badge(raw_job.source)
    salary = _format_salary(job)
    location = _format_location(job)

    st.markdown(f"{raw_job.company} | {location} | {salary}")

    if best_eval and best_eval.overall_score is not None:
        score = best_eval.overall_score
        color = score_color(score)
        fit = fit_category_label(best_eval.fit_category)
        resume_label = resume_map.get(best_eval.recommended_resume_id or 0, "—")
        st.markdown(
            f"Overall Score: **:{color}[{score}]** | Fit: **{fit}** | "
            f"Best Resume: **{resume_label}** | Source: {source}"
        )
    else:
        st.markdown(f"Source: {source} | Not yet evaluated by Tier 3")

    scraped_date = raw_job.scraped_at.strftime("%b %d, %Y") if raw_job.scraped_at else "—"
    st.caption(f"Scraped: {scraped_date}")


def _render_action_bar(session: Session, job: ProcessedJob, raw_job: RawJobPosting) -> None:
    """Render Shortlist / Skip / Apply / Cover Letter / Open Original buttons."""
    current = get_current_status(session, job.job_id)

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        if current == "shortlisted":
            if st.button("Remove Shortlist", key="jd_unshort", use_container_width=True):
                transition_job_status(session, job.job_id, "reviewed")
                st.rerun()
        else:
            if st.button("Shortlist", key="jd_short", type="primary", use_container_width=True):
                transition_job_status(session, job.job_id, "shortlisted")
                st.rerun()

    with col2:
        if current == "rejected_by_user":
            if st.button("Undo Skip", key="jd_unskip", use_container_width=True):
                transition_job_status(session, job.job_id, "reviewed")
                st.rerun()
        else:
            if st.button("Skip", key="jd_skip", use_container_width=True):
                transition_job_status(session, job.job_id, "rejected_by_user")
                st.rerun()

    with col3:
        if current == "applied":
            st.button("Applied", key="jd_applied", disabled=True, use_container_width=True)
        else:
            if st.button("Mark Applied", key="jd_apply", use_container_width=True):
                transition_job_status(session, job.job_id, "applied")
                st.rerun()

    with col4:
        # Cover letter generation — enabled when Tier 3 evaluation exists
        best_eval = (
            session.query(MatchEvaluation)
            .filter(
                MatchEvaluation.job_id == job.job_id,
                MatchEvaluation.tier_evaluated == 3,
                MatchEvaluation.is_current == True,  # noqa: E712
            )
            .order_by(MatchEvaluation.overall_score.desc())
            .first()
        )
        if best_eval and best_eval.overall_score:
            if st.button("Gen. Cover Letter", key="jd_cover", type="secondary", use_container_width=True):
                _generate_content_for_job(session, job, best_eval)
        else:
            st.button(
                "Gen. Cover Letter",
                key="jd_cover",
                disabled=True,
                use_container_width=True,
                help="Requires Tier 3 evaluation",
            )

    with col5:
        if raw_job.source_url:
            st.link_button("Open Original", raw_job.source_url, use_container_width=True)


def _render_score_bars(evaluation: MatchEvaluation) -> None:
    """Render 4 horizontal score bars (skills, seniority, remote, salary)."""
    st.subheader("Score Breakdown")

    dimensions = [
        ("Skill Match", evaluation.skill_match_score),
        ("Seniority", evaluation.seniority_match_score),
        ("Remote Compatibility", evaluation.remote_compatibility_score),
        ("Salary Alignment", evaluation.salary_alignment_score),
    ]

    for label, score in dimensions:
        if score is not None:
            color = score_color(score)
            col1, col2 = st.columns([3, 1])
            with col1:
                st.progress(score / 100, text=label)
            with col2:
                st.markdown(f"**:{color}[{score}]**")
        else:
            st.markdown(f"**{label}:** N/A")


def _render_resume_comparison(
    evals: list[MatchEvaluation], resume_map: dict[int, str]
) -> None:
    """Render side-by-side comparison table for all resume evaluations."""
    if not evals:
        return

    st.subheader("Resume Comparison")

    # Build comparison data
    dimensions = ["Overall", "Skills", "Seniority", "Remote", "Salary"]
    data: dict[str, list] = {"Dimension": dimensions}

    for ev in evals:
        resume_label = resume_map.get(ev.resume_id or 0, "Unknown")
        is_recommended = ev.resume_id == ev.recommended_resume_id
        col_name = f"{resume_label} {'(*)' if is_recommended else ''}"
        data[col_name] = [
            ev.overall_score,
            ev.skill_match_score,
            ev.seniority_match_score,
            ev.remote_compatibility_score,
            ev.salary_alignment_score,
        ]

    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption("* = Recommended resume")


def _render_reasoning(evaluation: MatchEvaluation) -> None:
    """Render AI reasoning, strengths, weaknesses, cover letter hints."""
    st.subheader("AI Analysis")

    # Strengths
    strengths = json.loads(evaluation.strengths) if evaluation.strengths else []
    if strengths:
        st.markdown("**Strengths:**")
        for s in strengths:
            st.markdown(f"+ {s}")

    # Weaknesses
    weaknesses = json.loads(evaluation.weaknesses) if evaluation.weaknesses else []
    if weaknesses:
        st.markdown("**Weaknesses:**")
        for w in weaknesses:
            st.markdown(f"- {w}")

    # Reasoning
    if evaluation.reasoning:
        st.markdown("**AI Reasoning:**")
        st.info(evaluation.reasoning)

    # Cover letter hints
    hints = json.loads(evaluation.cover_letter_hints) if evaluation.cover_letter_hints else []
    if hints:
        st.markdown("**Cover Letter Hints:**")
        for h in hints:
            st.markdown(f"- {h}")

    # Flags
    flags = json.loads(evaluation.flags) if evaluation.flags else []
    if flags:
        st.warning(f"Flags: {', '.join(flags)}")


def _render_filter_history(session: Session, job: ProcessedJob) -> None:
    """Show the job's journey through Tier 1 -> Tier 2 -> Tier 3."""
    st.subheader("Filter Journey")

    # Tier 1 result
    filter_result = (
        session.query(FilterResult)
        .filter(FilterResult.job_id == job.job_id)
        .first()
    )
    if filter_result:
        decision_display = {"pass": "PASS", "fail": "FAIL", "ambiguous": "AMBIGUOUS"}.get(
            filter_result.decision, filter_result.decision
        )
        rules_failed = json.loads(filter_result.rules_failed) if filter_result.rules_failed else []
        failed_info = f" — failed: {', '.join(rules_failed)}" if rules_failed else ""
        st.markdown(f"**Tier 1 (Rule-based):** {decision_display}{failed_info}")
    else:
        st.markdown("**Tier 1:** No filter result")

    # Tier 2 eval
    t2_eval = (
        session.query(MatchEvaluation)
        .filter(
            MatchEvaluation.job_id == job.job_id,
            MatchEvaluation.tier_evaluated == 2,
            MatchEvaluation.is_current == True,  # noqa: E712
        )
        .first()
    )
    if t2_eval:
        decision = t2_eval.decision or "?"
        confidence = t2_eval.confidence or 0.0
        reasoning = f' — "{t2_eval.reasoning}"' if t2_eval.reasoning else ""
        st.markdown(
            f"**Tier 2 ({t2_eval.model_used}):** {decision.upper()} ({confidence:.0%}){reasoning}"
        )

    # Tier 3 eval
    t3_evals = (
        session.query(MatchEvaluation)
        .filter(
            MatchEvaluation.job_id == job.job_id,
            MatchEvaluation.tier_evaluated == 3,
            MatchEvaluation.is_current == True,  # noqa: E712
        )
        .all()
    )
    if t3_evals:
        primary = t3_evals[0]
        score = primary.overall_score or 0
        fit = fit_category_label(primary.fit_category)
        st.markdown(f"**Tier 3 ({primary.model_used}):** {score} — {fit}")


def _render_generated_content(session: Session, job: ProcessedJob, evaluation: MatchEvaluation | None) -> None:
    """Display generated cover letter and why-company answer.

    Cover letter is filtered by recommended_resume_id from the evaluation,
    matching the resume-specific storage contract.
    """
    from jobhunter.db.models import CoverLetter, WhyCompany

    # Cover letter — filtered by recommended resume
    resume_id = evaluation.recommended_resume_id if evaluation else None
    cl_query = session.query(CoverLetter).filter_by(job_id=job.job_id, is_active=True)
    if resume_id:
        cl_query = cl_query.filter_by(resume_id=resume_id)
    cl = cl_query.first()
    if cl:
        st.subheader("Cover Letter")
        st.markdown(cl.content)
        st.caption(f"v{cl.version} | {cl.model_used} | ${cl.cost_usd:.4f} | {cl.generated_at:%Y-%m-%d %H:%M}")
    else:
        st.info("No cover letter generated yet. Click 'Gen. Cover Letter' to create one.")

    # Why-company
    wc = (
        session.query(WhyCompany)
        .filter_by(job_id=job.job_id, is_active=True)
        .first()
    )
    if wc:
        st.subheader("Why This Company?")
        st.markdown(wc.content)
        st.caption(f"v{wc.version} | {wc.model_used} | ${wc.cost_usd:.4f} | {wc.generated_at:%Y-%m-%d %H:%M}")
    else:
        st.info("No 'why this company?' answer generated yet.")


def _generate_content_for_job(session: Session, job: ProcessedJob, evaluation: MatchEvaluation) -> None:
    """Trigger cover letter + why-company generation from the dashboard."""
    import asyncio

    from jobhunter.config.loader import load_config
    from jobhunter.config.schema import SecretsConfig
    from jobhunter.db.settings import get_ai_cost_config
    from jobhunter.generation.cover_letter import CoverLetterGenerator
    from jobhunter.generation.service import GenerationCostTracker
    from jobhunter.generation.why_company import WhyCompanyGenerator

    config = load_config()
    secrets = SecretsConfig()
    model_config = config.ai_models.content_gen

    # Provider-neutral client selection
    from jobhunter.ai.claude_client import AIClient

    client: AIClient
    if model_config.provider == "openai":
        if not secrets.openai_api_key:
            st.error("OPENAI_API_KEY not configured.")
            return
        from jobhunter.ai.openai_client import OpenAIClient

        client = OpenAIClient(api_key=secrets.openai_api_key)
    else:
        if not secrets.anthropic_api_key:
            st.error("ANTHROPIC_API_KEY not configured.")
            return
        from jobhunter.ai.claude_client import ClaudeClient

        client = ClaudeClient(api_key=secrets.anthropic_api_key)

    cost_config = get_ai_cost_config(session)
    cost_tracker = GenerationCostTracker(session, cost_config.daily_cap_usd, cost_config.warn_at_percent)

    resume = (
        session.query(ResumeProfile).filter_by(resume_id=evaluation.recommended_resume_id).first()
        if evaluation.recommended_resume_id
        else None
    )
    if not resume:
        st.error("Recommended resume not found.")
        return

    # Cost cap check before each generation call (not once for both)
    with st.spinner("Generating cover letter..."):
        if not cost_tracker.can_spend():
            st.error("Daily cost cap reached. Cover letter generation blocked.")
        else:
            cl_gen = CoverLetterGenerator(session, client, model_config)
            cl_result = asyncio.run(cl_gen.generate(job, evaluation, resume))
            if cl_result.success:
                st.success(f"Cover letter generated (${cl_result.cost_usd:.4f})")
            else:
                st.error(f"Cover letter generation failed: {cl_result.error}")

    with st.spinner("Generating 'Why this company?' answer..."):
        if not cost_tracker.can_spend():
            st.error("Daily cost cap reached. Why-company generation blocked.")
        else:
            wc_gen = WhyCompanyGenerator(session, client, model_config)
            wc_result = asyncio.run(wc_gen.generate(job, evaluation))
            if wc_result.success:
                st.success(f"Why-company answer generated (${wc_result.cost_usd:.4f})")
            else:
                st.error(f"Why-company generation failed: {wc_result.error}")

    st.rerun()


def _render_job_description(raw_job: RawJobPosting) -> None:
    """Collapsible full job description."""
    with st.expander("Full Job Description", expanded=False):
        if raw_job.description:
            st.markdown(raw_job.description)
        else:
            st.caption("No description available.")


def _auto_mark_reviewed(session: Session, job_id: int) -> None:
    """Auto-create a 'reviewed' DS7 record if user hasn't interacted yet."""
    current = get_current_status(session, job_id)
    if current is None:
        transition_job_status(session, job_id, "reviewed", notes="Auto-marked on detail view")


def main() -> None:
    """Job Detail page entry point."""
    job_id = _get_job_id()

    if job_id is None:
        st.header("Job Detail")
        st.info("Select a job from Pipeline Review to see details.")
        if st.button("Go to Pipeline Review"):
            st.switch_page("pages/1_pipeline_review.py")
        return

    try:
        with get_session() as session:
            # Load job
            job = session.query(ProcessedJob).filter_by(job_id=job_id).first()
            if job is None:
                st.error(f"Job #{job_id} not found.")
                if st.button("Back to Pipeline Review"):
                    st.switch_page("pages/1_pipeline_review.py")
                return

            raw_job = session.query(RawJobPosting).filter_by(raw_id=job.raw_id).first()
            if raw_job is None:
                st.error("Raw job data not found.")
                return

            # Resume lookup
            resumes = session.query(ResumeProfile).all()
            resume_map: dict[int, str] = {r.resume_id: r.label for r in resumes}

            # Get evaluations
            t3_evals = (
                session.query(MatchEvaluation)
                .filter(
                    MatchEvaluation.job_id == job_id,
                    MatchEvaluation.tier_evaluated == 3,
                    MatchEvaluation.is_current == True,  # noqa: E712
                )
                .all()
            )
            # Sort recommended resume first
            t3_evals.sort(key=lambda e: e.resume_id != e.recommended_resume_id)
            best_eval = t3_evals[0] if t3_evals else None

            # Auto-mark as reviewed
            _auto_mark_reviewed(session, job_id)

            # Back link
            if st.button("Back to Pipeline Review"):
                st.switch_page("pages/1_pipeline_review.py")

            # Header
            _render_header(job, raw_job, best_eval, resume_map)

            st.divider()

            # Action bar
            _render_action_bar(session, job, raw_job)

            st.divider()

            # Score bars (Tier 3 only)
            if best_eval:
                _render_score_bars(best_eval)

                st.divider()

                # Resume comparison
                if len(t3_evals) > 0:
                    _render_resume_comparison(t3_evals, resume_map)

                st.divider()

                # AI Analysis
                _render_reasoning(best_eval)

            st.divider()

            # Generated content (cover letter + why-company)
            _render_generated_content(session, job, best_eval)

            if not best_eval:
                st.info("This job has not been evaluated by Tier 3 yet.")

            st.divider()

            # Filter journey
            _render_filter_history(session, job)

            st.divider()

            # Full description
            _render_job_description(raw_job)

    except RuntimeError:
        st.warning("Database not initialized. Run `python run.py init-db` first.")


main()
