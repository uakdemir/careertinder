"""Reusable paginated table component for dashboard pages."""

import streamlit as st


def paginated_controls(total_items: int, page_size: int, key_prefix: str) -> tuple[int, int]:
    """Render pagination controls and return (offset, limit).

    Args:
        total_items: Total number of items in the dataset.
        page_size: Number of items per page.
        key_prefix: Unique prefix for session state keys to avoid collisions.

    Returns:
        Tuple of (offset, limit) for the current page.
    """
    if total_items == 0:
        return 0, page_size

    total_pages = max(1, (total_items + page_size - 1) // page_size)

    state_key = f"{key_prefix}_page"
    if state_key not in st.session_state:
        st.session_state[state_key] = 1

    current_page: int = st.session_state[state_key]
    current_page = min(current_page, total_pages)

    col1, col2, col3, col4, col5 = st.columns([1, 1, 2, 1, 1])
    with col1:
        if st.button("◀ Prev", key=f"{key_prefix}_prev", disabled=current_page <= 1):
            st.session_state[state_key] = current_page - 1
            st.rerun()
    with col3:
        start = (current_page - 1) * page_size + 1
        end = min(current_page * page_size, total_items)
        st.markdown(f"Showing **{start}–{end}** of **{total_items}**")
    with col5:
        if st.button("Next ▶", key=f"{key_prefix}_next", disabled=current_page >= total_pages):
            st.session_state[state_key] = current_page + 1
            st.rerun()

    offset = (current_page - 1) * page_size
    return offset, page_size
