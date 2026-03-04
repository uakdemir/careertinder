"""Parse LinkedIn search URLs into structured search profile parameters.

Convenience tool: if parsing breaks due to LinkedIn URL format changes,
users can enter structured fields manually in the dashboard.

Compatible with valig/linkedin-jobs-scraper actor.
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

# LinkedIn job function codes (f_F parameter)
# These are passed directly to valig via urlParam
_JOB_FUNCTION_NAMES: dict[str, str] = {
    "it": "Information Technology",
    "eng": "Engineering",
    "prjm": "Project Management",
    "sale": "Sales",
    "mktg": "Marketing",
    "fin": "Finance",
    "hr": "Human Resources",
    "ops": "Operations",
    "cons": "Consulting",
    "dsgn": "Design",
    "prod": "Product Management",
    "data": "Data Science",
    "rsrch": "Research",
    "qa": "Quality Assurance",
    "supp": "Customer Support",
    "admn": "Administrative",
    "bd": "Business Development",
    "legal": "Legal",
}

# Common LinkedIn geoIds for reference
_GEO_ID_NAMES: dict[str, str] = {
    "102105699": "Turkey",
    "102095887": "California, US",
    "103644278": "United States",
    "101165590": "United Kingdom",
    "101282230": "Germany",
    "102299470": "India",
    "106155005": "New York, US",
    "100364837": "Remote (Worldwide)",
}


def parse_linkedin_url(url: str, label: str = "") -> LinkedInSearchProfile | None:
    """Parse a LinkedIn job search URL into a LinkedInSearchProfile.

    Returns None if the URL cannot be parsed (not a LinkedIn jobs URL).
    Missing fields get sensible defaults.

    Supported URL parameters:
      - keywords: Search terms → job_titles
      - location: Location text → locations
      - geoId: LinkedIn geographic ID → geo_id
      - f_E: Experience levels (1-6) → experience_level
      - f_WT: Workplace type (1-3) → workplace_type
      - f_F: Job functions (it, eng, prjm, etc.) → job_functions
      - f_TPR: Time posted (r86400, r604800, etc.) → posted_limit
      - f_JT: Contract type → contract_type
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

        # Extract geoId (LinkedIn's geographic identifier)
        geo_id = params.get("geoId", [None])[0]

        # Extract workplace type (f_WT)
        wt_codes = params.get("f_WT", [""])[0].split(",")
        workplace_type = [_WORKPLACE_MAP[c] for c in wt_codes if c in _WORKPLACE_MAP]
        if not workplace_type:
            workplace_type = ["remote"]

        # Extract experience level (f_E)
        exp_codes = params.get("f_E", [""])[0].split(",")
        experience_level = [_EXPERIENCE_MAP[c] for c in exp_codes if c in _EXPERIENCE_MAP]

        # Extract job functions (f_F) - passed to valig via urlParam
        func_codes = params.get("f_F", [""])[0].split(",")
        job_functions = [c for c in func_codes if c in _JOB_FUNCTION_NAMES]

        # Extract time posted (f_TPR)
        tpr = params.get("f_TPR", [None])[0]
        posted_limit = _TIME_POSTED_MAP.get(tpr) if tpr else None

        # Extract contract type (f_JT) - not commonly used but supported
        jt_codes = params.get("f_JT", [""])[0].split(",")
        contract_type_map = {"F": "Full-time", "P": "Part-time", "C": "Contract", "T": "Temporary", "I": "Internship"}
        contract_type = [contract_type_map[c] for c in jt_codes if c in contract_type_map]

        auto_label = label or _build_auto_label(job_titles, job_functions, locations, geo_id, workplace_type)

        return LinkedInSearchProfile(
            label=auto_label,
            job_titles=job_titles,
            locations=locations,
            geo_id=geo_id,
            workplace_type=workplace_type,
            experience_level=experience_level,
            job_functions=job_functions,
            contract_type=contract_type,
            posted_limit=posted_limit,
        )
    except Exception:
        logger.warning("Failed to parse LinkedIn URL: %s", url, exc_info=True)
        return None


def build_linkedin_url(profile: LinkedInSearchProfile) -> str:
    """Build a LinkedIn search URL from a structured profile (for display/reference)."""
    params: list[str] = []

    if profile.job_titles:
        params.append(f"keywords={profile.job_titles[0]}")

    if profile.locations:
        params.append(f"location={profile.locations[0]}")

    if profile.geo_id:
        params.append(f"geoId={profile.geo_id}")

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

    # Job functions (direct codes)
    if profile.job_functions:
        params.append(f"f_F={','.join(profile.job_functions)}")

    # Reverse-map posted limit
    tpr_reverse = {v: k for k, v in _TIME_POSTED_MAP.items()}
    if profile.posted_limit and profile.posted_limit in tpr_reverse:
        params.append(f"f_TPR={tpr_reverse[profile.posted_limit]}")

    params.append("sortBy=DD")
    return "https://www.linkedin.com/jobs/search/?" + "&".join(params)


def get_job_function_name(code: str) -> str:
    """Get human-readable name for a job function code."""
    return _JOB_FUNCTION_NAMES.get(code, code)


def get_geo_name(geo_id: str) -> str:
    """Get human-readable name for a geoId (if known)."""
    return _GEO_ID_NAMES.get(geo_id, f"geoId:{geo_id}")


def _build_auto_label(
    job_titles: list[str],
    job_functions: list[str],
    locations: list[str],
    geo_id: str | None,
    workplace_type: list[str],
) -> str:
    """Generate a human-readable label from search parameters."""
    # Title part
    if job_titles:
        title_part = job_titles[0]
    elif job_functions:
        func_names = [get_job_function_name(f) for f in job_functions[:2]]
        title_part = " / ".join(func_names)
    else:
        title_part = "All Jobs"

    # Location part
    if locations:
        loc_part = locations[0]
    elif geo_id:
        loc_part = get_geo_name(geo_id)
    elif "remote" in workplace_type:
        loc_part = "Remote"
    else:
        loc_part = "Any Location"

    return f"{title_part} — {loc_part}"
