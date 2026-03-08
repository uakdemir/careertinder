"""Tests for M4 content generation pipeline."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.orm import Session

from jobhunter.ai.claude_client import AIResponse
from jobhunter.config.schema import AICostConfig, AIModelConfig, AIModelsConfig
from jobhunter.db.models import (
    ApplicationStatus,
    Company,
    CoverLetter,
    MatchEvaluation,
    ProcessedJob,
    RawJobPosting,
    ResumeProfile,
    WhyCompany,
)
from jobhunter.generation.cover_letter import CoverLetterGenerator, CoverLetterResult
from jobhunter.generation.service import GenerationCostTracker, GenerationRunResult, GenerationService
from jobhunter.generation.why_company import WhyCompanyGenerator, WhyCompanyResult

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_client() -> AsyncMock:
    """Mock AIClient that returns predictable responses."""
    client = AsyncMock()
    client.complete.return_value = AIResponse(
        content="This is a generated cover letter with enough words to pass the minimum "
        "length check. It contains professional language and demonstrates how the "
        "candidate's experience aligns with the role requirements. The letter "
        "addresses specific company attributes and connects them to career goals.",
        model="gpt-4o",
        prompt_tokens=500,
        completion_tokens=400,
        cost_usd=0.0053,
    )
    return client


@pytest.fixture
def model_config() -> AIModelConfig:
    return AIModelConfig(provider="openai", model="gpt-4o", max_tokens=2000, temperature=0.5)


def _make_job_with_eval(db_session: Session) -> tuple[ProcessedJob, MatchEvaluation, ResumeProfile]:
    """Create a full job + company + raw posting + resume + Tier 3 evaluation."""
    company = Company(name="Acme Corp")
    db_session.add(company)
    db_session.flush()

    raw = RawJobPosting(
        source="linkedin",
        source_url="https://example.com/job/1",
        title="Senior Backend Engineer",
        company="Acme Corp",
        description="Build scalable distributed systems using Python and Kubernetes.",
        fingerprint_hash="abc123",
    )
    db_session.add(raw)
    db_session.flush()

    job = ProcessedJob(
        company_id=company.company_id,
        raw_id=raw.raw_id,
        title="Senior Backend Engineer",
        location_policy="remote_worldwide",
        description_clean="Build scalable distributed systems using Python and Kubernetes.",
        application_url="https://example.com/apply/1",
        source_site="linkedin",
        fingerprint_hash="abc123",
        status="evaluated",
    )
    db_session.add(job)
    db_session.flush()

    resume = ResumeProfile(
        label="Architect",
        file_path="data/resumes/architect.pdf",
        file_hash="hash123",
        extracted_text="Experienced software architect with 10+ years in distributed systems.",
        key_skills='["Python", "AWS", "Kubernetes"]',
        experience_summary="Senior architect building cloud platforms",
    )
    db_session.add(resume)
    db_session.flush()

    evaluation = MatchEvaluation(
        job_id=job.job_id,
        resume_id=resume.resume_id,
        tier_evaluated=3,
        overall_score=82,
        fit_category="strong_match",
        skill_match_score=85,
        seniority_match_score=80,
        remote_compatibility_score=90,
        salary_alignment_score=75,
        strengths=json.dumps(["Strong Python experience", "Cloud infrastructure"]),
        weaknesses=json.dumps(["No Go experience"]),
        cover_letter_hints=json.dumps(["Emphasize distributed systems work"]),
        reasoning="Strong match for backend role",
        model_used="claude-sonnet-4-20250514",
        tokens_used=2500,
        cost_usd=0.05,
        is_current=True,
        recommended_resume_id=resume.resume_id,
    )
    db_session.add(evaluation)
    db_session.flush()

    return job, evaluation, resume


# ---------------------------------------------------------------------------
# Cover Letter Generator
# ---------------------------------------------------------------------------


class TestCoverLetterGenerator:
    def test_generate_success(self, db_session: Session, mock_client: AsyncMock, model_config: AIModelConfig,
    ) -> None:
        job, evaluation, resume = _make_job_with_eval(db_session)

        gen = CoverLetterGenerator(db_session, mock_client, model_config)
        result: CoverLetterResult = asyncio.run(gen.generate(job, evaluation, resume))

        assert result.success is True
        assert result.letter_id is not None
        assert result.cost_usd > 0

        # Verify DS5 record
        cl = db_session.query(CoverLetter).filter_by(letter_id=result.letter_id).first()
        assert cl is not None
        assert cl.job_id == job.job_id
        assert cl.resume_id == resume.resume_id
        assert cl.version == 1
        assert cl.is_active is True
        assert cl.model_used == "gpt-4o"
        assert cl.prompt_template_id == "cover_letter_system.txt"

    def test_generate_versioning(self, db_session: Session, mock_client: AsyncMock, model_config: AIModelConfig,
    ) -> None:
        job, evaluation, resume = _make_job_with_eval(db_session)

        gen = CoverLetterGenerator(db_session, mock_client, model_config)

        # First generation
        r1 = asyncio.run(gen.generate(job, evaluation, resume))
        assert r1.success
        assert r1.letter_id is not None

        # Second generation — should deactivate first
        r2 = asyncio.run(gen.generate(job, evaluation, resume))
        assert r2.success
        assert r2.letter_id is not None

        # Old version deactivated
        cl1 = db_session.query(CoverLetter).filter_by(letter_id=r1.letter_id).first()
        assert cl1 is not None
        assert cl1.is_active is False
        assert cl1.version == 1

        # New version active
        cl2 = db_session.query(CoverLetter).filter_by(letter_id=r2.letter_id).first()
        assert cl2 is not None
        assert cl2.is_active is True
        assert cl2.version == 2

    def test_generate_empty_resume(self, db_session: Session, mock_client: AsyncMock, model_config: AIModelConfig,
    ) -> None:
        job, evaluation, resume = _make_job_with_eval(db_session)
        resume.extracted_text = ""

        gen = CoverLetterGenerator(db_session, mock_client, model_config)
        result = asyncio.run(gen.generate(job, evaluation, resume))

        assert result.success is False
        assert "Empty resume text" in (result.error or "")
        mock_client.complete.assert_not_called()

    def test_prompt_includes_hints(self, db_session: Session, mock_client: AsyncMock, model_config: AIModelConfig,
    ) -> None:
        job, evaluation, resume = _make_job_with_eval(db_session)

        gen = CoverLetterGenerator(db_session, mock_client, model_config)
        asyncio.run(gen.generate(job, evaluation, resume))

        # Check the user prompt passed to the client
        call_args = mock_client.complete.call_args
        user_prompt = call_args.kwargs.get("user_prompt", call_args.args[1] if len(call_args.args) > 1 else "")
        assert "Senior Backend Engineer" in user_prompt
        assert "Acme Corp" in user_prompt
        assert "Emphasize distributed systems work" in user_prompt

    def test_description_fallback_to_raw(self, db_session: Session, mock_client: AsyncMock, model_config: AIModelConfig,
    ) -> None:
        job, evaluation, resume = _make_job_with_eval(db_session)
        job.description_clean = ""  # Clear the clean description

        gen = CoverLetterGenerator(db_session, mock_client, model_config)
        asyncio.run(gen.generate(job, evaluation, resume))

        # Should fall back to raw_posting.description
        call_args = mock_client.complete.call_args
        user_prompt = call_args.kwargs.get("user_prompt", call_args.args[1] if len(call_args.args) > 1 else "")
        assert "distributed systems" in user_prompt


# ---------------------------------------------------------------------------
# Why Company Generator
# ---------------------------------------------------------------------------


class TestWhyCompanyGenerator:
    def test_generate_success(self, db_session: Session, mock_client: AsyncMock, model_config: AIModelConfig,
    ) -> None:
        job, evaluation, _resume = _make_job_with_eval(db_session)

        gen = WhyCompanyGenerator(db_session, mock_client, model_config)
        result: WhyCompanyResult = asyncio.run(gen.generate(job, evaluation))

        assert result.success is True
        assert result.answer_id is not None
        assert result.cost_usd > 0

        wc = db_session.query(WhyCompany).filter_by(answer_id=result.answer_id).first()
        assert wc is not None
        assert wc.job_id == job.job_id
        assert wc.version == 1
        assert wc.is_active is True
        assert wc.prompt_template_id == "why_company_system.txt"

    def test_generate_versioning(self, db_session: Session, mock_client: AsyncMock, model_config: AIModelConfig,
    ) -> None:
        job, evaluation, _resume = _make_job_with_eval(db_session)

        gen = WhyCompanyGenerator(db_session, mock_client, model_config)

        r1 = asyncio.run(gen.generate(job, evaluation))
        r2 = asyncio.run(gen.generate(job, evaluation))

        assert r1.success and r2.success

        wc1 = db_session.query(WhyCompany).filter_by(answer_id=r1.answer_id).first()
        assert wc1 is not None
        assert wc1.is_active is False

        wc2 = db_session.query(WhyCompany).filter_by(answer_id=r2.answer_id).first()
        assert wc2 is not None
        assert wc2.is_active is True
        assert wc2.version == 2

    def test_prompt_includes_company(self, db_session: Session, mock_client: AsyncMock, model_config: AIModelConfig,
    ) -> None:
        job, evaluation, _resume = _make_job_with_eval(db_session)

        gen = WhyCompanyGenerator(db_session, mock_client, model_config)
        asyncio.run(gen.generate(job, evaluation))

        call_args = mock_client.complete.call_args
        user_prompt = call_args.kwargs.get("user_prompt", call_args.args[1] if len(call_args.args) > 1 else "")
        assert "Acme Corp" in user_prompt
        assert "Senior Backend Engineer" in user_prompt

    def test_no_company_name_fallback(self, db_session: Session, mock_client: AsyncMock, model_config: AIModelConfig,
    ) -> None:
        job, evaluation, _resume = _make_job_with_eval(db_session)
        # Detach company to test fallback
        job.company = None  # type: ignore[assignment]

        gen = WhyCompanyGenerator(db_session, mock_client, model_config)
        asyncio.run(gen.generate(job, evaluation))

        call_args = mock_client.complete.call_args
        user_prompt = call_args.kwargs.get("user_prompt", call_args.args[1] if len(call_args.args) > 1 else "")
        assert "the company" in user_prompt


# ---------------------------------------------------------------------------
# Generation Service
# ---------------------------------------------------------------------------


class TestGenerationService:
    def _shortlist_job(self, db_session: Session, job_id: int) -> None:
        """Create a 'shortlisted' DS7 record for a job."""
        ds7 = ApplicationStatus(
            job_id=job_id,
            status="shortlisted",
            updated_by="test",
        )
        db_session.add(ds7)
        db_session.flush()

    def test_eligible_jobs_shortlisted_only(self, db_session: Session, mock_client: AsyncMock) -> None:
        job, evaluation, _resume = _make_job_with_eval(db_session)

        ai_config = AIModelsConfig()
        cost_config = AICostConfig(daily_cap_usd=10.0)
        service = GenerationService(db_session, mock_client, ai_config, cost_config)

        # No DS7 record — not eligible
        eligible = service._get_eligible_jobs()
        assert len(eligible) == 0

        # Shortlist the job
        self._shortlist_job(db_session, job.job_id)

        eligible = service._get_eligible_jobs()
        assert len(eligible) == 1
        assert eligible[0][0].job_id == job.job_id

    def test_skips_existing_content(self, db_session: Session, mock_client: AsyncMock, model_config: AIModelConfig,
    ) -> None:
        job, evaluation, resume = _make_job_with_eval(db_session)
        self._shortlist_job(db_session, job.job_id)

        ai_config = AIModelsConfig()
        cost_config = AICostConfig(daily_cap_usd=10.0)
        service = GenerationService(db_session, mock_client, ai_config, cost_config)

        # Create existing content
        cl = CoverLetter(
            job_id=job.job_id,
            resume_id=resume.resume_id,
            content="Existing CL",
            version=1,
            is_active=True,
            model_used="gpt-4o",
            tokens_used=900,
            cost_usd=0.005,
        )
        wc = WhyCompany(
            job_id=job.job_id,
            content="Existing WC",
            version=1,
            is_active=True,
            model_used="gpt-4o",
            tokens_used=500,
            cost_usd=0.003,
        )
        db_session.add_all([cl, wc])
        db_session.flush()

        needs_cl, needs_wc = service._get_content_needs(job.job_id, resume.resume_id)
        assert needs_cl is False
        assert needs_wc is False

    def test_content_needs_partial(self, db_session: Session, mock_client: AsyncMock) -> None:
        job, evaluation, resume = _make_job_with_eval(db_session)

        ai_config = AIModelsConfig()
        cost_config = AICostConfig(daily_cap_usd=10.0)
        service = GenerationService(db_session, mock_client, ai_config, cost_config)

        # Only CL exists, no WC
        cl = CoverLetter(
            job_id=job.job_id,
            resume_id=resume.resume_id,
            content="Existing CL",
            version=1,
            is_active=True,
            model_used="gpt-4o",
            tokens_used=900,
            cost_usd=0.005,
        )
        db_session.add(cl)
        db_session.flush()

        needs_cl, needs_wc = service._get_content_needs(job.job_id, resume.resume_id)
        assert needs_cl is False
        assert needs_wc is True

    def test_run_generates_both(self, db_session: Session, mock_client: AsyncMock) -> None:
        job, evaluation, resume = _make_job_with_eval(db_session)
        self._shortlist_job(db_session, job.job_id)

        ai_config = AIModelsConfig()
        cost_config = AICostConfig(daily_cap_usd=10.0)
        service = GenerationService(db_session, mock_client, ai_config, cost_config)

        result: GenerationRunResult = asyncio.run(service.run())

        assert result.cover_letters_generated == 1
        assert result.why_company_generated == 1
        assert result.errors == 0
        assert result.total_cost_usd > 0

    def test_dry_run_no_writes(self, db_session: Session, mock_client: AsyncMock) -> None:
        job, evaluation, resume = _make_job_with_eval(db_session)
        self._shortlist_job(db_session, job.job_id)

        ai_config = AIModelsConfig()
        cost_config = AICostConfig(daily_cap_usd=10.0)
        service = GenerationService(db_session, mock_client, ai_config, cost_config)

        result = asyncio.run(service.run(dry_run=True))

        assert result.cover_letters_generated == 1  # counted but not actually generated
        assert result.why_company_generated == 1
        mock_client.complete.assert_not_called()

        # No actual records
        assert db_session.query(CoverLetter).count() == 0
        assert db_session.query(WhyCompany).count() == 0


# ---------------------------------------------------------------------------
# Generation Cost Tracker
# ---------------------------------------------------------------------------


class TestGenerationCostTracker:
    def test_aggregates_all_tables(self, db_session: Session) -> None:
        job, evaluation, resume = _make_job_with_eval(db_session)

        # Already has $0.05 from the evaluation
        # Add a cover letter cost
        cl = CoverLetter(
            job_id=job.job_id,
            resume_id=resume.resume_id,
            content="Test CL",
            version=1,
            is_active=True,
            model_used="gpt-4o",
            tokens_used=900,
            cost_usd=0.01,
        )
        wc = WhyCompany(
            job_id=job.job_id,
            content="Test WC",
            version=1,
            is_active=True,
            model_used="gpt-4o",
            tokens_used=500,
            cost_usd=0.005,
        )
        db_session.add_all([cl, wc])
        db_session.flush()

        tracker = GenerationCostTracker(db_session, daily_cap_usd=2.0)
        daily_spend = tracker.get_daily_spend()

        # Evaluation ($0.05) + CL ($0.01) + WC ($0.005)
        assert abs(daily_spend - 0.065) < 0.001


# ---------------------------------------------------------------------------
# Prompt Rendering
# ---------------------------------------------------------------------------


class TestPromptRendering:
    def test_cover_letter_prompt_renders(self) -> None:
        from jobhunter.ai.evaluator import load_prompt, render_prompt

        template = load_prompt("cover_letter_user.txt")
        rendered = render_prompt(
            template,
            job_title="Staff Engineer",
            company_name="TestCo",
            job_description="Build things",
            resume_label="Architect",
            resume_text="Experienced architect",
            strengths="- Strong Python",
            weaknesses="- No Go",
            cover_letter_hints="- Focus on scale",
            overall_score="85",
            fit_category="strong_match",
        )
        assert "{" not in rendered  # No unresolved placeholders
        assert "Staff Engineer" in rendered
        assert "TestCo" in rendered
        assert "Focus on scale" in rendered

    def test_why_company_prompt_renders(self) -> None:
        from jobhunter.ai.evaluator import load_prompt, render_prompt

        template = load_prompt("why_company_user.txt")
        rendered = render_prompt(
            template,
            job_title="Staff Engineer",
            company_name="TestCo",
            company_context="Great engineering culture",
            job_description="Build things",
            strengths="- Strong Python",
            overall_score="85",
            fit_category="strong_match",
        )
        assert "{" not in rendered
        assert "Staff Engineer" in rendered
        assert "Great engineering culture" in rendered


# ---------------------------------------------------------------------------
# OpenAI Client (unit tests — no API calls)
# ---------------------------------------------------------------------------


class TestOpenAIClient:
    def test_cost_estimation(self) -> None:
        openai_client_mod = pytest.importorskip("jobhunter.ai.openai_client")
        client = openai_client_mod.OpenAIClient.__new__(openai_client_mod.OpenAIClient)
        # gpt-4o: $2.50/1M input, $10.00/1M output
        cost = client._estimate_cost("gpt-4o", 1000, 500)
        expected = (1000 * 2.50 + 500 * 10.00) / 1_000_000
        assert abs(cost - expected) < 0.000001

    def test_cost_estimation_unknown_model(self) -> None:
        openai_client_mod = pytest.importorskip("jobhunter.ai.openai_client")
        client = openai_client_mod.OpenAIClient.__new__(openai_client_mod.OpenAIClient)
        cost = client._estimate_cost("unknown-model", 1000, 500)
        assert cost == 0.0
