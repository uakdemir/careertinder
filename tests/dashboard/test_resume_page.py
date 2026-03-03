"""Tests for resume management page query logic."""

from sqlalchemy.orm import Session

from jobhunter.db.models import ResumeProfile
from jobhunter.resume.manager import ResumeManager


class TestResumeListQuery:
    """Test the resume listing query (used by the resume page)."""

    def test_empty_database(self, db_session: Session) -> None:
        """No resumes in DB → empty list."""
        profiles = db_session.query(ResumeProfile).order_by(ResumeProfile.label).all()
        assert profiles == []

    def test_returns_all_profiles_ordered(self, db_session: Session) -> None:
        """Inserted profiles are returned ordered by label."""
        db_session.add(
            ResumeProfile(
                label="leadership",
                file_path="data/resumes/resume_leadership.pdf",
                file_hash="abc123",
                extracted_text="Leader text",
                key_skills="[]",
                experience_summary="",
            )
        )
        db_session.add(
            ResumeProfile(
                label="architect",
                file_path="data/resumes/resume_architect.pdf",
                file_hash="def456",
                extracted_text="Architect text",
                key_skills="[]",
                experience_summary="",
            )
        )
        db_session.flush()

        profiles = db_session.query(ResumeProfile).order_by(ResumeProfile.label).all()
        assert len(profiles) == 2
        assert profiles[0].label == "architect"
        assert profiles[1].label == "leadership"

    def test_character_count(self, db_session: Session) -> None:
        """Character count matches extracted text length."""
        db_session.add(
            ResumeProfile(
                label="test",
                file_path="data/resumes/resume_test.pdf",
                file_hash="aaa",
                extracted_text="Hello World",
                key_skills="[]",
                experience_summary="",
            )
        )
        db_session.flush()

        profile = db_session.query(ResumeProfile).first()
        assert profile is not None
        assert len(profile.extracted_text) == 11


class TestResumeManagerSync:
    """Test ResumeManager.sync_resumes() integration with the page."""

    def test_sync_with_no_pdfs(self, db_session: Session, tmp_path) -> None:
        """Empty resume directory → returns empty list, no crash."""
        manager = ResumeManager(db_session, tmp_path)
        profiles = manager.sync_resumes()
        assert profiles == []

    def test_sync_creates_profile(self, db_session: Session, sample_resume_pdf, tmp_path) -> None:
        """A PDF in the resume dir gets extracted and stored."""
        # Move the PDF to the resume directory
        import shutil
        resume_dir = tmp_path / "resumes"
        resume_dir.mkdir()
        dest = resume_dir / sample_resume_pdf.name
        shutil.copy(sample_resume_pdf, dest)

        manager = ResumeManager(db_session, resume_dir)
        profiles = manager.sync_resumes()
        assert len(profiles) == 1
        assert profiles[0].label == "test"  # _derive_label strips "resume_" prefix
        assert len(profiles[0].extracted_text) > 0

    def test_edit_label(self, db_session: Session) -> None:
        """Simulates the page's edit-label flow: update label in DB."""
        db_session.add(
            ResumeProfile(
                label="old_label",
                file_path="data/resumes/resume_old.pdf",
                file_hash="hash1",
                extracted_text="text",
                key_skills="[]",
                experience_summary="",
            )
        )
        db_session.flush()

        profile = db_session.query(ResumeProfile).filter_by(label="old_label").first()
        assert profile is not None
        profile.label = "new_label"
        db_session.flush()

        updated = db_session.query(ResumeProfile).filter_by(label="new_label").first()
        assert updated is not None
        assert updated.extracted_text == "text"
