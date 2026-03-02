import logging
import re
from pathlib import Path

from sqlalchemy.orm import Session

from jobhunter.db.models import ResumeProfile
from jobhunter.resume.extractor import extract_text_from_pdf
from jobhunter.utils.hashing import file_hash

logger = logging.getLogger(__name__)

DEFAULT_RESUME_DIR = Path("data/resumes")


class ResumeManager:
    """Manages resume PDF extraction and database storage."""

    def __init__(self, session: Session, resume_dir: Path = DEFAULT_RESUME_DIR):
        self.session = session
        self.resume_dir = resume_dir

    def sync_resumes(self) -> list[ResumeProfile]:
        """Scan resume directory, extract new/updated PDFs, return all profiles.

        For M0: extracted_text and file_hash are populated.
        key_skills and experience_summary are set to empty/placeholder values.
        AI-based extraction is deferred to M3.
        """
        self.resume_dir.mkdir(parents=True, exist_ok=True)

        pdf_files = list(self.resume_dir.glob("*.pdf"))
        if not pdf_files:
            logger.warning("No PDF files found in %s", self.resume_dir)
            return self.get_all_profiles()

        seen_labels: set[str] = set()

        for pdf_path in pdf_files:
            label = self._derive_label(pdf_path)

            if label in seen_labels:
                logger.error(
                    "Duplicate label '%s' derived from %s. Skipping — rename the file to get a distinct label.",
                    label,
                    pdf_path.name,
                )
                continue
            seen_labels.add(label)

            current_hash = file_hash(pdf_path)
            existing = self.get_profile_by_label(label)

            if existing is not None:
                if existing.file_hash == current_hash:
                    logger.info("Resume '%s' unchanged, skipping.", label)
                    continue
                # Hash mismatch — re-extract
                logger.info("Resume '%s' updated, re-extracting.", label)
                try:
                    text = extract_text_from_pdf(pdf_path)
                except Exception:
                    logger.exception("Failed to extract text from %s, skipping.", pdf_path)
                    continue
                existing.file_path = str(pdf_path)
                existing.file_hash = current_hash
                existing.extracted_text = text
            else:
                # New resume
                logger.info("New resume found: '%s' from %s", label, pdf_path.name)
                try:
                    text = extract_text_from_pdf(pdf_path)
                except Exception:
                    logger.exception("Failed to extract text from %s, skipping.", pdf_path)
                    continue
                profile = ResumeProfile(
                    label=label,
                    file_path=str(pdf_path),
                    file_hash=current_hash,
                    extracted_text=text,
                    key_skills="[]",
                    experience_summary="",
                )
                self.session.add(profile)

        self.session.flush()
        return self.get_all_profiles()

    def get_all_profiles(self) -> list[ResumeProfile]:
        """Return all stored resume profiles."""
        return list(self.session.query(ResumeProfile).all())

    def get_profile_by_label(self, label: str) -> ResumeProfile | None:
        """Lookup a specific resume profile by its label."""
        return self.session.query(ResumeProfile).filter_by(label=label).first()

    @staticmethod
    def _derive_label(pdf_path: Path) -> str:
        """Derive a label from a resume filename.

        Pattern: resume_{label}.pdf → label
        Otherwise: filename stem as label
        """
        stem = pdf_path.stem
        match = re.match(r"^resume[_-](.+)$", stem, re.IGNORECASE)
        if match:
            return match.group(1).lower()
        return stem.lower()
