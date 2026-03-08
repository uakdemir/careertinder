"""Cover letter generator — D1 of M4.

Generates personalized cover letters by combining job description,
recommended resume text, and Tier 3 evaluation insights.
"""

import json
import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from jobhunter.ai.claude_client import AIClient, AIResponse
from jobhunter.ai.evaluator import load_prompt, render_prompt
from jobhunter.config.schema import AIModelConfig
from jobhunter.db.models import CoverLetter, MatchEvaluation, ProcessedJob, ResumeProfile

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CoverLetterResult:
    """Result of a cover letter generation attempt."""

    success: bool
    letter_id: int | None = None
    cost_usd: float = 0.0
    error: str | None = None


class CoverLetterGenerator:
    """Generates personalized cover letters for evaluated jobs."""

    def __init__(self, session: Session, client: AIClient, model_config: AIModelConfig) -> None:
        self._session = session
        self._client = client
        self._model_config = model_config
        self._system_prompt = load_prompt("cover_letter_system.txt")
        self._user_template = load_prompt("cover_letter_user.txt")

    async def generate(
        self,
        job: ProcessedJob,
        evaluation: MatchEvaluation,
        resume: ResumeProfile,
    ) -> CoverLetterResult:
        """Generate a cover letter for a job using the recommended resume.

        Args:
            job: The processed job to write a cover letter for.
            evaluation: The Tier 3 evaluation with strengths/weaknesses/hints.
            resume: The recommended resume profile.

        Returns:
            CoverLetterResult with letter_id on success.
        """
        if not resume.extracted_text or not resume.extracted_text.strip():
            msg = f"Empty resume text for profile '{resume.label}'"
            logger.error(msg)
            return CoverLetterResult(success=False, error=msg)

        try:
            user_prompt = self._build_user_prompt(job, evaluation, resume)

            response: AIResponse = await self._client.complete(
                system_prompt=self._system_prompt,
                user_prompt=user_prompt,
                model=self._model_config.model,
                max_tokens=self._model_config.max_tokens,
                temperature=self._model_config.temperature,
            )

            content = response.content.strip()
            if not content or len(content) < 50:
                msg = f"AI returned insufficient content ({len(content)} chars)"
                logger.warning(msg)
                return CoverLetterResult(success=False, error=msg)

            if len(content.split()) < 100:
                logger.warning(
                    "Cover letter is short (%d words) for job %d",
                    len(content.split()),
                    job.job_id,
                )

            version = self._deactivate_previous(job.job_id, resume.resume_id)
            letter = self._save(job, resume, content, response, version)
            self._session.commit()

            logger.info(
                "Generated cover letter for job %d (resume=%s, v%d, $%.4f)",
                job.job_id,
                resume.label,
                version,
                response.cost_usd,
            )

            return CoverLetterResult(
                success=True,
                letter_id=letter.letter_id,
                cost_usd=response.cost_usd,
            )

        except Exception as e:
            logger.error("Cover letter generation failed for job %d: %s", job.job_id, e)
            return CoverLetterResult(success=False, error=str(e))

    def _build_user_prompt(
        self,
        job: ProcessedJob,
        evaluation: MatchEvaluation,
        resume: ResumeProfile,
    ) -> str:
        """Render the user prompt template with job/resume/evaluation context.

        Falls back to DS1 raw description if description_clean is empty.
        """
        strengths = json.loads(evaluation.strengths) if evaluation.strengths else []
        weaknesses = json.loads(evaluation.weaknesses) if evaluation.weaknesses else []
        hints = json.loads(evaluation.cover_letter_hints) if evaluation.cover_letter_hints else []

        # Fallback: cleaned description -> raw description from DS1
        description = job.description_clean or ""
        if not description and job.raw_posting:
            description = job.raw_posting.description or ""

        return render_prompt(
            self._user_template,
            job_title=job.title,
            company_name=job.company.name if job.company else "the company",
            job_description=description,
            resume_label=resume.label,
            resume_text=resume.extracted_text,
            strengths="\n".join(f"- {s}" for s in strengths),
            weaknesses="\n".join(f"- {w}" for w in weaknesses),
            cover_letter_hints="\n".join(f"- {h}" for h in hints),
            overall_score=str(evaluation.overall_score or "N/A"),
            fit_category=evaluation.fit_category or "N/A",
        )

    def _deactivate_previous(self, job_id: int, resume_id: int) -> int:
        """Deactivate previous active versions. Returns next version number."""
        existing = (
            self._session.query(CoverLetter)
            .filter_by(job_id=job_id, resume_id=resume_id, is_active=True)
            .all()
        )
        next_version = 1
        for cl in existing:
            cl.is_active = False
            next_version = max(next_version, cl.version + 1)
        return next_version

    def _save(
        self,
        job: ProcessedJob,
        resume: ResumeProfile,
        content: str,
        response: AIResponse,
        version: int,
    ) -> CoverLetter:
        """Persist the generated cover letter to DS5."""
        letter = CoverLetter(
            job_id=job.job_id,
            resume_id=resume.resume_id,
            content=content,
            version=version,
            is_active=True,
            model_used=response.model,
            prompt_template_id="cover_letter_system.txt",
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            tokens_used=response.prompt_tokens + response.completion_tokens,
            cost_usd=response.cost_usd,
        )
        self._session.add(letter)
        self._session.flush()
        return letter
