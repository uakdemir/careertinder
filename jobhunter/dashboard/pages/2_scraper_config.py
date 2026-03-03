"""Scraper Configuration page — view/edit scraper settings (DB-backed)."""

import logging
import os

import streamlit as st
from pydantic import ValidationError

from jobhunter.db.session import get_session
from jobhunter.db.settings import CATEGORY_SCRAPING, get_scraping_config, update_settings
from jobhunter.scrapers.linkedin_url_parser import parse_linkedin_url

logger = logging.getLogger(__name__)

PAGE_TITLE = "Scraper Configuration"

# HarvestAPI enums for LinkedIn structured queries
_WORKPLACE_OPTIONS = ["remote", "hybrid", "office"]
_EXPERIENCE_OPTIONS = ["internship", "entry", "associate", "mid-senior", "director", "executive"]
_SALARY_OPTIONS = [None, "40k+", "60k+", "80k+", "100k+", "120k+", "140k+", "160k+", "180k+", "200k+"]
_POSTED_OPTIONS = [None, "1h", "24h", "week", "month"]


def _render_global_settings(current_timeout: int) -> int:
    """Render global scraping settings. Returns the timeout value from the form."""
    st.subheader("Global Settings")
    timeout: int = st.number_input(
        "Timeout (seconds)",
        min_value=30,
        max_value=3600,
        value=current_timeout,
        step=30,
        key="cfg_timeout",
    )
    return timeout


def _render_linkedin_config(cfg: dict) -> dict:
    """Render LinkedIn (HarvestAPI) config with multi-profile management."""
    st.subheader("LinkedIn (HarvestAPI)")
    enabled = st.checkbox("Enabled", value=cfg.get("enabled", True), key="li_enabled")
    actor_id = st.text_input(
        "Actor ID", value=cfg.get("apify_actor_id", "harvestapi/linkedin-job-search"), key="li_actor"
    )
    max_results: int = st.number_input(
        "Total Budget (max results across all profiles)",
        min_value=1,
        max_value=2000,
        value=cfg.get("max_results", 100),
        key="li_max",
    )

    # --- Search Profiles ---
    st.markdown("#### Search Profiles")
    st.caption("Each profile is a separate search query. Budget is split by weight.")

    profiles: list[dict] = list(cfg.get("search_profiles", []))

    # URL import tool
    with st.expander("Import from LinkedIn URL"):
        import_url = st.text_input(
            "Paste a LinkedIn search URL",
            key="li_import_url",
            placeholder="https://www.linkedin.com/jobs/search/?keywords=architect&f_WT=2",
        )
        import_label = st.text_input("Label (optional)", key="li_import_label")
        if st.button("Parse & Add", key="li_import_btn"):
            if import_url:
                parsed = parse_linkedin_url(import_url, label=import_label)
                if parsed:
                    profiles.append(parsed.model_dump())
                    st.success(f"Added profile: {parsed.label}")
                else:
                    st.error("Could not parse URL. Please add profile manually below.")

    # Render existing profiles
    profiles_to_keep: list[dict] = []
    for i, profile in enumerate(profiles):
        with st.expander(f"Profile: {profile.get('label', f'Profile {i + 1}')}", expanded=i == 0):
            col_label, col_weight = st.columns([3, 1])
            with col_label:
                label = st.text_input("Label", value=profile.get("label", ""), key=f"li_p{i}_label")
            with col_weight:
                weight: int = st.number_input(
                    "Weight", min_value=1, max_value=10,
                    value=profile.get("weight", 1), key=f"li_p{i}_weight",
                )

            job_titles_str = st.text_input(
                "Job Titles (comma-separated)",
                value=", ".join(profile.get("job_titles", [])),
                key=f"li_p{i}_titles",
            )
            locations_str = st.text_input(
                "Locations (comma-separated, empty = worldwide)",
                value=", ".join(profile.get("locations", [])),
                key=f"li_p{i}_locs",
            )

            col_wt, col_exp = st.columns(2)
            with col_wt:
                workplace_type: list[str] = st.multiselect(
                    "Workplace Type",
                    options=_WORKPLACE_OPTIONS,
                    default=profile.get("workplace_type", ["remote"]),
                    key=f"li_p{i}_wt",
                )
            with col_exp:
                experience_level: list[str] = st.multiselect(
                    "Experience Level",
                    options=_EXPERIENCE_OPTIONS,
                    default=profile.get("experience_level", []),
                    key=f"li_p{i}_exp",
                )

            col_sal, col_posted = st.columns(2)
            with col_sal:
                current_salary = profile.get("salary")
                salary_idx = _SALARY_OPTIONS.index(current_salary) if current_salary in _SALARY_OPTIONS else 0
                salary = st.selectbox(
                    "Min Salary",
                    options=_SALARY_OPTIONS,
                    index=salary_idx,
                    format_func=lambda x: "Any" if x is None else x,
                    key=f"li_p{i}_sal",
                )
            with col_posted:
                current_posted = profile.get("posted_limit")
                posted_idx = _POSTED_OPTIONS.index(current_posted) if current_posted in _POSTED_OPTIONS else 0
                posted_limit = st.selectbox(
                    "Posted Within",
                    options=_POSTED_OPTIONS,
                    index=posted_idx,
                    format_func=lambda x: "Any time" if x is None else x,
                    key=f"li_p{i}_posted",
                )

            remove = st.checkbox("Remove this profile", key=f"li_p{i}_remove")

            if not remove:
                profiles_to_keep.append({
                    "label": label,
                    "job_titles": [t.strip() for t in job_titles_str.split(",") if t.strip()],
                    "locations": [loc.strip() for loc in locations_str.split(",") if loc.strip()],
                    "workplace_type": workplace_type,
                    "experience_level": experience_level,
                    "salary": salary,
                    "posted_limit": posted_limit,
                    "weight": weight,
                })

    # Add new profile button
    if st.button("Add New Profile", key="li_add_profile"):
        profiles_to_keep.append({
            "label": "",
            "job_titles": [],
            "locations": [],
            "workplace_type": ["remote"],
            "experience_level": ["mid-senior", "director"],
            "salary": None,
            "posted_limit": None,
            "weight": 1,
        })

    if not profiles_to_keep:
        st.caption("No search profiles configured — LinkedIn scraper will return no results.")

    return {
        "enabled": enabled,
        "apify_actor_id": actor_id,
        "max_results": max_results,
        "search_profiles": profiles_to_keep,
    }


