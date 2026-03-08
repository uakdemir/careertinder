"""Ready to Apply — assembled application packages for shortlisted jobs (D6)."""

import streamlit as st
from sqlalchemy.orm import Session

from jobhunter.dashboard.components.status_actions import (
    latest_user_status_subquery,
    transition_job_status,
)
from jobhunter.db.models import (
    CoverLetter,
    MatchEvaluation,
    ProcessedJob,
    ResumeProfile,
    WhyCompany,
)
from jobhunter.db.session import get_session


def _get_ready_jobs(session: Session) -> list[dict]:
    """Load shortlisted jobs with their generated content.

    Returns dicts with: job, evaluation, resume, cover_letter, why_company, has_all_materials
    """
    latest_ds7 = latest_user_status_subquery()

    jobs = (
        session.query(ProcessedJob)
        .join(latest_ds7, ProcessedJob.job_id == latest_ds7.c.job_id)
        .filter(latest_ds7.c.user_status == "shortlisted")
        .order_by(ProcessedJob.job_id.desc())
        .all()
    )

    results: list[dict] = []
    for job in jobs:
        best_eval = (
            session.query(MatchEvaluation)
            .filter_by(job_id=job.job_id, is_current=True)
            .order_by(MatchEvaluation.overall_score.desc().nullslast())
            .first()
        )

        resume = None
        if best_eval and best_eval.recommended_resume_id:
            resume = session.query(ResumeProfile).filter_by(resume_id=best_eval.recommended_resume_id).first()

        # Cover letter filtered by recommended resume (resume-specific storage)
        cl_query = session.query(CoverLetter).filter_by(job_id=job.job_id, is_active=True)
        if best_eval and best_eval.recommended_resume_id:
            cl_query = cl_query.filter_by(resume_id=best_eval.recommended_resume_id)
        cl = cl_query.first()
        wc = session.query(WhyCompany).filter_by(job_id=job.job_id, is_active=True).first()

        results.append({
            "job": job,
            "evaluation": best_eval,
            "resume": resume,
            "cover_letter": cl,
            "why_company": wc,
            "has_all_materials": cl is not None and wc is not None,
        })

    return results


def _render_application_card(data: dict, session: Session) -> None:
    """Render a single application package card."""
    job: ProcessedJob = data["job"]
    cl: CoverLetter | None = data["cover_letter"]
    wc: WhyCompany | None = data["why_company"]
    resume: ResumeProfile | None = data["resume"]

    with st.container(border=True):
        # Header
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"### {job.title}")
            st.caption(f"{job.company.name if job.company else 'Unknown'} | {job.location_policy or 'N/A'}")
        with col2:
            if data["has_all_materials"]:
                st.success("Ready")
            else:
                st.warning("Incomplete")

        # Application link
        if job.application_url:
            st.markdown(f"[Open Application]({job.application_url})")

        # Recommended resume
        if resume:
            st.markdown(f"**Recommended Resume:** {resume.label}")

        # Cover letter
        if cl:
            with st.expander("Cover Letter", expanded=False):
                st.markdown(cl.content)
                st.caption(f"v{cl.version} | {cl.model_used}")
        else:
            st.info("Cover letter not yet generated.")

        # Why company
        if wc:
            with st.expander("Why This Company?", expanded=False):
                st.markdown(wc.content)
                st.caption(f"v{wc.version} | {wc.model_used}")
        else:
            st.info("'Why this company?' not yet generated.")

        # Actions
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("Mark Applied", key=f"apply_{job.job_id}", type="primary"):
                transition_job_status(session, job.job_id, "applied")
                session.commit()
                st.rerun()
        with col2:
            if st.button("View Detail", key=f"detail_{job.job_id}"):
                st.session_state["detail_job_id"] = job.job_id
                st.switch_page("pages/2_job_detail.py")
        with col3:
            with st.form(key=f"notes_form_{job.job_id}"):
                notes = st.text_input("Notes", placeholder="Add a note...")
                if st.form_submit_button("Save Note"):
                    transition_job_status(session, job.job_id, "shortlisted", notes=notes or None)
                    session.commit()
                    st.rerun()


def main() -> None:
    """Ready to Apply page entry point."""
    st.header("Ready to Apply")

    try:
        with get_session() as session:
            ready_jobs = _get_ready_jobs(session)

            if not ready_jobs:
                st.info("No shortlisted jobs yet. Shortlist jobs from the Pipeline Review page.")
                return

            # Summary
            total = len(ready_jobs)
            complete = sum(1 for j in ready_jobs if j["has_all_materials"])
            st.caption(f"{complete}/{total} jobs have all materials ready")

            # Filter
            show_filter = st.radio(
                "Show",
                ["All Shortlisted", "Ready Only", "Incomplete Only"],
                horizontal=True,
            )

            filtered = ready_jobs
            if show_filter == "Ready Only":
                filtered = [j for j in ready_jobs if j["has_all_materials"]]
            elif show_filter == "Incomplete Only":
                filtered = [j for j in ready_jobs if not j["has_all_materials"]]

            for data in filtered:
                _render_application_card(data, session)

    except RuntimeError:
        st.warning("Database not initialized. Run `python run.py init-db` first.")


main()
