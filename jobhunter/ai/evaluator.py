"""AI Evaluation Pipeline — Tier 2 + Tier 3 orchestration.

Contains the EvaluationService orchestrator, CostTracker, prompt helpers,
and the full pipeline logic for evaluating jobs against resumes.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from jobhunter.ai.claude_client import AIClient, AIResponse
from jobhunter.ai.response_models import (
    Tier2Response,
    Tier3Response,
    score_to_fit_category,
)
from jobhunter.config.schema import AICostConfig, AIModelsConfig
from jobhunter.db.models import MatchEvaluation, ProcessedJob, RawJobPosting, ResumeProfile

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------


def load_prompt(name: str) -> str:
    """Load a prompt template from the prompts directory."""
    path = PROMPTS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8")


def render_prompt(template: str, **kwargs: str) -> str:
    """Substitute {variables} in a prompt template."""
    return template.format(**kwargs)


def build_combined_resume_summary(profiles: list[ResumeProfile]) -> str:
    """Build a combined resume summary from all profiles for Tier 2 prompts."""
    sections: list[str] = []
    for profile in profiles:
        parts = [f"Profile: {profile.label}"]
        if profile.experience_summary:
            parts.append(f"Experience: {profile.experience_summary}")
        if profile.key_skills and profile.key_skills != "[]":
            parts.append(f"Key Skills: {profile.key_skills}")
        sections.append("\n".join(parts))
    return "\n---\n".join(sections) if sections else "No resume profiles available"


# ---------------------------------------------------------------------------
# Cost tracker
# ---------------------------------------------------------------------------


class CostTracker:
    """Track and enforce AI API spending limits."""

    def __init__(self, session: Session, daily_cap_usd: float = 2.00, warn_at_percent: float = 0.8) -> None:
        self._session = session
        self._daily_cap = daily_cap_usd
        self._warn_at = warn_at_percent

    def get_daily_spend(self) -> float:
        """Sum cost_usd from all DS4 records where evaluated_at is today (UTC)."""
        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        from sqlalchemy import func

        result = (
            self._session.query(func.coalesce(func.sum(MatchEvaluation.cost_usd), 0.0))
            .filter(MatchEvaluation.evaluated_at >= today_start)
            .scalar()
        )
        return float(result)

    def can_spend(self, estimated_cost: float = 0.0) -> bool:
        """Check if estimated_cost would exceed daily cap."""
        current = self.get_daily_spend()
        if current >= self._daily_cap:
            logger.warning("Daily cost cap reached: $%.4f / $%.2f", current, self._daily_cap)
            return False
        if current >= self._daily_cap * self._warn_at:
            logger.warning(
                "Approaching daily cost cap: $%.4f / $%.2f (%.0f%%)",
                current,
                self._daily_cap,
                self._warn_at * 100,
            )
        return True


# ---------------------------------------------------------------------------
# Evaluation run result
# ---------------------------------------------------------------------------


@dataclass
class EvaluationRunResult:
    """Summary of an evaluation run."""

    tier2_evaluated: int = 0
    tier2_passed: int = 0
    tier2_failed: int = 0
    tier2_maybe: int = 0
    tier2_errors: int = 0
    tier3_evaluated: int = 0
    tier3_strong: int = 0
    tier3_moderate: int = 0
    tier3_weak: int = 0
    tier3_errors: int = 0
    total_cost_usd: float = 0.0
    cap_reached: bool = False
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Evaluation service
# ---------------------------------------------------------------------------


class EvaluationService:
    """Orchestrates Tier 2 and Tier 3 AI evaluation pipeline."""

    TIER2_MAYBE_THRESHOLD = 0.4

    def __init__(
        self,
        session: Session,
        client: AIClient,
        ai_config: AIModelsConfig,
        cost_config: AICostConfig,
    ) -> None:
        self._session = session
        self._client = client
        self._ai_config = ai_config
        self._cost_tracker = CostTracker(session, cost_config.daily_cap_usd, cost_config.warn_at_percent)

        # Load prompts at init — fail fast if missing
        self._tier2_system = load_prompt("tier2_system.txt")
        self._tier2_user = load_prompt("tier2_user.txt")
        self._tier3_system = load_prompt("tier3_system.txt")
        self._tier3_user = load_prompt("tier3_user.txt")

    # -------------------------------------------------------------------
    # Main pipeline
    # -------------------------------------------------------------------

    async def run(
        self,
        tier2_only: bool = False,
        force: bool = False,
        dry_run: bool = False,
    ) -> EvaluationRunResult:
        """Run the full evaluation pipeline.

        1. Load tier1_pass + tier1_ambiguous jobs
        2. Skip already-evaluated (unless force=True)
        3. Run Tier 2 on eligible jobs
        4. If not tier2_only: run Tier 3 on tier2_pass + tier2_maybe
        5. Return summary
        """
        result = EvaluationRunResult()

        # Load resumes for prompts
        resumes = self._session.query(ResumeProfile).all()
        if not resumes:
            logger.warning("No resume profiles found. Run 'ingest-resumes' first.")
            return result

        combined_summary = build_combined_resume_summary(resumes)

        # --- Tier 2 ---
        tier2_candidates = self._get_tier2_candidates(force)
        if not tier2_candidates:
            logger.info("No jobs to evaluate at Tier 2")
        else:
            logger.info("Tier 2 candidates: %d jobs", len(tier2_candidates))

        for job, raw_job in tier2_candidates:
            if not self._cost_tracker.can_spend():
                result.cap_reached = True
                logger.warning("Cost cap reached — stopping Tier 2 evaluation")
                break

            if dry_run:
                logger.info("[DRY RUN] Would evaluate Tier 2: %s @ %s", raw_job.title, raw_job.company)
                result.tier2_evaluated += 1
                continue

            if force:
                self._supersede_evaluations(job.job_id, tier=2)

            try:
                evaluation = await self._evaluate_tier2(job, raw_job, combined_summary)
                result.tier2_evaluated += 1
                result.total_cost_usd += evaluation.cost_usd or 0.0

                if job.status == "tier2_pass":
                    result.tier2_passed += 1
                elif job.status == "tier2_maybe":
                    result.tier2_maybe += 1
                else:
                    result.tier2_failed += 1

            except Exception as e:
                logger.error("Tier 2 error for job %d: %s", job.job_id, e)
                job.status = "tier2_error"
                self._session.commit()
                result.tier2_errors += 1
                result.errors.append(f"Tier 2 job {job.job_id}: {e}")

        # --- Tier 3 ---
        if not tier2_only and not dry_run:
            tier3_candidates = self._get_tier3_candidates(force, resumes)
            if not tier3_candidates:
                logger.info("No jobs to evaluate at Tier 3")
            else:
                logger.info("Tier 3 candidates: %d jobs", len(tier3_candidates))

            for job, raw_job, missing_resumes in tier3_candidates:
                if not self._cost_tracker.can_spend():
                    result.cap_reached = True
                    logger.warning("Cost cap reached — stopping Tier 3 evaluation")
                    break

                if force:
                    self._supersede_evaluations(job.job_id, tier=3)
                    missing_resumes = list(resumes)

                evaluated_count = 0
                for resume in missing_resumes:
                    if not self._cost_tracker.can_spend():
                        result.cap_reached = True
                        break

                    try:
                        evaluation = await self._evaluate_tier3(job, raw_job, resume)
                        self._session.add(evaluation)
                        self._session.commit()
                        result.total_cost_usd += evaluation.cost_usd or 0.0
                        evaluated_count += 1
                    except Exception as e:
                        logger.error(
                            "Tier 3 error for job %d, resume %d: %s",
                            job.job_id,
                            resume.resume_id,
                            e,
                        )
                        result.tier3_errors += 1
                        result.errors.append(f"Tier 3 job {job.job_id} resume {resume.resume_id}: {e}")

                if evaluated_count > 0:
                    result.tier3_evaluated += 1
                    self._reconcile_tier3_recommendation(job)

                    # Check if all resumes now have current evaluations
                    current_count = (
                        self._session.query(MatchEvaluation)
                        .filter_by(job_id=job.job_id, tier_evaluated=3, is_current=True)
                        .count()
                    )
                    if current_count >= len(resumes):
                        job.status = "evaluated"
                        self._session.commit()

                        # Count by score
                        best = (
                            self._session.query(MatchEvaluation)
                            .filter_by(job_id=job.job_id, tier_evaluated=3, is_current=True)
                            .order_by(MatchEvaluation.overall_score.desc())
                            .first()
                        )
                        if best and best.overall_score is not None:
                            if best.overall_score >= 75:
                                result.tier3_strong += 1
                            elif best.overall_score >= 60:
                                result.tier3_moderate += 1
                            else:
                                result.tier3_weak += 1

        elif tier2_only and not dry_run:
            logger.info("Tier 2 only mode — skipping Tier 3")

        return result

    # -------------------------------------------------------------------
    # Candidate selection
    # -------------------------------------------------------------------

    def _get_tier2_candidates(self, force: bool) -> list[tuple[ProcessedJob, RawJobPosting]]:
        """Load jobs eligible for Tier 2 evaluation."""
        query = (
            self._session.query(ProcessedJob, RawJobPosting)
            .join(RawJobPosting, ProcessedJob.raw_id == RawJobPosting.raw_id)
            .filter(ProcessedJob.status.in_(["tier1_pass", "tier1_ambiguous"]))
        )

        if not force:
            # Skip jobs that already have a current Tier 2 evaluation
            from sqlalchemy import select

            evaluated_ids = (
                select(MatchEvaluation.job_id)
                .where(MatchEvaluation.tier_evaluated == 2, MatchEvaluation.is_current == True)  # noqa: E712
                .scalar_subquery()
            )
            query = query.filter(~ProcessedJob.job_id.in_(evaluated_ids))

        rows: list[tuple[ProcessedJob, RawJobPosting]] = query.all()  # type: ignore[assignment]
        return rows

    def _get_tier3_candidates(
        self, force: bool, resumes: list[ResumeProfile]
    ) -> list[tuple[ProcessedJob, RawJobPosting, list[ResumeProfile]]]:
        """Load jobs eligible for Tier 3 evaluation, with missing resume list."""
        query = (
            self._session.query(ProcessedJob, RawJobPosting)
            .join(RawJobPosting, ProcessedJob.raw_id == RawJobPosting.raw_id)
            .filter(ProcessedJob.status.in_(["tier2_pass", "tier2_maybe"]))
        )

        candidates: list[tuple[ProcessedJob, RawJobPosting, list[ResumeProfile]]] = []
        for job, raw_job in query.all():
            if force:
                candidates.append((job, raw_job, list(resumes)))
                continue

            # Per-resume skip logic: find which resumes are missing current evaluations
            existing_resume_ids = {
                r[0]
                for r in self._session.query(MatchEvaluation.resume_id)
                .filter_by(job_id=job.job_id, tier_evaluated=3, is_current=True)
                .all()
            }
            missing = [r for r in resumes if r.resume_id not in existing_resume_ids]
            if missing:
                candidates.append((job, raw_job, missing))

        return candidates

    # -------------------------------------------------------------------
    # Tier 2 evaluation
    # -------------------------------------------------------------------

    async def _evaluate_tier2(
        self,
        job: ProcessedJob,
        raw_job: RawJobPosting,
        resume_summary: str,
    ) -> MatchEvaluation:
        """Run Tier 2 evaluation on a single job."""
        description = raw_job.description[:1500] if raw_job.description else ""
        if not description.strip():
            job.status = "tier2_error"
            self._session.commit()
            raise ValueError(f"Empty description for job {job.job_id}")

        salary = raw_job.salary_raw or "Not specified"
        location = raw_job.location_raw or "Not specified"

        user_prompt = render_prompt(
            self._tier2_user,
            job_title=raw_job.title,
            company=raw_job.company,
            location=location,
            salary=salary,
            description=description,
            resume_summary=resume_summary,
        )

        tier2_config = self._ai_config.tier2
        response = await self._client.complete(
            system_prompt=self._tier2_system,
            user_prompt=user_prompt,
            model=tier2_config.model,
            max_tokens=tier2_config.max_tokens,
            temperature=tier2_config.temperature,
        )

        parsed = self._parse_tier2_response(response)

        # Map decision to status
        if parsed.decision == "yes":
            job.status = "tier2_pass"
        elif parsed.decision == "maybe" and parsed.confidence >= self.TIER2_MAYBE_THRESHOLD:
            job.status = "tier2_maybe"
        else:
            job.status = "tier2_fail"

        evaluation = MatchEvaluation(
            job_id=job.job_id,
            resume_id=None,
            tier_evaluated=2,
            decision=parsed.decision,
            confidence=parsed.confidence,
            reasoning=parsed.reasoning,
            flags=json.dumps(parsed.flags),
            model_used=response.model,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            tokens_used=response.prompt_tokens + response.completion_tokens,
            cost_usd=response.cost_usd,
            is_current=True,
        )

        self._session.add(evaluation)
        self._session.commit()
        return evaluation

    def _parse_tier2_response(self, response: AIResponse) -> Tier2Response:
        """Parse Tier 2 AI response, with regex fallback."""
        try:
            # Try to extract JSON from response (may have markdown fences)
            json_str = self._extract_json(response.content)
            data = json.loads(json_str)
            return Tier2Response(**data)
        except Exception:
            logger.warning("Tier 2 JSON parsing failed, attempting regex fallback")
            return self._tier2_regex_fallback(response.content)

    def _tier2_regex_fallback(self, content: str) -> Tier2Response:
        """Extract Tier 2 decision/confidence from raw text via regex."""
        decision_match = re.search(r'"decision"\s*:\s*"(yes|no|maybe)"', content, re.IGNORECASE)
        confidence_match = re.search(r'"confidence"\s*:\s*([\d.]+)', content)
        reasoning_match = re.search(r'"reasoning"\s*:\s*"([^"]+)"', content)

        if not decision_match:
            raise ValueError("Cannot extract decision from AI response")

        decision = decision_match.group(1).lower()
        confidence = float(confidence_match.group(1)) if confidence_match else 0.5
        reasoning = reasoning_match.group(1) if reasoning_match else "Extracted via regex fallback"

        return Tier2Response(
            decision=decision,
            confidence=confidence,
            reasoning=reasoning,
            flags=["regex_fallback"],
        )

    # -------------------------------------------------------------------
    # Tier 3 evaluation
    # -------------------------------------------------------------------

    async def _evaluate_tier3(
        self,
        job: ProcessedJob,
        raw_job: RawJobPosting,
        resume: ResumeProfile,
    ) -> MatchEvaluation:
        """Run Tier 3 deep evaluation for one job x one resume."""
        description = raw_job.description[:8000] if raw_job.description else ""
        salary = raw_job.salary_raw or "Not specified"
        location = raw_job.location_raw or "Not specified"
        resume_text = resume.extracted_text or "No resume text available"
        if not resume_text.strip():
            logger.warning("Empty resume text for profile '%s'", resume.label)
            resume_text = "No resume text available"

        user_prompt = render_prompt(
            self._tier3_user,
            job_title=raw_job.title,
            company=raw_job.company,
            location=location,
            salary=salary,
            description=description,
            resume_label=resume.label,
            resume_text=resume_text,
        )

        tier3_config = self._ai_config.tier3
        response = await self._client.complete(
            system_prompt=self._tier3_system,
            user_prompt=user_prompt,
            model=tier3_config.model,
            max_tokens=tier3_config.max_tokens,
            temperature=tier3_config.temperature,
        )

        parsed = self._parse_tier3_response(response)

        # Enforce canonical score-to-category mapping
        canonical_category = score_to_fit_category(parsed.overall_score)
        if parsed.fit_category != canonical_category:
            logger.warning(
                "AI category '%s' disagrees with score %d → '%s'; using score-derived",
                parsed.fit_category,
                parsed.overall_score,
                canonical_category,
            )

        return MatchEvaluation(
            job_id=job.job_id,
            resume_id=resume.resume_id,
            tier_evaluated=3,
            overall_score=parsed.overall_score,
            fit_category=canonical_category,
            skill_match_score=parsed.skill_match_score,
            seniority_match_score=parsed.seniority_match_score,
            remote_compatibility_score=parsed.remote_compatibility_score,
            salary_alignment_score=parsed.salary_alignment_score,
            strengths=json.dumps(parsed.strengths),
            weaknesses=json.dumps(parsed.weaknesses),
            flags=json.dumps(parsed.flags),
            reasoning=parsed.reasoning,
            cover_letter_hints=json.dumps(parsed.cover_letter_hints),
            model_used=response.model,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            tokens_used=response.prompt_tokens + response.completion_tokens,
            cost_usd=response.cost_usd,
            is_current=True,
        )

    def _parse_tier3_response(self, response: AIResponse) -> Tier3Response:
        """Parse Tier 3 AI response."""
        json_str = self._extract_json(response.content)
        data = json.loads(json_str)
        return Tier3Response(**data)

    # -------------------------------------------------------------------
    # Recommendation reconciliation
    # -------------------------------------------------------------------

    def _reconcile_tier3_recommendation(self, job: ProcessedJob) -> None:
        """Load all current Tier 3 evals for a job, recompute best overall_score,
        and update recommended_resume_id on all current rows."""
        current_evals = (
            self._session.query(MatchEvaluation)
            .filter_by(job_id=job.job_id, tier_evaluated=3, is_current=True)
            .all()
        )
        if not current_evals:
            return
        best = max(current_evals, key=lambda e: e.overall_score or 0)
        for ev in current_evals:
            ev.recommended_resume_id = best.resume_id
        self._session.commit()

    # -------------------------------------------------------------------
    # Force persistence (supersede old records)
    # -------------------------------------------------------------------

    def _supersede_evaluations(self, job_id: int, tier: int) -> None:
        """Mark existing current evaluations as superseded for --force runs."""
        self._session.query(MatchEvaluation).filter_by(
            job_id=job_id, tier_evaluated=tier, is_current=True
        ).update({"is_current": False})
        self._session.commit()

    # -------------------------------------------------------------------
    # JSON extraction helpers
    # -------------------------------------------------------------------

    @staticmethod
    def _extract_json(content: str) -> str:
        """Extract JSON from AI response, handling markdown code fences."""
        # Try to extract from ```json ... ``` blocks
        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
        if fence_match:
            return fence_match.group(1).strip()

        # Try to find a JSON object directly
        brace_match = re.search(r"\{.*\}", content, re.DOTALL)
        if brace_match:
            return brace_match.group(0)

        return content.strip()
