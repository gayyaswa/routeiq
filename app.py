"""RouteIQ Streamlit app — scenic route intelligence with GraphRAG."""
from __future__ import annotations

import os

import streamlit as st
from streamlit_folium import st_folium
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic

from routeiq.facade import RouteIQFacade
from routeiq.rag import POIIndexer, VectorBaseline
from routeiq.ui import MapBuilder
from routeiq.ui.card_renderer import render_stop_card

load_dotenv()

st.set_page_config(
    page_title="RouteIQ — Scenic Route Intelligence",
    layout="wide",
    page_icon="🗺",
    initial_sidebar_state="collapsed",
)

# Minimal global style overrides
st.markdown(
    """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .block-container {padding-top: 1.5rem; padding-bottom: 1rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def _load_resources():
    """Build and cache all RouteIQ components for the process lifetime."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    llm = ChatAnthropic(model="claude-sonnet-4-6", api_key=api_key or None)
    shared_indexer = POIIndexer()
    facade = RouteIQFacade(llm, poi_indexer=shared_indexer)
    vbaseline = VectorBaseline(shared_indexer)
    builder = MapBuilder()
    return facade, vbaseline, builder


facade, vector_baseline, map_builder = _load_resources()


# ── Header ────────────────────────────────────────────────────────────────────

st.title("🗺 RouteIQ")
st.caption("Scenic route intelligence · GraphRAG + Wikipedia · Bay Area & beyond")

# ── Query input ───────────────────────────────────────────────────────────────

query_input = st.text_input(
    "route_query",
    placeholder="e.g. Drive from San Francisco to Monterey, show coastal landmarks and historic sites",
    label_visibility="collapsed",
)
run_btn = st.button("Find Scenic Stops ›", type="primary")

if run_btn and query_input.strip():
    with st.spinner("Finding your scenic route…"):
        state = facade.run(query_input.strip())
    st.session_state["result"] = state
    st.session_state["last_query"] = query_input.strip()

result: dict | None = st.session_state.get("result")

if result is None:
    st.info("Enter a route query above, then click **Find Scenic Stops** to begin.")
    st.stop()

# ── Error path ────────────────────────────────────────────────────────────────

if result.get("error"):
    st.warning(result.get("narrative") or "Something went wrong. Please try a different query.")
    st.stop()

# ── Successful result ─────────────────────────────────────────────────────────

route_result = result["route_result"]
top_pois = result.get("top_pois") or []
narrative = result.get("narrative", "")
origin = result.get("origin", "")
destination = result.get("destination", "")

# ── Controls row ──────────────────────────────────────────────────────────────

ctrl_left, ctrl_right = st.columns([3, 1])

with ctrl_left:
    categories = sorted({sp.poi.category for sp in top_pois})
    selected_cats = st.multiselect(
        "Filter by category",
        options=categories,
        default=categories,
        label_visibility="collapsed",
    )

with ctrl_right:
    view_mode = st.radio(
        "view_mode",
        options=["GraphRAG", "Vector Baseline"],
        horizontal=True,
        label_visibility="collapsed",
    )

# Route stats bar
st.markdown(
    f"**{origin}** → **{destination}** &nbsp;·&nbsp; "
    f"{route_result.length_km:.0f} km &nbsp;·&nbsp; "
    f"{route_result.drive_time_min:.0f} min drive &nbsp;·&nbsp; "
    f"{len(top_pois)} scenic stops",
    unsafe_allow_html=True,
)

# ── Two-column layout: map + stop cards ───────────────────────────────────────

map_col, card_col = st.columns([3, 2], gap="medium")

filtered_pois = [sp for sp in top_pois if sp.poi.category in selected_cats]

with map_col:
    folium_map = map_builder.build(
        route_result, top_pois, filtered_categories=selected_cats
    )
    st_folium(folium_map, height=500, use_container_width=True, returned_objects=[])

with card_col:
    if view_mode == "GraphRAG":
        if filtered_pois:
            cards_html = (
                '<div style="height:500px;overflow-y:auto;padding-right:6px;">'
                + "".join(render_stop_card(sp, i) for i, sp in enumerate(filtered_pois, 1))
                + "</div>"
            )
            st.components.v1.html(cards_html, height=510, scrolling=False)
        else:
            st.info("No stops match the selected categories.")
    else:
        # Vector baseline — semantic-only, no graph constraints
        last_query = st.session_state.get("last_query", "")
        vector_results = vector_baseline.query(last_query, n_results=5) if last_query else []

        if vector_results:
            st.caption("Vector-only retrieval (semantic similarity, no route constraints):")
            for i, r in enumerate(vector_results, 1):
                st.markdown(
                    f"**{i}. {r['name']}** &nbsp; `{r['category']}` &nbsp; score: `{r['similarity_score']:.3f}`",
                    unsafe_allow_html=True,
                )
                if r.get("description"):
                    st.caption(r["description"][:130])
                st.divider()
        else:
            st.info("Run a route query first to populate the vector baseline.")

# ── Narrative ─────────────────────────────────────────────────────────────────

with st.expander("Route narrative (generated by Claude)", expanded=False):
    st.markdown(narrative)
