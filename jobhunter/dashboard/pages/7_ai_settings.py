"""AI Settings — cost cap editor, spend display, and model configuration (D5)."""

import logging
from datetime import UTC, datetime, timedelta

import pandas as pd
import streamlit as st
from sqlalchemy import func
from sqlalchemy.orm import Session

from jobhunter.config.schema import AICostConfig, AppConfig
from jobhunter.db.models import MatchEvaluation
from jobhunter.db.session import get_session
from jobhunter.db.settings import CATEGORY_AI_COST, get_ai_cost_config, update_settings

logger = logging.getLogger(__name__)


def _get_today_spend(session: Session) -> dict[str, float | int]:
    """Get today's AI spend broken down by tier."""
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    rows = (
        session.query(
            MatchEvaluation.tier_evaluated,
            func.coalesce(func.sum(MatchEvaluation.cost_usd), 0.0).label("cost"),
            func.count(MatchEvaluation.eval_id).label("calls"),
        )
        .filter(MatchEvaluation.evaluated_at >= today_start)
        .group_by(MatchEvaluation.tier_evaluated)
        .all()
    )

    result: dict[str, float | int] = {
        "tier2_cost": 0.0,
        "tier2_calls": 0,
        "tier3_cost": 0.0,
        "tier3_calls": 0,
        "total_cost": 0.0,
        "total_calls": 0,
    }

    for tier, cost, calls in rows:
        cost_val = float(cost)
        calls_val = int(calls)
        if tier == 2:
            result["tier2_cost"] = cost_val
            result["tier2_calls"] = calls_val
        elif tier == 3:
            result["tier3_cost"] = cost_val
            result["tier3_calls"] = calls_val
        result["total_cost"] += cost_val
        result["total_calls"] += calls_val

    return result


def _render_cost_overview(session: Session) -> None:
    """Show today's spend, daily cap, and progress bar."""
    cost_config = get_ai_cost_config(session)
    spend = _get_today_spend(session)

    st.subheader("Today's AI Spend")

    total = spend["total_cost"]
    cap = cost_config.daily_cap_usd

    # Progress display
    if cap > 0:
        pct = total / cap
        st.markdown(f"**${total:.2f} / ${cap:.2f}**")
        if pct >= 1.0:
            st.progress(1.0, text="Daily cap reached")
            st.error("Daily cap reached — evaluation paused")
        elif pct >= cost_config.warn_at_percent:
            st.progress(min(pct, 1.0), text=f"{pct:.0%} of daily cap")
            st.warning(f"Approaching daily cap — ${cap - total:.2f} remaining")
        else:
            st.progress(min(pct, 1.0), text=f"{pct:.0%} of daily cap")
    else:
        st.markdown(f"**${total:.2f}** (no daily cap set)")

    # Breakdown table
    breakdown_data = {
        "Tier": ["Tier 2", "Tier 3", "Cover Letter", "**Total**"],
        "Calls": [
            spend["tier2_calls"],
            spend["tier3_calls"],
            "—",
            spend["total_calls"],
        ],
        "Cost": [
            f"${spend['tier2_cost']:.3f}",
            f"${spend['tier3_cost']:.3f}",
            "— (M4)",
            f"${total:.3f}",
        ],
    }
    st.dataframe(
        pd.DataFrame(breakdown_data),
        use_container_width=True,
        hide_index=True,
    )


def _render_cost_config_editor(session: Session) -> None:
    """Editable form for daily_cap_usd and warn_at_percent."""
    st.subheader("Cost Configuration")

    cost_config = get_ai_cost_config(session)

    with st.form("ai_cost_form"):
        daily_cap = st.number_input(
            "Daily Cost Cap (USD)",
            min_value=0.0,
            max_value=100.0,
            value=cost_config.daily_cap_usd,
            step=0.50,
            format="%.2f",
        )
        # Display as percentage (0-100) but store as 0.0-1.0
        warn_pct = st.number_input(
            "Warn at (%)",
            min_value=0,
            max_value=100,
            value=int(cost_config.warn_at_percent * 100),
            step=5,
        )

        submitted = st.form_submit_button("Save Settings")
        if submitted:
            try:
                new_data = {
                    "daily_cap_usd": daily_cap,
                    "warn_at_percent": warn_pct / 100.0,
                }
                # Validate via Pydantic
                AICostConfig(**new_data)
                update_settings(session, CATEGORY_AI_COST, new_data)
                st.success("AI cost settings saved.")
                logger.info("AI cost config updated: cap=$%.2f, warn=%d%%", daily_cap, warn_pct)
            except Exception as e:
                st.error(f"Failed to save: {e}")
                logger.exception("Failed to save AI cost config")


def _render_model_info() -> None:
    """Read-only display of configured AI models per tier."""
    st.subheader("Model Configuration")
    st.caption("Read-only — edit `config.yaml` to change models.")

    config: AppConfig | None = st.session_state.get("config")
    if config is None:
        st.warning("Configuration not loaded.")
        return

    models = config.ai_models
    model_data = {
        "Task": ["Tier 2 (triage)", "Tier 3 (deep eval)", "Content Generation"],
        "Provider": [models.tier2.provider, models.tier3.provider, models.content_gen.provider],
        "Model": [models.tier2.model, models.tier3.model, models.content_gen.model],
        "Max Tokens": [models.tier2.max_tokens, models.tier3.max_tokens, models.content_gen.max_tokens],
    }
    st.dataframe(
        pd.DataFrame(model_data),
        use_container_width=True,
        hide_index=True,
    )


def _render_cost_history(session: Session) -> None:
    """Simple cost history: last 7 days of daily spend."""
    st.subheader("Cost History (last 7 days)")

    seven_days_ago = datetime.now(UTC) - timedelta(days=7)

    rows = (
        session.query(
            func.date(MatchEvaluation.evaluated_at).label("day"),
            func.coalesce(func.sum(MatchEvaluation.cost_usd), 0.0).label("cost"),
        )
        .filter(MatchEvaluation.evaluated_at >= seven_days_ago)
        .group_by(func.date(MatchEvaluation.evaluated_at))
        .order_by(func.date(MatchEvaluation.evaluated_at))
        .all()
    )

    if not rows:
        st.caption("No AI evaluations in the last 7 days.")
        return

    df = pd.DataFrame(rows, columns=["Day", "Cost ($)"])
    df["Day"] = pd.to_datetime(df["Day"]).dt.strftime("%b %d")
    st.bar_chart(df.set_index("Day"))

    total = sum(float(r[1]) for r in rows)
    avg = total / len(rows)
    st.caption(f"7-day total: ${total:.2f}  |  Daily average: ${avg:.2f}")


def main() -> None:
    """AI Settings page entry point."""
    st.header("AI Settings")

    try:
        with get_session() as session:
            _render_cost_overview(session)

            st.divider()

            _render_cost_config_editor(session)

            st.divider()

            _render_model_info()

            st.divider()

            _render_cost_history(session)

    except RuntimeError:
        st.warning("Database not initialized. Run `python run.py init-db` first.")


main()
