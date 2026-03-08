"""Generation service orchestrator — D4 of M4.

Selects eligible jobs (evaluated + shortlisted), dispatches cover letter
and why-company generation, and tracks combined cost.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from jobhunter.ai.claude_client import AIClient
from jobhunter.ai.evaluator import CostTracker
from jobhunter.config.schema import AICostConfig, AIModelsConfig
from jobhunter.db.models import (
    CoverLetter,
    MatchEvaluation,
    ProcessedJob,
    ResumeProfile,
    WhyCompany,
)
from jobhunter.generation.cover_letter import CoverLetterGenerator
from jobhunter.generation.why_company import WhyCompanyGenerator

logger = logging.getLogger(__name__)


@dataclass
class GenerationRunResult:
    """Summary of a generation run."""

    cover_letters_generated: int = 0
    why_company_generated: int = 0
    cover_letters_skipped: int = 0
    why_company_skipped: int = 0
    errors: int = 0
    total_cost_usd: float = 0.0
    cap_reached: bool = False
    error_details: list[str] = field(default_factory=list)


class GenerationCostTracker(CostTracker):
    """Extends CostTracker to aggregate DS4 + DS5 + DS6 daily spend."""

    def get_daily_spend(self) -> float:
        """Sum cost_usd from DS4, DS5, and DS6 for today (UTC)."""
        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

        eval_cost = (
            self._session.query(func.coalesce(func.sum(MatchEvaluation.cost_usd), 0.0))
            .filter(MatchEvaluation.evaluated_at >= today_start)
            .scalar()
        )
        cl_cost = (
            self._session.query(func.coalesce(func.sum(CoverLetter.cost_usd), 0.0))
            .filter(CoverLetter.generated_at >= today_start)
            .scalar()
        )
        wc_cost = (
            self._session.query(func.coalesce(func.sum(WhyCompany.cost_usd), 0.0))
            .filter(WhyCompany.generated_at >= today_start)
            .scalar()
        )
        return float(eval_cost) + float(cl_cost) + float(wc_cost)


class GenerationService:
    """Orchestrates content generation for shortlisted jobs."""

    def __init__(
        self,
        session: Session,
        client: AIClient,
        ai_config: AIModelsConfig,
        cost_config: AICostConfig,
    ) -> None:
        self._session = session
        self._cost_tracker = GenerationCostTracker(
            session, cost_config.daily_cap_usd, cost_config.warn_at_percent
        )
        self._cl_generator = CoverLetterGenerator(session, client, ai_config.content_gen)
        self._wc_generator = WhyCompanyGenerator(session, client, ai_config.content_gen)

    async def run(
        self,
        force: bool = False,
        dry_run: bool = False,
    ) -> GenerationRunResult:
        """Run batch generation for all eligible jobs.

        Eligible = ProcessedJob.status == 'evaluated' AND
                   latest DS7 status == 'shortlisted'.

        Args:
            force: Regenerate even if content already exists.
            dry_run: Report what would be generated without making API calls.

        Returns:
            GenerationRunResult summary.
        """
        result = GenerationRunResult()

        eligible = self._get_eligible_jobs()
        if not eligible:
            logger.info("No eligible jobs for content generation")
            return result

        logger.info("Content generation: %d eligible jobs", len(eligible))

        for job, evaluation, resume in eligible:
            needs_cl, needs_wc = self._get_content_needs(job.job_id, resume.resume_id)

            if force:
                needs_cl = True
                needs_wc = True

            if not needs_cl and not needs_wc:
                result.cover_letters_skipped += 1
                result.why_company_skipped += 1
                continue

            if dry_run:
                if needs_cl:
                    logger.info(
                        "[DRY RUN] Would generate cover letter: %s @ %s (resume=%s)",
                        job.title,
                        job.company.name if job.company else "?",
                        resume.label,
                    )
                if needs_wc:
                    logger.info(
                        "[DRY RUN] Would generate why-company: %s @ %s",
                        job.title,
                        job.company.name if job.company else "?",
                    )
                if needs_cl:
                    result.cover_letters_generated += 1
                else:
                    result.cover_letters_skipped += 1
                if needs_wc:
                    result.why_company_generated += 1
                else:
                    result.why_company_skipped += 1
                continue

            # --- Cover letter ---
            if needs_cl:
                if not self._cost_tracker.can_spend():
                    result.cap_reached = True
                    logger.warning("Cost cap reached — stopping generation")
                    break

                cl_result = await self._cl_generator.generate(job, evaluation, resume)
                if cl_result.success:
                    result.cover_letters_generated += 1
                    result.total_cost_usd += cl_result.cost_usd
                else:
                    result.errors += 1
                    result.error_details.append(
                        f"CL job {job.job_id}: {cl_result.error}"
                    )
            else:
                result.cover_letters_skipped += 1

            # --- Why company ---
            if needs_wc:
                if not self._cost_tracker.can_spend():
                    result.cap_reached = True
                    logger.warning("Cost cap reached — stopping generation")
                    break

                wc_result = await self._wc_generator.generate(job, evaluation)
                if wc_result.success:
                    result.why_company_generated += 1
                    result.total_cost_usd += wc_result.cost_usd
                else:
                    result.errors += 1
                    result.error_details.append(
                        f"WC job {job.job_id}: {wc_result.error}"
                    )
            else:
                result.why_company_skipped += 1

        return result

    def _get_eligible_jobs(self) -> list[tuple[ProcessedJob, MatchEvaluation, ResumeProfile]]:
        """Load jobs eligible for generation.

        Returns tuples of (job, best_evaluation, recommended_resume).
        Only includes jobs with:
          - ProcessedJob.status == 'evaluated'
          - Latest DS7 ApplicationStatus.status == 'shortlisted'
          - A current Tier 3 MatchEvaluation with recommended_resume_id
        """
        from jobhunter.dashboard.components.status_actions import latest_user_status_subquery

        latest_ds7 = latest_user_status_subquery()

        # Jobs that are evaluated and shortlisted
        jobs = (
            self._session.query(ProcessedJob)
            .join(latest_ds7, ProcessedJob.job_id == latest_ds7.c.job_id)
            .filter(
                ProcessedJob.status == "evaluated",
                latest_ds7.c.user_status == "shortlisted",
            )
            .all()
        )

        results: list[tuple[ProcessedJob, MatchEvaluation, ResumeProfile]] = []
        for job in jobs:
            # Find the best current Tier 3 evaluation with a recommended resume
            evaluation = (
                self._session.query(MatchEvaluation)
                .filter_by(job_id=job.job_id, tier_evaluated=3, is_current=True)
                .filter(MatchEvaluation.recommended_resume_id.isnot(None))
                .order_by(MatchEvaluation.overall_score.desc())
                .first()
            )
            if not evaluation:
                logger.warning(
                    "Job %d is shortlisted but has no current Tier 3 evaluation — skipping",
                    job.job_id,
                )
                continue

            resume = (
                self._session.query(ResumeProfile)
                .filter_by(resume_id=evaluation.recommended_resume_id)
                .first()
            )
            if not resume:
                logger.error(
                    "Recommended resume %d not found for job %d — skipping",
                    evaluation.recommended_resume_id,
                    job.job_id,
                )
                continue

            results.append((job, evaluation, resume))

        return results

    def _get_content_needs(self, job_id: int, resume_id: int) -> tuple[bool, bool]:
        """Check which artifacts are missing for this job.

        Returns:
            (needs_cover_letter, needs_why_company) — True if the artifact
            does not have an active row.
        """
        has_cl = (
            self._session.query(CoverLetter)
            .filter_by(job_id=job_id, resume_id=resume_id, is_active=True)
            .first()
            is not None
        )
        has_wc = (
            self._session.query(WhyCompany)
            .filter_by(job_id=job_id, is_active=True)
            .first()
            is not None
        )
        return (not has_cl, not has_wc)
