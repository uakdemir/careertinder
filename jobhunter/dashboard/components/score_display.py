"""Score display components — color-coded score bars and badges."""


def score_color(score: int) -> str:
    """Return 'green', 'orange', or 'red' based on score thresholds."""
    if score >= 75:
        return "green"
    elif score >= 60:
        return "orange"
    return "red"


def score_badge(score: int) -> str:
    """Return a colored markdown score badge."""
    color = score_color(score)
    return f":{color}[{score}]"


def fit_category_label(category: str | None) -> str:
    """Return human-readable fit category."""
    labels = {
        "exceptional_match": "Exceptional",
        "strong_match": "Strong Match",
        "moderate_match": "Moderate",
        "weak_match": "Weak",
        "poor_match": "Poor",
    }
    return labels.get(category or "", category or "—")
