"""Tests for raw jobs browser page query logic."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from jobhunter.db.models import RawJobPosting


def _make_job(
    session: Session,
    *,
    source: str = "linkedin",
    title: str = "Software Architect",
    company: str = "TestCorp",
    salary_raw: str | None = "$150K",
    scraped_at: datetime | None = None,
    fingerprint: str | None = None,
) -> RawJobPosting:
    """Helper to create a RawJobPosting in the test DB."""
    if scraped_at is None:
        scraped_at = datetime.now(UTC)
    if fingerprint is None:
        import hashlib
        fingerprint = hashlib.sha256(f"{company}:{title}:{source}:{scraped_at}".encode()).hexdigest()

    job = RawJobPosting(
        source=source,
        source_url=f"https://example.com/job/{fingerprint[:8]}",
        title=title,
        company=company,
        salary_raw=salary_raw,
        location_raw="Remote",
        description=f"Job description for {title} at {company}",
        fingerprint_hash=fingerprint,
        scraped_at=scraped_at,
    )
    session.add(job)
    session.flush()
    return job


class TestRawJobsQuery:
    """Test the query logic used by the raw jobs page."""

    def test_empty_database(self, db_session: Session) -> None:
        """No jobs → count is 0."""
        count = db_session.query(RawJobPosting).count()
        assert count == 0

    def test_source_filter(self, db_session: Session) -> None:
        """Filter by source returns only matching jobs."""
        _make_job(db_session, source="linkedin", title="Job A", company="A Corp")
        _make_job(db_session, source="wellfound", title="Job B", company="B Corp")
        _make_job(db_session, source="linkedin", title="Job C", company="C Corp")

        results = db_session.query(RawJobPosting).filter(RawJobPosting.source == "linkedin").all()
        assert len(results) == 2
        assert all(r.source == "linkedin" for r in results)

    def test_date_filter(self, db_session: Session) -> None:
        """Filter by date range returns only recent jobs."""
        _make_job(db_session, title="Recent", company="X", scraped_at=datetime.now(UTC))
        _make_job(
            db_session,
            title="Old",
            company="Y",
            scraped_at=datetime.now(UTC) - timedelta(days=10),
        )

        cutoff = datetime.now(UTC) - timedelta(days=7)
        results = db_session.query(RawJobPosting).filter(RawJobPosting.scraped_at >= cutoff).all()
        assert len(results) == 1
        assert results[0].title == "Recent"

    def test_search_title(self, db_session: Session) -> None:
        """Search by title substring."""
        _make_job(db_session, title="VP Engineering", company="MegaTech")
        _make_job(db_session, title="Junior Developer", company="SmallCo")

        pattern = "%Engineering%"
        results = db_session.query(RawJobPosting).filter(RawJobPosting.title.ilike(pattern)).all()
        assert len(results) == 1
        assert results[0].title == "VP Engineering"

    def test_search_company(self, db_session: Session) -> None:
        """Search by company substring."""
        _make_job(db_session, title="Job A", company="MegaTech")
        _make_job(db_session, title="Job B", company="SmallCo")

        pattern = "%Mega%"
        results = db_session.query(RawJobPosting).filter(RawJobPosting.company.ilike(pattern)).all()
        assert len(results) == 1
        assert results[0].company == "MegaTech"

    def test_combined_search_title_or_company(self, db_session: Session) -> None:
        """Search matches either title or company."""
        _make_job(db_session, title="Architect", company="AlphaCo")
        _make_job(db_session, title="Manager", company="Architect Inc")
        _make_job(db_session, title="Developer", company="BetaCo")

        pattern = "%Architect%"
        results = (
            db_session.query(RawJobPosting)
            .filter(
                (RawJobPosting.title.ilike(pattern)) | (RawJobPosting.company.ilike(pattern))
            )
            .all()
        )
        assert len(results) == 2

    def test_pagination_offset_limit(self, db_session: Session) -> None:
        """Pagination with offset and limit."""
        for i in range(50):
            _make_job(db_session, title=f"Job {i:03d}", company=f"Corp {i:03d}")

        page_size = 25
        page1 = (
            db_session.query(RawJobPosting)
            .order_by(RawJobPosting.scraped_at.desc())
            .offset(0)
            .limit(page_size)
            .all()
        )
        page2 = (
            db_session.query(RawJobPosting)
            .order_by(RawJobPosting.scraped_at.desc())
            .offset(25)
            .limit(page_size)
            .all()
        )

        assert len(page1) == 25
        assert len(page2) == 25
        # No overlap
        page1_ids = {j.raw_id for j in page1}
        page2_ids = {j.raw_id for j in page2}
        assert page1_ids.isdisjoint(page2_ids)

    def test_ordering_newest_first(self, db_session: Session) -> None:
        """Default ordering is newest first."""
        _make_job(
            db_session, title="Old", company="A", scraped_at=datetime.now(UTC) - timedelta(days=5)
        )
        _make_job(
            db_session, title="New", company="B", scraped_at=datetime.now(UTC)
        )

        results = db_session.query(RawJobPosting).order_by(RawJobPosting.scraped_at.desc()).all()
        assert results[0].title == "New"
        assert results[1].title == "Old"
