"""Manual Job Entry — add jobs from any website via a dashboard form."""

import logging

import streamlit as st

from jobhunter.db.models import RawJobPosting
from jobhunter.db.session import get_session
from jobhunter.utils.hashing import normalize_and_hash

logger = logging.getLogger(__name__)


def _handle_submission(
    title: str,
    company: str,
    source_url: str,
    description: str,
    salary_raw: str,
    location_raw: str,
    requirements: str,
) -> None:
    """Validate and persist the manual job entry."""
    errors: list[str] = []
    if not title.strip():
        errors.append("Job Title is required.")
    if not company.strip():
        errors.append("Company is required.")
    if not source_url.strip():
        errors.append("Job Posting URL is required.")
    if not description.strip():
        errors.append("Job Description is required.")

    if errors:
        for err in errors:
            st.error(err)
        return

    fingerprint = normalize_and_hash(company.strip(), title.strip())

    with get_session() as session:
        existing = session.query(RawJobPosting).filter_by(fingerprint_hash=fingerprint).first()
        if existing:
            st.error(
                f"A job with this title and company already exists "
                f"(source: {existing.source}, added: {existing.scraped_at.strftime('%b %d, %Y')})."
            )
            st.info("Check the Raw Jobs page to view the existing entry.")
            return

        posting = RawJobPosting(
            source="manual",
            source_url=source_url.strip(),
            title=title.strip(),
            company=company.strip(),
            salary_raw=salary_raw.strip() or None,
            location_raw=location_raw.strip() or None,
            description=description.strip(),
            requirements=requirements.strip() or None,
            raw_html=None,
            fingerprint_hash=fingerprint,
            scraper_run_id=None,
        )
        session.add(posting)
        session.commit()

        st.success(f"Job added: **{title.strip()}** at **{company.strip()}**")
        st.info("The job will appear in Raw Jobs and flow through filtering when you run the pipeline.")


def main() -> None:
    """Manual Job Entry page entry point."""
    st.header("Add Job Manually")
    st.caption("Add a job posting from any website. It will flow through the same pipeline as scraped jobs.")

    with st.form("manual_entry_form"):
        title = st.text_input("Job Title *", placeholder="Senior Software Engineer")
        company = st.text_input("Company *", placeholder="Acme Corp")
        source_url = st.text_input("Job Posting URL *", placeholder="https://...")
        description = st.text_area(
            "Job Description *",
            height=300,
            placeholder="Paste the full job description here...",
        )
        col1, col2 = st.columns(2)
        with col1:
            salary_raw = st.text_input("Salary Info", placeholder="$120K-$160K")
        with col2:
            location_raw = st.text_input("Location", placeholder="Remote, US-based")
        requirements = st.text_area(
            "Requirements (optional)",
            height=150,
            placeholder="Paste requirements section if separate...",
        )

        submitted = st.form_submit_button("Add Job", type="primary")

    if submitted:
        _handle_submission(title, company, source_url, description, salary_raw, location_raw, requirements)


main()
