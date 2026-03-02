
import pytest
from sqlalchemy.exc import IntegrityError

from jobhunter.db.models import (
    ApplicationStatus,
    Company,
    CoverLetter,
    JobFingerprint,
    MatchEvaluation,
    ProcessedJob,
    RawJobPosting,
    ResumeProfile,
    ScraperRun,
)


class TestCompany:
    def test_create_company(self, db_session):
        company = Company(name="Acme Corp")
        db_session.add(company)
        db_session.flush()
        assert company.company_id is not None
        assert company.name == "Acme Corp"

    def test_unique_name_constraint(self, db_session):
        db_session.add(Company(name="Acme Corp"))
        db_session.flush()
        db_session.add(Company(name="Acme Corp"))
        with pytest.raises(IntegrityError):
            db_session.flush()


class TestScraperRun:
    def test_create_scraper_run(self, db_session):
        run = ScraperRun(scraper_name="linkedin", status="running")
        db_session.add(run)
        db_session.flush()
        assert run.run_id is not None
        assert run.jobs_found == 0


class TestRawJobPosting:
    def test_create_raw_posting(self, db_session):
        posting = RawJobPosting(
            source="linkedin",
            source_url="https://linkedin.com/jobs/123",
            title="Senior Architect",
            company="Acme Corp",
            description="Build distributed systems",
            fingerprint_hash="abc123",
        )
        db_session.add(posting)
        db_session.flush()
        assert posting.raw_id is not None

    def test_raw_posting_with_scraper_run(self, db_session):
        run = ScraperRun(scraper_name="remote_io", status="success")
        db_session.add(run)
        db_session.flush()

        posting = RawJobPosting(
            source="remote_io",
            source_url="https://remote.io/job/1",
            title="Tech Lead",
            company="StartupX",
            description="Lead engineering team",
            fingerprint_hash="def456",
            scraper_run_id=run.run_id,
        )
        db_session.add(posting)
        db_session.flush()
        assert posting.scraper_run.run_id == run.run_id


class TestProcessedJob:
    def _make_processed_job(self, db_session):
        company = Company(name="TestCo")
        db_session.add(company)
        db_session.flush()

        raw = RawJobPosting(
            source="linkedin",
            source_url="https://example.com",
            title="Architect",
            company="TestCo",
            description="Job description",
            fingerprint_hash="hash1",
        )
        db_session.add(raw)
        db_session.flush()

        job = ProcessedJob(
            company_id=company.company_id,
            raw_id=raw.raw_id,
            title="Architect",
            location_policy="remote_worldwide",
            description_clean="Job description",
            application_url="https://apply.example.com",
            source_site="linkedin",
            fingerprint_hash="hash1",
        )
        db_session.add(job)
        db_session.flush()
        return job

    def test_create_processed_job(self, db_session):
        job = self._make_processed_job(db_session)
        assert job.job_id is not None
        assert job.status == "new"

    def test_fingerprint_unique(self, db_session):
        self._make_processed_job(db_session)
        company = Company(name="OtherCo")
        db_session.add(company)
        db_session.flush()

        raw = RawJobPosting(
            source="wellfound",
            source_url="https://wellfound.com/1",
            title="Architect",
            company="OtherCo",
            description="Desc",
            fingerprint_hash="hash1",
        )
        db_session.add(raw)
        db_session.flush()

        dup = ProcessedJob(
            company_id=company.company_id,
            raw_id=raw.raw_id,
            title="Architect",
            location_policy="remote_worldwide",
            description_clean="Desc",
            application_url="https://apply2.example.com",
            source_site="wellfound",
            fingerprint_hash="hash1",
        )
        db_session.add(dup)
        with pytest.raises(IntegrityError):
            db_session.flush()


class TestResumeProfile:
    def test_create_resume_profile(self, db_session):
        profile = ResumeProfile(
            label="leadership",
            file_path="data/resumes/resume_leadership.pdf",
            file_hash="abc123",
            extracted_text="John Doe, 10 years experience",
            key_skills='["Python", "Leadership"]',
            experience_summary="Senior engineering leader",
        )
        db_session.add(profile)
        db_session.flush()
        assert profile.resume_id is not None

    def test_unique_label(self, db_session):
        db_session.add(ResumeProfile(
            label="leadership",
            file_path="path1.pdf",
            file_hash="h1",
            extracted_text="text1",
            key_skills="[]",
            experience_summary="",
        ))
        db_session.flush()
        db_session.add(ResumeProfile(
            label="leadership",
            file_path="path2.pdf",
            file_hash="h2",
            extracted_text="text2",
            key_skills="[]",
            experience_summary="",
        ))
        with pytest.raises(IntegrityError):
            db_session.flush()


