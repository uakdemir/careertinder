"""Tests for AI response models and score-to-category mapping."""

import pytest
from pydantic import ValidationError

from jobhunter.ai.response_models import (
    SCORE_TO_CATEGORY,
    Tier2Response,
    Tier3Response,
    score_to_fit_category,
)


class TestTier2Response:
    def test_valid_yes(self) -> None:
        r = Tier2Response(decision="yes", confidence=0.9, reasoning="Good match for the role")
        assert r.decision == "yes"
        assert r.confidence == 0.9
        assert r.flags == []

    def test_valid_no(self) -> None:
        r = Tier2Response(decision="no", confidence=0.2, reasoning="Not relevant to candidate")
        assert r.decision == "no"

    def test_valid_maybe(self) -> None:
        r = Tier2Response(decision="maybe", confidence=0.5, reasoning="Partial match, unclear seniority")
        assert r.decision == "maybe"

    def test_invalid_decision(self) -> None:
        with pytest.raises(ValidationError):
            Tier2Response(decision="unsure", confidence=0.5, reasoning="Some reasoning text here")

    def test_confidence_bounds(self) -> None:
        with pytest.raises(ValidationError):
            Tier2Response(decision="yes", confidence=1.5, reasoning="Over confidence text")
        with pytest.raises(ValidationError):
            Tier2Response(decision="yes", confidence=-0.1, reasoning="Negative confidence text")

    def test_reasoning_too_short(self) -> None:
        with pytest.raises(ValidationError):
            Tier2Response(decision="yes", confidence=0.9, reasoning="short")

    def test_with_flags(self) -> None:
        r = Tier2Response(
            decision="yes", confidence=0.8,
            reasoning="Good match but salary unclear",
            flags=["salary_unclear", "regex_fallback"],
        )
        assert len(r.flags) == 2


class TestTier3Response:
    def test_valid_response(self) -> None:
        r = Tier3Response(
            overall_score=82,
            fit_category="strong_match",
            skill_match_score=85,
            seniority_match_score=90,
            remote_compatibility_score=75,
            salary_alignment_score=80,
            strengths=["Strong Python experience", "K8s expertise"],
            weaknesses=["No Go experience"],
            reasoning="Candidate has strong backend skills matching requirements closely",
        )
        assert r.overall_score == 82
        assert r.fit_category == "strong_match"
        assert len(r.strengths) == 2

    def test_invalid_score_range(self) -> None:
        with pytest.raises(ValidationError):
            Tier3Response(
                overall_score=101,
                fit_category="strong_match",
                skill_match_score=85,
                seniority_match_score=90,
                remote_compatibility_score=75,
                salary_alignment_score=80,
                strengths=["Good"],
                reasoning="This is a valid reasoning text here",
            )

    def test_invalid_fit_category(self) -> None:
        with pytest.raises(ValidationError):
            Tier3Response(
                overall_score=82,
                fit_category="great_match",
                skill_match_score=85,
                seniority_match_score=90,
                remote_compatibility_score=75,
                salary_alignment_score=80,
                strengths=["Good"],
                reasoning="This is a valid reasoning text here",
            )

    def test_strengths_required(self) -> None:
        with pytest.raises(ValidationError):
            Tier3Response(
                overall_score=50,
                fit_category="weak_match",
                skill_match_score=40,
                seniority_match_score=50,
                remote_compatibility_score=60,
                salary_alignment_score=70,
                strengths=[],
                reasoning="This is a valid reasoning text here",
            )


class TestScoreToFitCategory:
    @pytest.mark.parametrize(
        "score,expected",
        [
            (100, "exceptional_match"),
            (90, "exceptional_match"),
            (89, "strong_match"),
            (75, "strong_match"),
            (74, "moderate_match"),
            (60, "moderate_match"),
            (59, "weak_match"),
            (40, "weak_match"),
            (39, "poor_match"),
            (0, "poor_match"),
        ],
    )
    def test_score_boundaries(self, score: int, expected: str) -> None:
        assert score_to_fit_category(score) == expected

    def test_score_to_category_table_sorted(self) -> None:
        thresholds = [t for t, _ in SCORE_TO_CATEGORY]
        assert thresholds == sorted(thresholds, reverse=True)
