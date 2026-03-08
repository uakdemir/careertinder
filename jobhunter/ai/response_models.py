"""Pydantic models for parsing and validating AI evaluation responses."""

from pydantic import BaseModel, Field


class Tier2Response(BaseModel):
    """Validated response from Tier 2 AI evaluation."""

    decision: str = Field(pattern=r"^(yes|no|maybe)$")
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(min_length=10, max_length=500)
    flags: list[str] = Field(default_factory=list)


class Tier3Response(BaseModel):
    """Validated response from Tier 3 AI evaluation."""

    overall_score: int = Field(ge=0, le=100)
    fit_category: str = Field(
        pattern=r"^(exceptional_match|strong_match|moderate_match|weak_match|poor_match)$"
    )
    skill_match_score: int = Field(ge=0, le=100)
    seniority_match_score: int = Field(ge=0, le=100)
    remote_compatibility_score: int = Field(ge=0, le=100)
    salary_alignment_score: int = Field(ge=0, le=100)
    strengths: list[str] = Field(min_length=1, max_length=10)
    weaknesses: list[str] = Field(default_factory=list, max_length=10)
    flags: list[str] = Field(default_factory=list)
    reasoning: str = Field(min_length=20, max_length=2000)
    cover_letter_hints: list[str] = Field(default_factory=list)


# Canonical score-to-category mapping (enforced after AI response parsing)
SCORE_TO_CATEGORY: list[tuple[int, str]] = [
    (90, "exceptional_match"),
    (75, "strong_match"),
    (60, "moderate_match"),
    (40, "weak_match"),
    (0, "poor_match"),
]


def score_to_fit_category(score: int) -> str:
    """Map an overall score to its canonical fit_category."""
    for threshold, category in SCORE_TO_CATEGORY:
        if score >= threshold:
            return category
    return "poor_match"
