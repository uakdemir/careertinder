from pathlib import Path

import pytest
from pdfplumber.utils.exceptions import PdfminerException

from jobhunter.resume.extractor import extract_text_from_pdf
from jobhunter.resume.manager import ResumeManager
from jobhunter.utils.hashing import file_hash


class TestExtractTextFromPdf:
    def test_extract_from_valid_pdf(self, sample_resume_pdf):
        text = extract_text_from_pdf(sample_resume_pdf)
        assert "John Doe" in text
        assert "Software Architect" in text

    def test_extract_from_empty_pdf(self, tmp_path):
        """A PDF with no text content returns empty string."""
        pdf_path = tmp_path / "empty.pdf"
        # Minimal valid PDF with no content stream text
        pdf_bytes = (
            b"%PDF-1.4\n"
            b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
            b"xref\n0 4\n"
            b"0000000000 65535 f \n"
            b"0000000009 00000 n \n"
            b"0000000058 00000 n \n"
            b"0000000115 00000 n \n"
            b"trailer\n<< /Size 4 /Root 1 0 R >>\n"
            b"startxref\n206\n%%EOF\n"
        )
        pdf_path.write_bytes(pdf_bytes)
        text = extract_text_from_pdf(pdf_path)
        assert text == ""

    def test_extract_from_corrupt_file_raises(self, tmp_path):
        bad_file = tmp_path / "corrupt.pdf"
        bad_file.write_bytes(b"not a pdf at all")
        with pytest.raises(PdfminerException):
            extract_text_from_pdf(bad_file)


class TestFileHash:
    def test_hash_consistency(self, sample_resume_pdf):
        h1 = file_hash(sample_resume_pdf)
        h2 = file_hash(sample_resume_pdf)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex digest

    def test_different_content_different_hash(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("content A", encoding="utf-8")
        f2.write_text("content B", encoding="utf-8")
        assert file_hash(f1) != file_hash(f2)


class TestResumeManager:
    def test_sync_no_pdfs(self, db_session, tmp_path):
        manager = ResumeManager(db_session, resume_dir=tmp_path / "resumes")
        profiles = manager.sync_resumes()
        assert profiles == []

    def test_sync_new_resume(self, db_session, sample_resume_pdf):
        resume_dir = sample_resume_pdf.parent
        manager = ResumeManager(db_session, resume_dir=resume_dir)
        profiles = manager.sync_resumes()
        assert len(profiles) == 1
        assert profiles[0].label == "test"
        assert "John Doe" in profiles[0].extracted_text

    def test_sync_unchanged_resume_skips(self, db_session, sample_resume_pdf):
        resume_dir = sample_resume_pdf.parent
        manager = ResumeManager(db_session, resume_dir=resume_dir)

        # First sync
        profiles1 = manager.sync_resumes()
        assert len(profiles1) == 1

        # Second sync — same file
        profiles2 = manager.sync_resumes()
        assert len(profiles2) == 1
        # Same record (not duplicated)
        assert profiles1[0].resume_id == profiles2[0].resume_id

    def test_derive_label_with_prefix(self):
        assert ResumeManager._derive_label(Path("resume_leadership.pdf")) == "leadership"
        assert ResumeManager._derive_label(Path("resume-architect.pdf")) == "architect"

    def test_derive_label_without_prefix(self):
        assert ResumeManager._derive_label(Path("my_cv.pdf")) == "my_cv"
