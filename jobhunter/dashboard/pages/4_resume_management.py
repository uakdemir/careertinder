"""Resume Management page — upload PDFs, view extracted text, manage profiles."""

import logging
from pathlib import Path

import streamlit as st
from sqlalchemy.orm import Session

from jobhunter.db.models import ResumeProfile
from jobhunter.db.session import get_session
from jobhunter.resume.manager import DEFAULT_RESUME_DIR, ResumeManager

logger = logging.getLogger(__name__)

PAGE_TITLE = "Resume Management"


def _save_uploaded_file(uploaded_file: st.runtime.uploaded_file_manager.UploadedFile) -> Path:
    """Save an uploaded PDF to the resume directory. Returns the saved path."""
    resume_dir = DEFAULT_RESUME_DIR
    resume_dir.mkdir(parents=True, exist_ok=True)
    dest = resume_dir / str(uploaded_file.name)
    dest.write_bytes(uploaded_file.getvalue())
    return dest


def _render_upload_section(session: Session) -> None:
    """Render the PDF upload widget and handle new uploads."""
    uploaded = st.file_uploader("Upload a resume PDF", type=["pdf"], key="resume_upload")
    if uploaded is not None:
        dest = _save_uploaded_file(uploaded)
        manager = ResumeManager(session, DEFAULT_RESUME_DIR)
        profiles = manager.sync_resumes()
        st.success(f"Saved and processed **{dest.name}**. {len(profiles)} resume(s) on file.")


def _render_resume_list(session: Session) -> list[ResumeProfile]:
    """Render the table of existing resumes. Returns profiles for downstream use."""
    profiles = (
        session.query(ResumeProfile)
        .order_by(ResumeProfile.label)
        .all()
    )

    if not profiles:
        st.info("No resumes found. Upload a PDF to get started.")
        return []

    st.subheader("Existing Resumes")
    rows = [
        {
            "Label": p.label,
            "File": Path(p.file_path).name,
            "Characters": len(p.extracted_text),
            "Last Updated": p.last_updated.strftime("%Y-%m-%d %H:%M"),
        }
        for p in profiles
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)
    return profiles


def _render_resume_detail(session: Session, profiles: list[ResumeProfile]) -> None:
    """Render detail view for a selected resume: preview, re-extract, edit label."""
    if not profiles:
        return

    labels = [p.label for p in profiles]
    selected_label = st.selectbox("Select a resume to inspect", labels, key="resume_select")
    if selected_label is None:
        return

    profile = next(p for p in profiles if p.label == selected_label)

    with st.expander(f"Extracted Text — {profile.label}", expanded=True):
        if profile.extracted_text:
            st.text_area(
                "Content",
                value=profile.extracted_text,
                height=300,
                disabled=True,
                key="resume_text_preview",
                label_visibility="collapsed",
            )
        else:
            st.warning("No text extracted — the PDF may be scanned/image-based.")

    col1, col2 = st.columns(2)

    # Re-extract button
    with col1:
        if st.button("Re-extract text", key="re_extract"):
            manager = ResumeManager(session, DEFAULT_RESUME_DIR)
            # Force re-extract by clearing the hash so sync detects a change
            profile.file_hash = ""
            session.flush()
            manager.sync_resumes()
            st.success(f"Re-extracted text for **{profile.label}**.")
            st.rerun()

    # Edit label
    with col2:
        new_label = st.text_input("Edit label", value=profile.label, key="edit_label")
        if new_label and new_label != profile.label:
            # Check for duplicates
            existing = session.query(ResumeProfile).filter_by(label=new_label).first()
            if existing is not None:
                st.error(f"Label **{new_label}** already exists.")
            elif st.button("Save label", key="save_label"):
                profile.label = new_label
                session.flush()
                st.success(f"Label updated to **{new_label}**.")
                st.rerun()


def main() -> None:
    """Resume Management page entry point."""
    st.header(PAGE_TITLE)
    st.markdown("Upload resume PDFs, view extracted text, and manage resume profiles.")

    try:
        with get_session() as session:
            _render_upload_section(session)
            profiles = _render_resume_list(session)
            _render_resume_detail(session, profiles)
    except RuntimeError:
        st.warning("Database not initialized. Run `python run.py init-db` first.")


main()
