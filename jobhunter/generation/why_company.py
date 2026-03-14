"""Why-company answer generator — D2 of M4.

Generates concise "Why do I want to work at this company?" answers
using job description and company context.
"""

import json
import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from jobhunter.ai.claude_client import AIClient, AIResponse
from jobhunter.ai.evaluator import load_prompt, render_prompt
from jobhunter.config.schema import AIModelConfig
from jobhunter.db.models import MatchEvaluation, ProcessedJob, WhyCompany

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WhyCompanyResult:
    """Result of a why-company generation attempt."""

    success: bool
    answer_id: int | None = None
    cost_usd: float = 0.0
    error: str | None = None


class WhyCompanyGenerator:
    """Generates "Why this company?" answers for evaluated jobs."""

    def __init__(self, session: Session, client: AIClient, model_config: AIModelConfig) -> None:
        self._session = session
        self._client = client
        self._model_config = model_config
        self._system_prompt = load_prompt("why_company_system.txt")
        self._user_template = load_prompt("why_company_user.txt")

    async def generate(
        self,
        job: ProcessedJob,
        evaluation: MatchEvaluation,
    ) -> WhyCompanyResult:
        """Generate a "why this company?" answer.

        Args:
            job: The processed job.
            evaluation: The Tier 3 evaluation for context.

        Returns:
            WhyCompanyResult with answer_id on success.
        """
        try:
            # no_autoflush prevents premature flush when lazy-loading
            # relationships (e.g. job.company) while the session has dirty state
            with self._session.no_autoflush:
                user_prompt = self._build_user_prompt(job, evaluation)

            response: AIResponse = await self._client.complete(
                system_prompt=self._system_prompt,
                user_prompt=user_prompt,
                model=self._model_config.model,
                max_tokens=self._model_config.max_tokens,
                temperature=self._model_config.temperature,
            )

            content = response.content.strip()
            if not content or len(content) < 30:
                msg = f"AI returned insufficient content ({len(content)} chars)"
                logger.warning(msg)
                return WhyCompanyResult(success=False, error=msg)

            version = self._deactivate_previous(job.job_id)
            answer = self._save(job, content, response, version)
            self._session.commit()

            logger.info(
                "Generated why-company answer for job %d (v%d, $%.4f)",
                job.job_id,
                version,
                response.cost_usd,
            )

            return WhyCompanyResult(
                success=True,
                answer_id=answer.answer_id,
                cost_usd=response.cost_usd,
            )

        except Exception as e:
            logger.error("Why-company generation failed for job %d: %s", job.job_id, e)
            return WhyCompanyResult(success=False, error=str(e))

    def _build_user_prompt(
        self,
        job: ProcessedJob,
        evaluation: MatchEvaluation,
    ) -> str:
        """Render the user prompt template with job and evaluation context.

        Falls back to DS1 raw description if description_clean is empty.
        Includes Company.research_notes when available.
        """
        strengths = json.loads(evaluation.strengths) if evaluation.strengths else []

        # Fallback: cleaned description -> raw description from DS1
        description = job.description_clean or ""
        if not description and job.raw_posting:
            description = job.raw_posting.description or ""

        # Include company research notes if available
        company_context = ""
        if job.company and job.company.research_notes:
            company_context = job.company.research_notes

        return render_prompt(
            self._user_template,
            job_title=job.title,
            company_name=job.company.name if job.company else "the company",
            job_description=description,
            company_context=company_context,
            strengths="\n".join(f"- {s}" for s in strengths),
            fit_category=evaluation.fit_category or "N/A",
            overall_score=str(evaluation.overall_score or "N/A"),
        )

    def _deactivate_previous(self, job_id: int) -> int:
        """Deactivate previous active versions. Returns next version number."""
        existing = (
            self._session.query(WhyCompany)
            .filter_by(job_id=job_id, is_active=True)
            .all()
        )
        next_version = 1
        for wc in existing:
            wc.is_active = False
            next_version = max(next_version, wc.version + 1)
        return next_version

    def _save(
        self,
        job: ProcessedJob,
        content: str,
        response: AIResponse,
        version: int,
    ) -> WhyCompany:
        """Persist the generated answer to DS6."""
        answer = WhyCompany(
            job_id=job.job_id,
            content=content,
            version=version,
            is_active=True,
            model_used=response.model,
            prompt_template_id="why_company_system.txt",
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            tokens_used=response.prompt_tokens + response.completion_tokens,
            cost_usd=response.cost_usd,
        )
        self._session.add(answer)
        self._session.flush()
        return answer
