"""Applied Jobs — track submitted applications and add status notes."""

import streamlit as st
from sqlalchemy.orm import Session

from jobhunter.dashboard.components.status_actions import (
    latest_user_status_subquery,
    transition_job_status,
)
from jobhunter.db.models import (
    ApplicationStatus,
    CoverLetter,
    MatchEvaluation,
    ProcessedJob,
    ResumeProfile,
    WhyCompany,
)
from jobhunter.db.session import get_session


def _get_applied_jobs(session: Session) -> list[dict]:
    """Load jobs with 'applied' user status, including application date and notes."""
    latest_ds7 = latest_user_status_subquery()

    jobs = (
        session.query(ProcessedJob)
        .join(latest_ds7, ProcessedJob.job_id == latest_ds7.c.job_id)
        .filter(latest_ds7.c.user_status == "applied")
        .order_by(ProcessedJob.job_id.desc())
        .all()
    )

    results: list[dict] = []
    for job in jobs:
        # Get the 'applied' status record for timestamp
        applied_record = (
            session.query(ApplicationStatus)
            .filter_by(job_id=job.job_id, status="applied")
            .order_by(ApplicationStatus.status_id.desc())
            .first()
        )

        # Get all notes for this job
        all_statuses = (
            session.query(ApplicationStatus)
            .filter_by(job_id=job.job_id)
            .order_by(ApplicationStatus.status_id.desc())
            .all()
        )
        notes_history = [
            {"status": s.status, "notes": s.notes, "date": s.updated_at}
            for s in all_statuses
            if s.notes
        ]

        best_eval = (
            session.query(MatchEvaluation)
            .filter_by(job_id=job.job_id, is_current=True)
            .order_by(MatchEvaluation.overall_score.desc().nullslast())
            .first()
        )

        resume = None
        if best_eval and best_eval.recommended_resume_id:
            resume = session.query(ResumeProfile).filter_by(
                resume_id=best_eval.recommended_resume_id
            ).first()

        cl = (
            session.query(CoverLetter)
            .filter_by(job_id=job.job_id, is_active=True)
            .first()
        )
        wc = (
            session.query(WhyCompany)
            .filter_by(job_id=job.job_id, is_active=True)
            .first()
        )

        results.append({
            "job": job,
            "applied_at": applied_record.updated_at if applied_record else None,
            "notes_history": notes_history,
            "evaluation": best_eval,
            "resume": resume,
            "cover_letter": cl,
            "why_company": wc,
        })

    return results


def _render_applied_card(data: dict, session: Session) -> None:
    """Render a single applied job card."""
    job: ProcessedJob = data["job"]
    applied_at = data["applied_at"]
    notes_history: list[dict] = data["notes_history"]
    resume: ResumeProfile | None = data["resume"]
    cl: CoverLetter | None = data["cover_letter"]
    wc: WhyCompany | None = data["why_company"]

    with st.container(border=True):
        # Header
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"### {job.title}")
            company_name = job.company.name if job.company else "Unknown"
            st.caption(f"{company_name} | {job.location_policy or 'N/A'}")
        with col2:
            if applied_at:
                st.metric("Applied", applied_at.strftime("%b %d, %Y"))
            else:
                st.metric("Applied", "Date unknown")

        # Resume used
        if resume:
            st.caption(f"Resume: {resume.label}")

        # Application materials
        col_cl, col_wc = st.columns(2)
        with col_cl:
            if cl:
                with st.expander("Cover Letter", expanded=False):
                    st.markdown(cl.content)
            else:
                st.caption("No cover letter")
        with col_wc:
            if wc:
                with st.expander("Why This Company?", expanded=False):
                    st.markdown(wc.content)
            else:
                st.caption("No 'why company' answer")

        # Notes history
        if notes_history:
            with st.expander(f"Notes ({len(notes_history)})", expanded=False):
                for note in notes_history:
                    date_str = note["date"].strftime("%b %d %H:%M") if note["date"] else ""
                    st.markdown(f"**{note['status']}** ({date_str}): {note['notes']}")

        # Add note form
        col1, col2 = st.columns([3, 1])
        with col1:
            with st.form(key=f"applied_note_{job.job_id}"):
                note_text = st.text_input("Add note", placeholder="Interview scheduled, follow-up sent...")
                if st.form_submit_button("Save Note"):
                    transition_job_status(session, job.job_id, "applied", notes=note_text or None)
                    session.commit()
                    st.rerun()
        with col2:
            if st.button("View Detail", key=f"applied_detail_{job.job_id}"):
                st.session_state["detail_job_id"] = job.job_id
                st.switch_page("pages/2_job_detail.py")


def main() -> None:
    """Applied Jobs page entry point."""
    st.header("Applied Jobs")

    try:
        with get_session() as session:
            applied_jobs = _get_applied_jobs(session)

            if not applied_jobs:
                st.info("No applied jobs yet. Mark jobs as applied from Pipeline Review or Ready to Apply.")
                return

            st.caption(f"{len(applied_jobs)} applications")

            for data in applied_jobs:
                _render_applied_card(data, session)

    except RuntimeError:
        st.warning("Database not initialized. Run `python run.py init-db` first.")


main()
