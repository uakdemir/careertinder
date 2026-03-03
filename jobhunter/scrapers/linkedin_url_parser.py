"""Parse LinkedIn search URLs into structured HarvestAPI actor parameters.

Convenience tool: if parsing breaks due to LinkedIn URL format changes,
users can enter structured fields manually in the dashboard.
"""

import logging
from urllib.parse import parse_qs, urlparse

from jobhunter.config.schema import LinkedInSearchProfile

logger = logging.getLogger(__name__)

# LinkedIn URL parameter → experience level enum mapping
_EXPERIENCE_MAP: dict[str, str] = {
    "1": "internship",
    "2": "entry",
    "3": "associate",
    "4": "mid-senior",
    "5": "director",
    "6": "executive",
}

# LinkedIn URL parameter → workplace type mapping
_WORKPLACE_MAP: dict[str, str] = {
    "1": "office",
    "2": "remote",
    "3": "hybrid",
}

# LinkedIn URL parameter → posted limit mapping
_TIME_POSTED_MAP: dict[str, str] = {
    "r3600": "1h",
    "r86400": "24h",
    "r604800": "week",
    "r2592000": "month",
}

# Salary filter → HarvestAPI salary enum (approximate mapping)
_SALARY_MAP: dict[str, str] = {
    "1": "40k+",
    "2": "60k+",
    "3": "80k+",
    "4": "100k+",
    "5": "120k+",
    "6": "140k+",
    "7": "160k+",
    "8": "180k+",
    "9": "200k+",
}


def parse_linkedin_url(url: str, label: str = "") -> LinkedInSearchProfile | None:
    """Parse a LinkedIn job search URL into a LinkedInSearchProfile.

    Returns None if the URL cannot be parsed (not a LinkedIn jobs URL).
    Missing fields get sensible defaults.
    """
    try:
        parsed = urlparse(url)
        if "linkedin.com" not in parsed.netloc:
            logger.warning("Not a LinkedIn URL: %s", url)
            return None

        params = parse_qs(parsed.query)

        # Extract keywords → job_titles
        keywords = params.get("keywords", [""])[0]
        job_titles = [keywords] if keywords else []

        # Extract location
        location = params.get("location", [""])[0]
        locations = [location] if location else []

        # Extract workplace type (f_WT)
        wt_codes = params.get("f_WT", [""])[0].split(",")
        workplace_type = [_WORKPLACE_MAP[c] for c in wt_codes if c in _WORKPLACE_MAP]
        if not workplace_type:
            workplace_type = ["remote"]

        # Extract experience level (f_E)
        exp_codes = params.get("f_E", [""])[0].split(",")
        experience_level = [_EXPERIENCE_MAP[c] for c in exp_codes if c in _EXPERIENCE_MAP]

        # Extract time posted (f_TPR)
        tpr = params.get("f_TPR", [None])[0]
        posted_limit = _TIME_POSTED_MAP.get(tpr, None) if tpr else None

        # Extract salary filter (f_SB2) — LinkedIn uses numeric codes
        sb2 = params.get("f_SB2", [None])[0]
        salary = _SALARY_MAP.get(sb2, None) if sb2 else None

        auto_label = label or _build_auto_label(job_titles, locations, workplace_type)

        return LinkedInSearchProfile(
            label=auto_label,
            job_titles=job_titles,
            locations=locations,
            workplace_type=workplace_type,
            experience_level=experience_level,
            salary=salary,
            posted_limit=posted_limit,
        )
    except Exception:
        logger.warning("Failed to parse LinkedIn URL: %s", url, exc_info=True)
        return None


def build_linkedin_url(profile: LinkedInSearchProfile) -> str:
    """Build a LinkedIn search URL from a structured profile (for display/reference)."""
    parts = ["https://www.linkedin.com/jobs/search/?"]
    params: list[str] = []

    if profile.job_titles:
        params.append(f"keywords={profile.job_titles[0]}")

    if profile.locations:
        params.append(f"location={profile.locations[0]}")

    # Reverse-map workplace type
    wt_reverse = {v: k for k, v in _WORKPLACE_MAP.items()}
    wt_codes = [wt_reverse[wt] for wt in profile.workplace_type if wt in wt_reverse]
    if wt_codes:
        params.append(f"f_WT={','.join(wt_codes)}")

    # Reverse-map experience level
    exp_reverse = {v: k for k, v in _EXPERIENCE_MAP.items()}
    exp_codes = [exp_reverse[e] for e in profile.experience_level if e in exp_reverse]
    if exp_codes:
        params.append(f"f_E={','.join(exp_codes)}")

    # Reverse-map posted limit
    tpr_reverse = {v: k for k, v in _TIME_POSTED_MAP.items()}
    if profile.posted_limit and profile.posted_limit in tpr_reverse:
        params.append(f"f_TPR={tpr_reverse[profile.posted_limit]}")

    params.append("sortBy=DD")
    return parts[0] + "&".join(params)


def _build_auto_label(
    job_titles: list[str], locations: list[str], workplace_type: list[str]
) -> str:
    """Generate a human-readable label from search parameters."""
    title_part = job_titles[0] if job_titles else "All Jobs"
    loc_part = locations[0] if locations else ("Remote" if "remote" in workplace_type else "Any Location")
    return f"{title_part} — {loc_part}"