def _render_wellfound_config(cfg: dict) -> dict:
    """Render Wellfound (Apify) config fields. Returns form values."""
    st.subheader("Wellfound (Apify)")
    st.caption("Deferred: all available Apify actors require manual cookie/CAPTCHA management.")
    enabled = st.checkbox("Enabled", value=cfg.get("enabled", False), key="wf_enabled")
    actor_id = st.text_input("Actor ID", value=cfg.get("apify_actor_id", ""), key="wf_actor")
    search_kw = st.text_input("Search Keyword", value=cfg.get("search_keyword", ""), key="wf_kw")
    loc_filter = st.text_input("Location Filter", value=cfg.get("location_filter", ""), key="wf_loc")
    max_results = st.number_input(
        "Max Results", min_value=1, max_value=1000,
        value=cfg.get("max_results", 100), key="wf_max",
    )
    return {
        "enabled": enabled,
        "apify_actor_id": actor_id,
        "search_keyword": search_kw,
        "location_filter": loc_filter,
        "max_results": max_results,
    }


def _render_playwright_config(
    label: str,
    cfg: dict,
    prefix: str,
) -> dict:
    """Render a Playwright-based scraper config (Remote.io or RemoteRocketship)."""
    st.subheader(f"{label} (Playwright)")
    enabled = st.checkbox("Enabled", value=cfg.get("enabled", True), key=f"{prefix}_enabled")
    base_url = st.text_input("Base URL", value=cfg.get("base_url", ""), key=f"{prefix}_url")
    col1, col2 = st.columns(2)
    with col1:
        max_pages = st.number_input(
            "Max Pages", min_value=1, max_value=100,
            value=cfg.get("max_pages", 10), key=f"{prefix}_pages",
        )
    with col2:
        delay = st.number_input(
            "Delay (s)", min_value=0, max_value=30,
            value=cfg.get("delay_seconds", 2), key=f"{prefix}_delay",
        )
    return {
        "enabled": enabled,
        "base_url": base_url,
        "max_pages": max_pages,
        "delay_seconds": delay,
    }


def _render_secrets_status() -> None:
    """Show read-only indicator for API key configuration."""
    st.subheader("Secrets Status")
    apify_token = os.environ.get("APIFY_API_TOKEN")
    if apify_token:
        st.markdown("Apify token: **configured**")
    else:
        st.markdown("Apify token: **not configured** — set `APIFY_API_TOKEN` in `.env`")


def main() -> None:
    """Scraper Configuration page entry point."""
    st.header(PAGE_TITLE)
    st.markdown("View and edit scraper settings. Changes are saved to the database and take effect on the next scrape.")

    try:
        with get_session() as session:
            config = get_scraping_config(session)
            config_dict = config.model_dump()

            timeout = _render_global_settings(config_dict["timeout_seconds"])

            st.divider()
            linkedin_vals = _render_linkedin_config(config_dict["linkedin"])

            st.divider()
            wellfound_vals = _render_wellfound_config(config_dict["wellfound"])

            st.divider()
            rio_vals = _render_playwright_config(
                "Remote.io", config_dict["remote_io"], "rio",
            )

            st.divider()
            rrs_vals = _render_playwright_config(
                "RemoteRocketship", config_dict["remote_rocketship"], "rrs",
            )

            st.divider()
            _render_secrets_status()

            st.divider()
            if st.button("Save Configuration", type="primary", key="save_config"):
                new_data = {
                    "timeout_seconds": timeout,
                    "linkedin": linkedin_vals,
                    "wellfound": wellfound_vals,
                    "remote_io": rio_vals,
                    "remote_rocketship": rrs_vals,
                }
                try:
                    update_settings(session, CATEGORY_SCRAPING, new_data)
                    st.success("Configuration saved.")
                except ValidationError as e:
                    st.error(f"Validation failed:\n{e}")
    except RuntimeError:
        st.warning("Database not initialized. Run `python run.py init-db` first.")


main()
