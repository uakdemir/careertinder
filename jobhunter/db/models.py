from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


# DS1 -- RawJobPosting
class RawJobPosting(Base):
    __tablename__ = "raw_job_postings"

    raw_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(
        String,
        CheckConstraint("source IN ('remote_io', 'remote_rocketship', 'wellfound', 'linkedin')"),
        nullable=False,
    )
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    company: Mapped[str] = mapped_column(String, nullable=False)
    salary_raw: Mapped[str | None] = mapped_column(String, nullable=True)
    location_raw: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(default=_utcnow)
    scraper_run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("scraper_runs.run_id"), nullable=True
    )
    fingerprint_hash: Mapped[str] = mapped_column(String, nullable=False, index=True)

    scraper_run: Mapped["ScraperRun | None"] = relationship(back_populates="raw_postings")
    filter_results: Mapped[list["FilterResult"]] = relationship(back_populates="raw_posting")


# DS2 -- Company
class Company(Base):
    __tablename__ = "companies"

    company_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    website: Mapped[str | None] = mapped_column(String, nullable=True)
    industry: Mapped[str | None] = mapped_column(String, nullable=True)
    size: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    glassdoor_url: Mapped[str | None] = mapped_column(String, nullable=True)
    research_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    processed_jobs: Mapped[list["ProcessedJob"]] = relationship(back_populates="company")


