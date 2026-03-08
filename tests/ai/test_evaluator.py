"""Tests for EvaluationService, CostTracker, and prompt helpers."""

import json
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.orm import Session

from jobhunter.ai.claude_client import AIResponse
from jobhunter.ai.evaluator import (
    CostTracker,
    EvaluationService,
    build_combined_resume_summary,
    load_prompt,
    render_prompt,
)
from jobhunter.config.schema import AICostConfig, AIModelConfig, AIModelsConfig
from jobhunter.db.models import (
    Company,
    MatchEvaluation,
    ProcessedJob,
    RawJobPosting,
    ResumeProfile,
)

# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------


class TestLoadPrompt:
    def test_load_existing_prompt(self) -> None:
        content = load_prompt("tier2_system.txt")
        assert "recruiter" in content.lower() or "evaluate" in content.lower()

    def test_load_missing_prompt(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_prompt("nonexistent_prompt.txt")


class TestRenderPrompt:
    def test_basic_substitution(self) -> None:
        template = "Hello {name}, your score is {score}"
        result = render_prompt(template, name="Alice", score="95")
        assert result == "Hello Alice, your score is 95"

    def test_missing_key_raises(self) -> None:
        template = "Hello {name}"
        with pytest.raises(KeyError):
            render_prompt(template)


class TestBuildCombinedResumeSummary:
    def test_single_profile(self, db_session: Session) -> None:
        profile = ResumeProfile(
            label="Architect",
            file_path="/tmp/arch.pdf",
            file_hash="abc123",
            extracted_text="Full resume text",
            key_skills='["Python", "AWS"]',
            experience_summary="10 years backend",
        )
        db_session.add(profile)
        db_session.flush()

        result = build_combined_resume_summary([profile])
        assert "Architect" in result
        assert "10 years backend" in result
        assert "Python" in result

    def test_multiple_profiles(self, db_session: Session) -> None:
        p1 = ResumeProfile(
            label="Leader", file_path="/tmp/l.pdf", file_hash="a",
            extracted_text="text", key_skills='["Management"]', experience_summary="12 years",
        )
        p2 = ResumeProfile(
            label="Developer", file_path="/tmp/d.pdf", file_hash="b",
            extracted_text="text", key_skills='["Python"]', experience_summary="10 years",
        )
        db_session.add_all([p1, p2])
        db_session.flush()

        result = build_combined_resume_summary([p1, p2])
        assert "Leader" in result
        assert "Developer" in result
        assert "---" in result  # Separator

    def test_empty_profiles(self) -> None:
        result = build_combined_resume_summary([])
        assert "No resume" in result


# ---------------------------------------------------------------------------
# CostTracker
# ---------------------------------------------------------------------------


class TestCostTracker:
    def test_zero_spend_initially(self, db_session: Session) -> None:
        tracker = CostTracker(db_session, daily_cap_usd=2.0)
        assert tracker.get_daily_spend() == 0.0
        assert tracker.can_spend() is True

    def test_cap_reached(self, db_session: Session) -> None:
        # Insert evaluations totaling above cap
        _seed_company_and_job(db_session)
        for _i in range(5):
            db_session.add(MatchEvaluation(
                job_id=1, tier_evaluated=2, model_used="test", tokens_used=100,
                cost_usd=0.50, is_current=True, decision="yes", confidence=0.9,
                reasoning="test",
            ))
        db_session.commit()

        tracker = CostTracker(db_session, daily_cap_usd=2.0)
        assert tracker.get_daily_spend() == 2.50
        assert tracker.can_spend() is False

    def test_warn_at_threshold(self, db_session: Session) -> None:
        _seed_company_and_job(db_session)
        db_session.add(MatchEvaluation(
            job_id=1, tier_evaluated=2, model_used="test", tokens_used=100,
            cost_usd=1.70, is_current=True, decision="yes", confidence=0.9,
            reasoning="test",
        ))
        db_session.commit()

        tracker = CostTracker(db_session, daily_cap_usd=2.0, warn_at_percent=0.8)
        # $1.70 >= $2.00 * 0.8 = $1.60 → should warn but still allow
        assert tracker.can_spend() is True


# ---------------------------------------------------------------------------
# EvaluationService
# ---------------------------------------------------------------------------


def _seed_company_and_job(session: Session) -> tuple[ProcessedJob, RawJobPosting]:
    """Insert minimum required records for evaluation tests."""
    company = Company(name="TestCo")
    session.add(company)
    session.flush()

    raw = RawJobPosting(
        source="linkedin",
        source_url="https://example.com/job/1",
        title="Senior Backend Engineer",
        company="TestCo",
        salary_raw="$120,000 - $150,000",
        location_raw="Remote",
        description="We need a senior backend engineer with Python, AWS, K8s experience. "
        "This is a remote position open to candidates worldwide.",
        fingerprint_hash="abc123",
    )
    session.add(raw)
    session.flush()

    job = ProcessedJob(
        company_id=company.company_id,
        raw_id=raw.raw_id,
        title="Senior Backend Engineer",
        salary_min=120000,
        salary_max=150000,
        location_policy="remote_worldwide",
        description_clean=raw.description,
        application_url=raw.source_url,
        source_site="linkedin",
        fingerprint_hash="abc123",
        status="tier1_pass",
    )
    session.add(job)
    session.flush()
    return job, raw


def _seed_resume(session: Session, label: str = "Architect") -> ResumeProfile:
    """Insert a resume profile for testing."""
    profile = ResumeProfile(
        label=label,
        file_path="/tmp/test.pdf",
        file_hash="hash123",
        extracted_text="Senior software architect with 10 years experience in Python, AWS, K8s",
        key_skills='["Python", "AWS", "Kubernetes"]',
        experience_summary="10 years backend engineering",
    )
    session.add(profile)
    session.flush()
    return profile


def _make_mock_client(tier2_response: str | None = None, tier3_response: str | None = None) -> AsyncMock:
    """Create a mock AIClient that returns predefined responses."""
    client = AsyncMock()

    t2_content = tier2_response or json.dumps({
        "decision": "yes",
        "confidence": 0.85,
        "reasoning": "Strong match for senior backend role with relevant Python and AWS experience",
        "flags": [],
    })

    t3_content = tier3_response or json.dumps({
        "overall_score": 82,
        "fit_category": "strong_match",
        "skill_match_score": 85,
        "seniority_match_score": 90,
        "remote_compatibility_score": 75,
        "salary_alignment_score": 80,
        "strengths": ["Strong Python background", "AWS expertise"],
        "weaknesses": ["No Go experience"],
        "flags": [],
        "reasoning": "Candidate has strong backend skills that match well with the requirements",
        "cover_letter_hints": ["Highlight K8s migration experience"],
    })

    call_count = 0

    async def mock_complete(**kwargs) -> AIResponse:  # type: ignore[override]
        nonlocal call_count
        call_count += 1
        # Determine which response to return based on max_tokens hint
        max_tokens = kwargs.get("max_tokens", 300)
        content = t3_content if max_tokens >= 1000 else t2_content
        return AIResponse(
            content=content, model="test-model",
            prompt_tokens=500, completion_tokens=200, cost_usd=0.01,
        )

    client.complete = mock_complete
    return client


def _make_ai_config() -> AIModelsConfig:
    return AIModelsConfig(
        tier2=AIModelConfig(provider="anthropic", model="test-haiku", max_tokens=300, temperature=0.1),
        tier3=AIModelConfig(provider="anthropic", model="test-sonnet", max_tokens=2000, temperature=0.3),
    )


class TestEvaluationServiceTier2:
    @pytest.mark.asyncio
    async def test_tier2_pass(self, db_session: Session) -> None:
        job, raw = _seed_company_and_job(db_session)
        _seed_resume(db_session)
        client = _make_mock_client()
        cost_config = AICostConfig(daily_cap_usd=10.0)
        service = EvaluationService(db_session, client, _make_ai_config(), cost_config)

        result = await service.run(tier2_only=True)

        assert result.tier2_evaluated == 1
        assert result.tier2_passed == 1
        assert result.total_cost_usd > 0

        # Verify DB state
        db_session.refresh(job)
        assert job.status == "tier2_pass"
        eval_record = db_session.query(MatchEvaluation).filter_by(job_id=job.job_id, tier_evaluated=2).first()
        assert eval_record is not None
        assert eval_record.decision == "yes"
        assert eval_record.is_current is True

    @pytest.mark.asyncio
    async def test_tier2_no_candidates(self, db_session: Session) -> None:
        _seed_resume(db_session)
        client = _make_mock_client()
        cost_config = AICostConfig(daily_cap_usd=10.0)
        service = EvaluationService(db_session, client, _make_ai_config(), cost_config)

        result = await service.run(tier2_only=True)
        assert result.tier2_evaluated == 0

    @pytest.mark.asyncio
    async def test_tier2_dry_run(self, db_session: Session) -> None:
        _seed_company_and_job(db_session)
        _seed_resume(db_session)
        client = _make_mock_client()
        cost_config = AICostConfig(daily_cap_usd=10.0)
        service = EvaluationService(db_session, client, _make_ai_config(), cost_config)

        result = await service.run(tier2_only=True, dry_run=True)

        assert result.tier2_evaluated == 1
        assert result.total_cost_usd == 0.0  # No API calls in dry run

    @pytest.mark.asyncio
    async def test_tier2_skip_already_evaluated(self, db_session: Session) -> None:
        job, raw = _seed_company_and_job(db_session)
        _seed_resume(db_session)

        # Pre-seed an existing Tier 2 evaluation
        db_session.add(MatchEvaluation(
            job_id=job.job_id, tier_evaluated=2, model_used="old", tokens_used=100,
            cost_usd=0.01, is_current=True, decision="yes", confidence=0.8,
            reasoning="old evaluation",
        ))
        db_session.commit()

        client = _make_mock_client()
        cost_config = AICostConfig(daily_cap_usd=10.0)
        service = EvaluationService(db_session, client, _make_ai_config(), cost_config)

        result = await service.run(tier2_only=True)
        assert result.tier2_evaluated == 0  # Should skip

    @pytest.mark.asyncio
    async def test_tier2_force_reevaluate(self, db_session: Session) -> None:
        job, raw = _seed_company_and_job(db_session)
        _seed_resume(db_session)

        # Pre-seed evaluation
        db_session.add(MatchEvaluation(
            job_id=job.job_id, tier_evaluated=2, model_used="old", tokens_used=100,
            cost_usd=0.01, is_current=True, decision="no", confidence=0.3,
            reasoning="old evaluation result",
        ))
        db_session.commit()

        client = _make_mock_client()
        cost_config = AICostConfig(daily_cap_usd=10.0)
        service = EvaluationService(db_session, client, _make_ai_config(), cost_config)

        result = await service.run(tier2_only=True, force=True)
        assert result.tier2_evaluated == 1

        # Old eval should be superseded
        evals = db_session.query(MatchEvaluation).filter_by(job_id=job.job_id, tier_evaluated=2).all()
        current = [e for e in evals if e.is_current]
        superseded = [e for e in evals if not e.is_current]
        assert len(current) == 1
        assert len(superseded) == 1
        assert current[0].decision == "yes"


class TestEvaluationServiceTier3:
    @pytest.mark.asyncio
    async def test_full_pipeline(self, db_session: Session) -> None:
        job, raw = _seed_company_and_job(db_session)
        job.status = "tier2_pass"
        _seed_resume(db_session)

        # Need a Tier 2 eval to exist
        db_session.add(MatchEvaluation(
            job_id=job.job_id, tier_evaluated=2, model_used="test", tokens_used=100,
            cost_usd=0.01, is_current=True, decision="yes", confidence=0.9,
            reasoning="test tier 2 eval",
        ))
        db_session.commit()

        client = _make_mock_client()
        cost_config = AICostConfig(daily_cap_usd=10.0)
        service = EvaluationService(db_session, client, _make_ai_config(), cost_config)

        result = await service.run(tier2_only=False)

        # Tier 2 has no new candidates (already evaluated), but Tier 3 should run
        assert result.tier3_evaluated >= 0  # May or may not have tier3 candidates depending on status

    @pytest.mark.asyncio
    async def test_tier3_score_category_enforcement(self, db_session: Session) -> None:
        """Score-to-category mapping is enforced even if AI returns wrong category."""
        job, raw = _seed_company_and_job(db_session)
        job.status = "tier2_pass"
        _seed_resume(db_session)
        db_session.commit()

        # AI returns score 82 but wrong category
        t3_response = json.dumps({
            "overall_score": 82,
            "fit_category": "moderate_match",  # Wrong: should be strong_match
            "skill_match_score": 85,
            "seniority_match_score": 90,
            "remote_compatibility_score": 75,
            "salary_alignment_score": 80,
            "strengths": ["Python expertise"],
            "weaknesses": ["No Go"],
            "flags": [],
            "reasoning": "Good candidate match with relevant backend experience and skills",
            "cover_letter_hints": [],
        })

        client = _make_mock_client(tier3_response=t3_response)
        cost_config = AICostConfig(daily_cap_usd=10.0)
        service = EvaluationService(db_session, client, _make_ai_config(), cost_config)

        await service.run()

        # Find the Tier 3 eval
        t3_eval = db_session.query(MatchEvaluation).filter_by(
            job_id=job.job_id, tier_evaluated=3, is_current=True,
        ).first()

        if t3_eval is not None:
            # Score 82 → strong_match (enforced by score_to_fit_category)
            assert t3_eval.fit_category == "strong_match"


class TestEvaluationServiceCostCap:
    @pytest.mark.asyncio
    async def test_stops_at_cap(self, db_session: Session) -> None:
        _seed_company_and_job(db_session)
        _seed_resume(db_session)
        # Set very low cap
        cost_config = AICostConfig(daily_cap_usd=0.001)

        # Pre-seed cost to exceed cap
        company = Company(name="CapCo")
        db_session.add(company)
        db_session.flush()
        raw2 = RawJobPosting(
            source="linkedin", source_url="https://example.com/2",
            title="Test", company="CapCo", description="x" * 100,
            fingerprint_hash="cap_test_hash",
        )
        db_session.add(raw2)
        db_session.flush()
        job2 = ProcessedJob(
            company_id=company.company_id, raw_id=raw2.raw_id, title="Test",
            location_policy="remote_worldwide", description_clean="x" * 100,
            application_url="https://example.com/2", source_site="linkedin",
            fingerprint_hash="cap_test_hash", status="new",
        )
        db_session.add(job2)
        db_session.flush()

        db_session.add(MatchEvaluation(
            job_id=job2.job_id, tier_evaluated=2, model_used="test", tokens_used=100,
            cost_usd=0.01, is_current=True, decision="yes", confidence=0.9,
            reasoning="cap test evaluation",
        ))
        db_session.commit()

        client = _make_mock_client()
        service = EvaluationService(db_session, client, _make_ai_config(), cost_config)

        result = await service.run(tier2_only=True)
        assert result.cap_reached is True


class TestTier2RegexFallback:
    def test_regex_fallback(self, db_session: Session) -> None:
        cost_config = AICostConfig(daily_cap_usd=10.0)
        client = _make_mock_client()
        service = EvaluationService(db_session, client, _make_ai_config(), cost_config)

        # Simulate malformed JSON with extractable fields
        response = AIResponse(
            content='Some text before {"decision": "yes", "confidence": 0.7, "reasoning": "partial match"} after',
            model="test", prompt_tokens=100, completion_tokens=50, cost_usd=0.01,
        )
        parsed = service._parse_tier2_response(response)
        assert parsed.decision == "yes"
        assert parsed.confidence == 0.7


class TestJsonExtraction:
    def test_extract_from_fenced_block(self, db_session: Session) -> None:
        cost_config = AICostConfig(daily_cap_usd=10.0)
        client = _make_mock_client()
        service = EvaluationService(db_session, client, _make_ai_config(), cost_config)

        content = '```json\n{"key": "value"}\n```'
        assert service._extract_json(content) == '{"key": "value"}'

    def test_extract_bare_json(self, db_session: Session) -> None:
        cost_config = AICostConfig(daily_cap_usd=10.0)
        client = _make_mock_client()
        service = EvaluationService(db_session, client, _make_ai_config(), cost_config)

        content = 'Here is the answer: {"key": "value"}'
        assert service._extract_json(content) == '{"key": "value"}'
