"""Filter service for Tier 1 filtering operations.

Orchestrates filtering, database writes, and audit logging.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from jobhunter.db.models import Company, FilterResult, JobFingerprint, ProcessedJob, RawJobPosting
from jobhunter.filters.engine import FilterOutcome, RuleEngine
from jobhunter.filters.parsers.location_parser import parse_location
from jobhunter.filters.parsers.salary_parser import parse_salary
from jobhunter.filters.rules.base import FilterDecision

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from jobhunter.config.schema import FilteringConfig

logger = logging.getLogger(__name__)


def get_or_create_company(session: Session, company_name: str) -> Company:
    """Get existing or create new Company record.

    Uses existing DS2 schema: `name` is UNIQUE and normalized (title-cased, trimmed).
    """
    canonical_name = company_name.strip().title()  # Title-case per DS2 spec

    existing = session.execute(
        select(Company).where(Company.name == canonical_name)
    ).scalar_one_or_none()

    if existing:
        return existing

    company = Company(name=canonical_name)
    session.add(company)
    session.flush()  # Get company_id before ProcessedJob insert
    return company


def _clean_description(description: str) -> str:
    """Clean and normalize job description.

    Removes HTML artifacts and normalizes whitespace.
    """
    import re

    # Remove HTML tags
    cleaned = re.sub(r"<[^>]+>", " ", description)
    # Normalize whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def upsert_filter_result(
    session: Session,
    raw_job: RawJobPosting,
    outcome: FilterOutcome,
    job_id: int | None = None,
) -> FilterResult:
    """Insert or update FilterResult for a raw job.

    Uses INSERT ON CONFLICT for idempotent upserts.
    """
    passed = outcome.final_decision != FilterDecision.FAIL
    decision = outcome.final_decision.value

    rules_applied = [r.rule_name for r in outcome.rule_results]
    rule_details = {r.rule_name: r.details for r in outcome.rule_results if r.details}

    # Check if filter result exists
    existing = session.execute(
        select(FilterResult).where(FilterResult.raw_id == raw_job.raw_id)
    ).scalar_one_or_none()

    if existing:
        # Update existing
        existing.passed = passed
        existing.decision = decision
        existing.job_id = job_id
        existing.rules_applied = json.dumps(rules_applied)
        existing.rules_passed = json.dumps(outcome.passed_rules)
        existing.rules_failed = json.dumps(outcome.failed_rules)
        existing.rule_details = json.dumps(rule_details) if rule_details else None
        existing.filtered_at = datetime.now(UTC)
        session.flush()
        return existing

    # Create new
    filter_result = FilterResult(
        raw_id=raw_job.raw_id,
        job_id=job_id,
        passed=passed,
        decision=decision,
        rules_applied=json.dumps(rules_applied),
        rules_passed=json.dumps(outcome.passed_rules),
        rules_failed=json.dumps(outcome.failed_rules),
        rule_details=json.dumps(rule_details) if rule_details else None,
    )
    session.add(filter_result)
    session.flush()
    return filter_result


def upsert_processed_job(
    session: Session,
    raw_job: RawJobPosting,
    outcome: FilterOutcome,
    company_id: int,
) -> ProcessedJob:
    """Create or update ProcessedJob for a passing/ambiguous job."""
    # Parse salary and location
    parsed_salary = parse_salary(raw_job.salary_raw)
    parsed_location = parse_location(raw_job.location_raw, raw_job.description)

    # Determine status
    if outcome.final_decision == FilterDecision.PASS:
        status = "tier1_pass"
    else:
        status = "tier1_ambiguous"

    # Check if ProcessedJob exists (by raw_id unique constraint)
    existing = session.execute(
        select(ProcessedJob).where(ProcessedJob.raw_id == raw_job.raw_id)
    ).scalar_one_or_none()

    now = datetime.now(UTC)

    if existing:
        # Update existing
        existing.status = status
        existing.salary_min = parsed_salary.min_annual_usd if parsed_salary else None
        existing.salary_max = parsed_salary.max_annual_usd if parsed_salary else None
        existing.currency = parsed_salary.original_currency if parsed_salary else "USD"
        existing.location_policy = parsed_location.policy.value
        existing.remote_regions = (
            json.dumps(parsed_location.allowed_regions)
            if parsed_location.allowed_regions
            else None
        )
        existing.last_seen = now
        existing.updated_at = now
        session.flush()
        return existing

    # Create new
    job = ProcessedJob(
        raw_id=raw_job.raw_id,
        company_id=company_id,
        title=raw_job.title.strip(),
        salary_min=parsed_salary.min_annual_usd if parsed_salary else None,
        salary_max=parsed_salary.max_annual_usd if parsed_salary else None,
        currency=parsed_salary.original_currency if parsed_salary else "USD",
        location_policy=parsed_location.policy.value,
        remote_regions=(
            json.dumps(parsed_location.allowed_regions)
            if parsed_location.allowed_regions
            else None
        ),
        description_clean=_clean_description(raw_job.description),
        requirements=raw_job.requirements,
        application_url=raw_job.source_url,
        source_site=raw_job.source,
        fingerprint_hash=raw_job.fingerprint_hash,
        first_seen=now,
        last_seen=now,
        status=status,
    )
    session.add(job)
    session.flush()
    return job


def upsert_fingerprint(
    session: Session,
    job: ProcessedJob,
    raw_job: RawJobPosting,
) -> JobFingerprint:
    """Insert or update fingerprint for a processed job."""
    existing = session.get(JobFingerprint, job.fingerprint_hash)

    if existing:
        # Update existing: add source URL, increment times_seen, update last_seen
        urls = json.loads(existing.source_urls)
        if raw_job.source_url not in urls:
            urls.append(raw_job.source_url)
            existing.source_urls = json.dumps(urls)
        existing.times_seen += 1
        existing.last_seen = datetime.now(UTC)
        session.flush()
        return existing

    # Create new fingerprint
    fingerprint = JobFingerprint(
        fingerprint_hash=job.fingerprint_hash,
        job_id=job.job_id,
        source_urls=json.dumps([raw_job.source_url]),
        times_seen=1,
        first_seen=datetime.now(UTC),
        last_seen=datetime.now(UTC),
    )
    session.add(fingerprint)
    session.flush()
    return fingerprint


def persist_filter_outcome(
    session: Session,
    raw_job: RawJobPosting,
    outcome: FilterOutcome,
) -> FilterResult:
    """Atomically persist FilterResult, ProcessedJob (if passing), and JobFingerprint.

    This is a single transaction - if any write fails, all are rolled back.
    """
    job_id: int | None = None

    # If passed/ambiguous, create ProcessedJob + Company + JobFingerprint
    if outcome.final_decision != FilterDecision.FAIL:
        company = get_or_create_company(session, raw_job.company)
        processed_job = upsert_processed_job(session, raw_job, outcome, company.company_id)
        job_id = processed_job.job_id
        upsert_fingerprint(session, processed_job, raw_job)

    # Upsert FilterResult
    filter_result = upsert_filter_result(session, raw_job, outcome, job_id)

    return filter_result


def filter_unprocessed_jobs(
    session: Session,
    config: FilteringConfig,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[int, int, int, int]:
    """Filter unprocessed raw job postings.

    Args:
        session: Database session
        config: Filtering configuration
        force: If True, re-filter all jobs (not just unfiltered)
        dry_run: If True, log what would happen without writing

    Returns:
        Tuple of (total, passed, failed, ambiguous) counts
    """
    engine = RuleEngine(config)

    # Build query for jobs to filter
    query = select(RawJobPosting)
    if not force:
        # Only jobs without a FilterResult
        query = query.outerjoin(FilterResult).where(FilterResult.filter_id.is_(None))

    jobs = list(session.execute(query).scalars().all())
    logger.info("Found %d jobs to filter (force=%s)", len(jobs), force)

    passed_count = 0
    failed_count = 0
    ambiguous_count = 0

    for job in jobs:
        outcome = engine.filter(job)

        if outcome.final_decision == FilterDecision.PASS:
            passed_count += 1
        elif outcome.final_decision == FilterDecision.FAIL:
            failed_count += 1
        else:
            ambiguous_count += 1

        if dry_run:
            logger.info(
                "DRY RUN: raw_id=%d would be %s (failed: %s, ambiguous: %s)",
                job.raw_id,
                outcome.final_decision.value,
                outcome.failed_rules,
                outcome.ambiguous_rules,
            )
        else:
            try:
                persist_filter_outcome(session, job, outcome)
            except Exception:
                logger.exception("Failed to persist filter outcome for raw_id=%d", job.raw_id)
                # Continue with other jobs - don't abort entire batch
                continue

    if not dry_run:
        session.commit()

    return len(jobs), passed_count, failed_count, ambiguous_count