class TestMatchEvaluation:
    def test_create_evaluation(self, db_session):
        # Setup
        company = Company(name="EvalCo")
        db_session.add(company)
        db_session.flush()
        raw = RawJobPosting(
            source="linkedin", source_url="https://example.com", title="Dev",
            company="EvalCo", description="Desc", fingerprint_hash="evalhash",
        )
        db_session.add(raw)
        db_session.flush()
        job = ProcessedJob(
            company_id=company.company_id, raw_id=raw.raw_id, title="Dev",
            location_policy="remote_worldwide", description_clean="Desc",
            application_url="https://apply.com", source_site="linkedin",
            fingerprint_hash="evalhash",
        )
        db_session.add(job)
        db_session.flush()

        evaluation = MatchEvaluation(
            job_id=job.job_id,
            tier_evaluated=2,
            model_used="claude-3-5-haiku-latest",
            tokens_used=150,
            decision="yes",
            confidence=0.85,
        )
        db_session.add(evaluation)
        db_session.flush()
        assert evaluation.eval_id is not None


class TestCoverLetter:
    def test_create_cover_letter(self, db_session):
        company = Company(name="CLCo")
        db_session.add(company)
        db_session.flush()
        raw = RawJobPosting(
            source="linkedin", source_url="https://example.com", title="Lead",
            company="CLCo", description="Desc", fingerprint_hash="clhash",
        )
        db_session.add(raw)
        db_session.flush()
        job = ProcessedJob(
            company_id=company.company_id, raw_id=raw.raw_id, title="Lead",
            location_policy="remote_worldwide", description_clean="Desc",
            application_url="https://apply.com", source_site="linkedin",
            fingerprint_hash="clhash",
        )
        db_session.add(job)
        db_session.flush()
        resume = ResumeProfile(
            label="test", file_path="test.pdf", file_hash="h",
            extracted_text="text", key_skills="[]", experience_summary="",
        )
        db_session.add(resume)
        db_session.flush()

        letter = CoverLetter(
            job_id=job.job_id,
            resume_id=resume.resume_id,
            content="Dear Hiring Manager...",
            model_used="gpt-4o",
            tokens_used=500,
        )
        db_session.add(letter)
        db_session.flush()
        assert letter.letter_id is not None
        assert letter.is_active is True
        assert letter.version == 1


class TestApplicationStatus:
    def test_append_only_status(self, db_session):
        company = Company(name="StatusCo")
        db_session.add(company)
        db_session.flush()
        raw = RawJobPosting(
            source="wellfound", source_url="https://example.com", title="Mgr",
            company="StatusCo", description="Desc", fingerprint_hash="stathash",
        )
        db_session.add(raw)
        db_session.flush()
        job = ProcessedJob(
            company_id=company.company_id, raw_id=raw.raw_id, title="Mgr",
            location_policy="remote_worldwide", description_clean="Desc",
            application_url="https://apply.com", source_site="wellfound",
            fingerprint_hash="stathash",
        )
        db_session.add(job)
        db_session.flush()

        for status in ["new", "reviewed", "shortlisted"]:
            db_session.add(ApplicationStatus(job_id=job.job_id, status=status))
        db_session.flush()

        statuses = db_session.query(ApplicationStatus).filter_by(job_id=job.job_id).all()
        assert len(statuses) == 3


class TestJobFingerprint:
    def test_create_fingerprint(self, db_session):
        company = Company(name="FPCo")
        db_session.add(company)
        db_session.flush()
        raw = RawJobPosting(
            source="remote_io", source_url="https://example.com", title="Arch",
            company="FPCo", description="Desc", fingerprint_hash="fphash",
        )
        db_session.add(raw)
        db_session.flush()
        job = ProcessedJob(
            company_id=company.company_id, raw_id=raw.raw_id, title="Arch",
            location_policy="remote_worldwide", description_clean="Desc",
            application_url="https://apply.com", source_site="remote_io",
            fingerprint_hash="fphash",
        )
        db_session.add(job)
        db_session.flush()

        fp = JobFingerprint(
            fingerprint_hash="fphash",
            job_id=job.job_id,
            source_urls='["https://example.com"]',
        )
        db_session.add(fp)
        db_session.flush()
        assert fp.times_seen == 1
