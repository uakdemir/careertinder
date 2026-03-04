"""Filtering Configuration Editor — edit Tier 1 filter rules via dashboard.

Edits are saved to the SQLite settings table and take effect on next filter run.
"""

import logging

import streamlit as st

from jobhunter.config.schema import FilteringConfig
from jobhunter.db.session import get_session
from jobhunter.db.settings import CATEGORY_FILTERING, get_filtering_config, update_settings

logger = logging.getLogger(__name__)

PAGE_TITLE = "Filter Configuration"


def _render_salary_settings(config: FilteringConfig) -> int:
    """Render salary settings section."""
    st.subheader("Salary Settings")
    salary_min: int = st.number_input(
        "Minimum Salary (USD)",
        min_value=0,
        max_value=500000,
        value=config.salary_min_usd,
        step=5000,
        help="Jobs with salary below this threshold will fail. Jobs without salary data pass to Tier 2.",
    )
    st.info("ℹ️ Jobs without salary data pass to Tier 2 (not configurable per design philosophy)")
    return salary_min


def _render_title_patterns(config: FilteringConfig) -> tuple[list[str], list[str]]:
    """Render title whitelist/blacklist section."""
    st.subheader("Title Patterns")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Whitelist** (at least one must match)")
        whitelist_text = st.text_area(
            "Title Whitelist",
            value="\n".join(config.title_whitelist),
            height=200,
            help="One pattern per line. Jobs not matching any pattern become ambiguous.",
            label_visibility="collapsed",
        )
        whitelist = [p.strip() for p in whitelist_text.split("\n") if p.strip()]

    with col2:
        st.markdown("**Blacklist** (auto-reject)")
        blacklist_text = st.text_area(
            "Title Blacklist",
            value="\n".join(config.title_blacklist),
            height=200,
            help="One pattern per line. Jobs matching any pattern are rejected.",
            label_visibility="collapsed",
        )
        blacklist = [p.strip() for p in blacklist_text.split("\n") if p.strip()]

    return whitelist, blacklist


def _render_location_keywords(config: FilteringConfig) -> tuple[list[str], list[str]]:
    """Render location keywords section."""
    st.subheader("Location Keywords")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Include** (positive signals)")
        include_text = st.text_area(
            "Location Include",
            value="\n".join(config.location_keywords.include),
            height=150,
            help="Keywords that indicate remote-friendly positions.",
            label_visibility="collapsed",
        )
        include = [p.strip() for p in include_text.split("\n") if p.strip()]

    with col2:
        st.markdown("**Exclude** (negative signals)")
        exclude_text = st.text_area(
            "Location Exclude",
            value="\n".join(config.location_keywords.exclude),
            height=150,
            help="Keywords that indicate geo-restrictions.",
            label_visibility="collapsed",
        )
        exclude = [p.strip() for p in exclude_text.split("\n") if p.strip()]

    return include, exclude


def _render_company_lists(config: FilteringConfig) -> tuple[list[str], list[str]]:
    """Render company whitelist/blacklist section."""
    st.subheader("Company Lists")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Whitelist** (dream companies - always pass)")
        whitelist_text = st.text_area(
            "Company Whitelist",
            value="\n".join(config.company_whitelist),
            height=100,
            help="Companies on this list always pass regardless of other rules.",
            label_visibility="collapsed",
        )
        whitelist = [p.strip() for p in whitelist_text.split("\n") if p.strip()]

    with col2:
        st.markdown("**Blacklist** (always reject)")
        blacklist_text = st.text_area(
            "Company Blacklist",
            value="\n".join(config.company_blacklist),
            height=100,
            help="Companies on this list are always rejected.",
            label_visibility="collapsed",
        )
        blacklist = [p.strip() for p in blacklist_text.split("\n") if p.strip()]

    return whitelist, blacklist


def _render_keywords(config: FilteringConfig) -> tuple[list[str], list[str]]:
    """Render required/excluded keywords section."""
    st.subheader("Keywords")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Required** (at least one)")
        required_text = st.text_area(
            "Required Keywords",
            value="\n".join(config.required_keywords),
            height=150,
            help="At least one keyword must appear in title or description. Jobs without any become ambiguous.",
            label_visibility="collapsed",
        )
        required = [p.strip() for p in required_text.split("\n") if p.strip()]

    with col2:
        st.markdown("**Excluded** (auto-reject)")
        excluded_text = st.text_area(
            "Excluded Keywords",
            value="\n".join(config.excluded_keywords),
            height=150,
            help="Jobs containing any of these keywords are rejected.",
            label_visibility="collapsed",
        )
        excluded = [p.strip() for p in excluded_text.split("\n") if p.strip()]

    return required, excluded


def main() -> None:
    """Filter Configuration page entry point."""
    st.header(PAGE_TITLE)

    try:
        with get_session() as session:
            config = get_filtering_config(session)

            # Render all sections
            salary_min = _render_salary_settings(config)

            st.markdown("---")
            title_whitelist, title_blacklist = _render_title_patterns(config)

            st.markdown("---")
            location_include, location_exclude = _render_location_keywords(config)

            st.markdown("---")
            company_whitelist, company_blacklist = _render_company_lists(config)

            st.markdown("---")
            required_keywords, excluded_keywords = _render_keywords(config)

            st.markdown("---")

            # Save button
            if st.button("Save Configuration", type="primary"):
                try:
                    # Build new config dict
                    new_config = {
                        "salary_min_usd": salary_min,
                        "title_whitelist": title_whitelist,
                        "title_blacklist": title_blacklist,
                        "location_keywords": {
                            "include": location_include,
                            "exclude": location_exclude,
                        },
                        "company_whitelist": company_whitelist,
                        "company_blacklist": company_blacklist,
                        "required_keywords": required_keywords,
                        "excluded_keywords": excluded_keywords,
                    }

                    # Validate and save
                    update_settings(session, CATEGORY_FILTERING, new_config)
                    session.commit()

                    st.success("✓ Configuration saved successfully!")
                    logger.info("Filtering configuration updated from dashboard")

                except Exception as e:
                    st.error(f"Failed to save configuration: {e}")
                    logger.exception("Failed to save filtering configuration")

    except RuntimeError:
        st.warning("Database not initialized. Run `python run.py init-db` first.")


main()
