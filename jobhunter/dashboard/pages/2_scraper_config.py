"""Scraper Configuration page — view/edit scraper settings (DB-backed)."""

import json
import logging
import os
from pathlib import Path

import streamlit as st
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from jobhunter.config.loader import load_config
from jobhunter.db.session import create_engine, get_session
from jobhunter.db.settings import CATEGORY_SCRAPING, get_scraping_config, update_settings
from jobhunter.scrapers.linkedin_url_parser import (
    get_geo_name,
    get_job_function_name,
    parse_linkedin_url,
)

logger = logging.getLogger(__name__)

PAGE_TITLE = "Scraper Configuration"

# Valig enums for LinkedIn structured queries
_WORKPLACE_OPTIONS = ["remote", "hybrid", "office"]
_EXPERIENCE_OPTIONS = ["internship", "entry", "associate", "mid-senior", "director", "executive"]
_POSTED_OPTIONS = [None, "1h", "24h", "week", "month"]
_JOB_FUNCTION_OPTIONS = ["it", "eng", "prjm", "sale", "mktg", "fin", "hr", "ops", "cons", "dsgn", "prod", "data"]


def _ensure_db_initialized() -> bool:
    """Ensure database engine is initialized. Returns True if successful."""
    if "db_initialized" not in st.session_state:
        try:
            config = load_config(Path("config.yaml"))
            create_engine(config.database)
            st.session_state.config = config
            st.session_state.db_initialized = True
            logger.info("Database initialized from scraper config page")
        except Exception as e:
            logger.exception("Failed to initialize database")
            st.error(f"Failed to initialize database: {e}")
            return False
    return True


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
    """Render LinkedIn (valig) config with multi-profile management."""
    st.subheader("LinkedIn (valig)")
    enabled = st.checkbox("Enabled", value=cfg.get("enabled", True), key="li_enabled")
    actor_id = st.text_input(
        "Actor ID", value=cfg.get("apify_actor_id", "valig/linkedin-jobs-scraper"), key="li_actor"
    )
    max_results: int = st.number_input(
        "Total Budget (max results across all profiles)",
        min_value=1,
        max_value=2000,
        value=cfg.get("max_results", 100),
        key="li_max",
    )

    # --- Search Profiles (using session state) ---
    st.markdown("#### Search Profiles")
    st.caption("Each profile is a separate search query. Budget is split by weight.")

    # Initialize profiles from session state or DB
    if "linkedin_profiles" not in st.session_state:
        st.session_state.linkedin_profiles = list(cfg.get("search_profiles", []))
        logger.debug("Initialized linkedin_profiles from DB: %d profiles", len(st.session_state.linkedin_profiles))

    profiles: list[dict] = st.session_state.linkedin_profiles

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
                    new_profile = parsed.model_dump()
                    st.session_state.linkedin_profiles.append(new_profile)
                    logger.info("Added LinkedIn profile from URL: %s", parsed.label)
                    st.success(f"Added profile: {parsed.label}")
                    st.rerun()
                else:
                    st.error("Could not parse URL. Please add profile manually below.")

    # Render existing profiles
    profiles_to_keep: list[dict] = []
    for i, profile in enumerate(profiles):
        profile_label = profile.get("label", f"Profile {i + 1}")
        is_only_profile = i == 0 and len(profiles) == 1
        with st.expander(f"Profile: {profile_label}", expanded=is_only_profile):
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

            # Geo ID field
            geo_id = profile.get("geo_id") or ""
            geo_display = f" ({get_geo_name(geo_id)})" if geo_id else ""
            geo_id_input = st.text_input(
                f"Geo ID{geo_display}",
                value=geo_id,
                key=f"li_p{i}_geo",
                help="LinkedIn geographic ID (e.g., 102105699 for Turkey). Leave empty for worldwide.",
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

            # Job functions
            current_functions = profile.get("job_functions", [])
            job_functions: list[str] = st.multiselect(
                "Job Functions",
                options=_JOB_FUNCTION_OPTIONS,
                default=[f for f in current_functions if f in _JOB_FUNCTION_OPTIONS],
                format_func=lambda x: f"{x} ({get_job_function_name(x)})",
                key=f"li_p{i}_func",
            )

            # Posted limit
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
                    "geo_id": geo_id_input.strip() or None,
                    "workplace_type": workplace_type,
                    "experience_level": experience_level,
                    "job_functions": job_functions,
                    "contract_type": profile.get("contract_type", []),  # Preserve existing
                    "posted_limit": posted_limit,
                    "weight": weight,
                })

    # Add new profile button
    if st.button("Add New Profile", key="li_add_profile"):
        st.session_state.linkedin_profiles.append({
            "label": "",
            "job_titles": [],
            "locations": [],
            "geo_id": None,
            "workplace_type": ["remote"],
            "experience_level": ["mid-senior", "director"],
            "job_functions": [],
            "contract_type": [],
            "posted_limit": None,
            "weight": 1,
        })
        logger.info("Added empty LinkedIn profile")
        st.rerun()

    if not profiles_to_keep and not profiles:
        st.caption("No search profiles configured — LinkedIn scraper will return no results.")

    # Update session state with current form values (important: do this every render)
    st.session_state.linkedin_profiles = profiles_to_keep

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

    if not _ensure_db_initialized():
        st.warning("Database not initialized. Run `python run.py init-db` first.")
        return

    try:
        with get_session() as session:
            config = get_scraping_config(session)
            config_dict = config.model_dump()
            logger.debug("Loaded scraping config from DB")

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

                # Log what we're saving
                logger.info("Saving scraper config...")
                logger.info("LinkedIn profiles to save: %d", len(linkedin_vals.get("search_profiles", [])))
                for i, p in enumerate(linkedin_vals.get("search_profiles", [])):
                    logger.info("  Profile %d: %s", i, p.get("label", "unnamed"))
                logger.debug("Full config: %s", json.dumps(new_data, indent=2, default=str))

                try:
                    update_settings(session, CATEGORY_SCRAPING, new_data)
                    session.commit()  # Explicit commit
                    logger.info("Configuration saved successfully to database")

                    # Clear session state AFTER successful save
                    if "linkedin_profiles" in st.session_state:
                        del st.session_state.linkedin_profiles
                        logger.debug("Cleared linkedin_profiles from session state")

                    st.success("Configuration saved.")
                    st.rerun()

                except ValidationError as e:
                    logger.error("Validation error saving config: %s", e)
                    st.error(f"Validation failed:\n{e}")

                except OperationalError as e:
                    logger.error("Database error saving config: %s", e)
                    if "database is locked" in str(e).lower():
                        st.error(
                            "Database is locked. Close any other applications "
                            "(like SQLite Browser) that have the database open and try again."
                        )
                    else:
                        st.error(f"Database error: {e}")

                except Exception as e:
                    logger.exception("Unexpected error saving config")
                    st.error(f"Failed to save: {e}")

    except RuntimeError as e:
        logger.error("Runtime error in scraper config: %s", e)
        st.warning("Database not initialized. Run `python run.py init-db` first.")

    except Exception as e:
        logger.exception("Unexpected error loading scraper config")
        st.error(f"Error: {e}")


main()