# DS3 -- ProcessedJob
class ProcessedJob(Base):
    __tablename__ = "processed_jobs"
    __table_args__ = (
        Index("ix_processed_jobs_source_first_seen", "source_site", "first_seen"),
    )

    job_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.company_id"), nullable=False, index=True
    )
    raw_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("raw_job_postings.raw_id"), nullable=False, unique=True
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String, nullable=False, default="USD")
    location_policy: Mapped[str] = mapped_column(
        String,
        CheckConstraint(
            "location_policy IN ('remote_worldwide', 'remote_regional', "
            "'remote_country_specific', 'hybrid', 'onsite', 'unclear')"
        ),
        nullable=False,
    )
    remote_regions: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_clean: Mapped[str] = mapped_column(Text, nullable=False)
    requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    application_url: Mapped[str] = mapped_column(String, nullable=False)
    source_site: Mapped[str] = mapped_column(String, nullable=False)
    fingerprint_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    first_seen: Mapped[datetime] = mapped_column(default=_utcnow)
    last_seen: Mapped[datetime] = mapped_column(default=_utcnow)
    status: Mapped[str] = mapped_column(
        String,
        CheckConstraint(
            "status IN ('new', 'tier1_pass', 'tier1_fail', 'tier1_ambiguous', 'tier2_pass', "
            "'tier2_fail', 'tier2_maybe', 'tier2_error', 'evaluated', 'shortlisted', "
            "'rejected_by_user', 'applied')"
        ),
        nullable=False,
        default="new",
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    company: Mapped["Company"] = relationship(back_populates="processed_jobs")
    raw_posting: Mapped["RawJobPosting"] = relationship()
    evaluations: Mapped[list["MatchEvaluation"]] = relationship(back_populates="job")
    cover_letters: Mapped[list["CoverLetter"]] = relationship(back_populates="job")
    why_company_answers: Mapped[list["WhyCompany"]] = relationship(back_populates="job")
    application_statuses: Mapped[list["ApplicationStatus"]] = relationship(back_populates="job")
    filter_results: Mapped[list["FilterResult"]] = relationship(back_populates="job")
    fingerprint: Mapped["JobFingerprint | None"] = relationship(back_populates="job")


# DS4 -- MatchEvaluation
class MatchEvaluation(Base):
    __tablename__ = "match_evaluations"
    __table_args__ = (
        Index("ix_match_evaluations_job_resume", "job_id", "resume_id"),
    )

    eval_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("processed_jobs.job_id"), nullable=False, index=True)
    resume_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("resume_profiles.resume_id"), nullable=True)
    tier_evaluated: Mapped[int] = mapped_column(
        Integer, CheckConstraint("tier_evaluated IN (2, 3)"), nullable=False
    )
    overall_score: Mapped[int | None] = mapped_column(
        Integer, CheckConstraint("overall_score BETWEEN 0 AND 100"), nullable=True
    )
    fit_category: Mapped[str | None] = mapped_column(String, nullable=True)
    skill_match_score: Mapped[int | None] = mapped_column(
        Integer, CheckConstraint("skill_match_score BETWEEN 0 AND 100"), nullable=True
    )
    seniority_match_score: Mapped[int | None] = mapped_column(
        Integer, CheckConstraint("seniority_match_score BETWEEN 0 AND 100"), nullable=True
    )
    remote_compatibility_score: Mapped[int | None] = mapped_column(
        Integer, CheckConstraint("remote_compatibility_score BETWEEN 0 AND 100"), nullable=True
    )
    salary_alignment_score: Mapped[int | None] = mapped_column(
        Integer, CheckConstraint("salary_alignment_score BETWEEN 0 AND 100"), nullable=True
    )
    strengths: Mapped[str | None] = mapped_column(Text, nullable=True)
    weaknesses: Mapped[str | None] = mapped_column(Text, nullable=True)
    flags: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_resume_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("resume_profiles.resume_id"), nullable=True
    )
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_letter_hints: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision: Mapped[str | None] = mapped_column(String, nullable=True)
    confidence: Mapped[float | None] = mapped_column(
        Float, CheckConstraint("confidence BETWEEN 0.0 AND 1.0"), nullable=True
    )
    model_used: Mapped[str] = mapped_column(String, nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(default=_utcnow)

    job: Mapped["ProcessedJob"] = relationship(back_populates="evaluations")
    resume: Mapped["ResumeProfile | None"] = relationship(
        foreign_keys=[resume_id], back_populates="evaluations"
    )
    recommended_resume: Mapped["ResumeProfile | None"] = relationship(foreign_keys=[recommended_resume_id])


# DS5 -- CoverLetter
class CoverLetter(Base):
    __tablename__ = "cover_letters"

    letter_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("processed_jobs.job_id"), nullable=False, index=True)
    resume_id: Mapped[int] = mapped_column(Integer, ForeignKey("resume_profiles.resume_id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    model_used: Mapped[str] = mapped_column(String, nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(default=_utcnow)

    job: Mapped["ProcessedJob"] = relationship(back_populates="cover_letters")
    resume: Mapped["ResumeProfile"] = relationship()


# DS6 -- WhyCompany
class WhyCompany(Base):
    __tablename__ = "why_company_answers"

    answer_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("processed_jobs.job_id"), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    model_used: Mapped[str] = mapped_column(String, nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(default=_utcnow)

    job: Mapped["ProcessedJob"] = relationship(back_populates="why_company_answers")


# DS7 -- ApplicationStatus
class ApplicationStatus(Base):
    __tablename__ = "application_statuses"

    status_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("processed_jobs.job_id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String,
        CheckConstraint(
            "status IN ('new', 'reviewed', 'shortlisted', 'applying', 'applied', "
            "'interviewing', 'offered', 'rejected', 'withdrawn', 'rejected_by_user')"
        ),
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_by: Mapped[str] = mapped_column(String, nullable=False, default="system")

    job: Mapped["ProcessedJob"] = relationship(back_populates="application_statuses")


# DS8 -- ResumeProfile
class ResumeProfile(Base):
    __tablename__ = "resume_profiles"

    resume_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    file_hash: Mapped[str] = mapped_column(String, nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False)
    key_skills: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    experience_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    years_of_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_updated: Mapped[datetime] = mapped_column(default=_utcnow)

    evaluations: Mapped[list["MatchEvaluation"]] = relationship(
        foreign_keys=[MatchEvaluation.resume_id], back_populates="resume"
    )


# DS9 -- ScraperRun
class ScraperRun(Base):
    __tablename__ = "scraper_runs"

    run_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scraper_name: Mapped[str] = mapped_column(
        String,
        CheckConstraint("scraper_name IN ('remote_io', 'remote_rocketship', 'wellfound', 'linkedin')"),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String,
        CheckConstraint(
            "status IN ('running', 'success', 'partial_success', 'failed', 'timeout', 'blocked', 'cancelled')"
        ),
        nullable=False,
        default="running",
    )
    jobs_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    jobs_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    jobs_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages_scraped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_traceback: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)

    raw_postings: Mapped[list["RawJobPosting"]] = relationship(back_populates="scraper_run")


# DS10 -- FilterResult
class FilterResult(Base):
    """Audit trail for Tier 1 filtering decisions.

    One row per RawJobPosting (raw_id is unique). Re-filtering updates in place.
    """

    __tablename__ = "filter_results"

    filter_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("processed_jobs.job_id"), nullable=True
    )
    raw_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("raw_job_postings.raw_id"), nullable=False, unique=True
    )
    passed: Mapped[bool] = mapped_column(nullable=False)
    decision: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint("decision IN ('pass', 'fail', 'ambiguous')"),
        nullable=False,
    )
    rules_applied: Mapped[str] = mapped_column(Text, nullable=False)
    rules_passed: Mapped[str] = mapped_column(Text, nullable=False)
    rules_failed: Mapped[str] = mapped_column(Text, nullable=False)
    rule_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    filtered_at: Mapped[datetime] = mapped_column(default=_utcnow)

    job: Mapped["ProcessedJob | None"] = relationship(back_populates="filter_results")
    raw_posting: Mapped["RawJobPosting"] = relationship(back_populates="filter_results")


# DS11 -- JobFingerprint
class JobFingerprint(Base):
    __tablename__ = "job_fingerprints"

    fingerprint_hash: Mapped[str] = mapped_column(String, primary_key=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("processed_jobs.job_id"), nullable=False)
    source_urls: Mapped[str] = mapped_column(Text, nullable=False)
    first_seen: Mapped[datetime] = mapped_column(default=_utcnow)
    last_seen: Mapped[datetime] = mapped_column(default=_utcnow)
    times_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    job: Mapped["ProcessedJob"] = relationship(back_populates="fingerprint")
