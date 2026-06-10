"""RouteIQ Streamlit app — scenic route intelligence with GraphRAG."""
from __future__ import annotations

import os
import time
import threading

import streamlit as st
from streamlit_folium import st_folium
from dotenv import load_dotenv

from routeiq.graph import GraphLoader
from routeiq.ui import MapBuilder
from routeiq.ui.card_renderer import render_stop_card

load_dotenv()

import osmnx as ox

_T0 = time.perf_counter()
def _log(msg: str) -> None:
    print(f"[{time.perf_counter()-_T0:6.2f}s] {msg}", flush=True)
# OSMnx 2.x uses overpass_url (not overpass_endpoint which silently does nothing)
ox.settings.overpass_url = "https://overpass.kumi.systems/api"
ox.settings.overpass_rate_limit = False   # skip the /status pre-check that times out at 180s
ox.settings.requests_timeout = 45         # fail fast per mirror instead of hanging

st.set_page_config(
    page_title="RouteIQ — Scenic Route Intelligence",
    layout="wide",
    page_icon="🗺",
    initial_sidebar_state="collapsed",
)

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


# ── Vertical stepper renderer ─────────────────────────────────────────────────

_STEPPER_CSS = """
<style>
.riq-stepper{font-family:-apple-system,BlinkMacSystemFont,sans-serif;padding:16px 4px;}
.riq-step{display:flex;align-items:flex-start;margin-bottom:4px;}
.riq-icon{font-size:18px;min-width:30px;line-height:1.6;}
.riq-icon.riq-blink{animation:riq-pulse 1s ease-in-out infinite;}
.riq-label{font-size:15px;font-weight:500;line-height:1.6;}
.riq-label.riq-done{color:#22c55e;}
.riq-label.riq-active{color:#3b82f6;}
.riq-label.riq-pending{color:#9ca3af;}
.riq-subtask{font-size:13px;color:#6b7280;font-style:italic;margin-left:30px;margin-bottom:6px;}
.riq-connector{width:2px;height:14px;background:#e5e7eb;margin-left:13px;margin-bottom:4px;}
@keyframes riq-pulse{0%,100%{opacity:1}50%{opacity:0.2}}
</style>
"""

_STEPS = [
    ("parse",   "Parsing your query",                  "🔍"),
    ("graph",   "Building route",                      "🗺️"),
    ("rag",     "Enriching with Wikipedia + GraphRAG", "📚"),
    ("narrate", "Generating narrative",                "✍️"),
]


def _render_stepper(state: dict) -> str:
    current = state.get("current")
    done = state.get("done", set())
    subtask = state.get("subtask", "")

    rows = [_STEPPER_CSS, '<div class="riq-stepper">']
    for i, (step_id, label, icon) in enumerate(_STEPS):
        if step_id in done:
            icon_cls, label_cls, display_icon = "", "riq-done", "✅"
        elif step_id == current:
            icon_cls, label_cls, display_icon = "riq-blink", "riq-active", icon
        else:
            icon_cls, label_cls, display_icon = "", "riq-pending", "⭕"

        rows.append(
            f'<div class="riq-step">'
            f'<span class="riq-icon {icon_cls}">{display_icon}</span>'
            f'<span class="riq-label {label_cls}">{label}</span>'
            f'</div>'
        )
        if step_id == current and subtask:
            rows.append(f'<div class="riq-subtask">{subtask}</div>')
        if i < len(_STEPS) - 1:
            rows.append('<div class="riq-connector"></div>')

    rows.append('</div>')
    return "".join(rows)


# ── Background graph preload ──────────────────────────────────────────────────

# Pre-warm the 4 Day-5 demo route corridors so the OSM graphs are cached before
# the first user query. Each bbox covers origin→destination + 0.1° padding.
_DEMO_BBOXES = [
    dict(north=37.9, south=36.5, east=-121.7, west=-122.6),  # SF → Monterey
    dict(north=38.5, south=37.6, east=-122.1, west=-122.6),  # SF → Napa
    dict(north=37.5, south=36.8, east=-121.7, west=-122.2),  # SJ → Santa Cruz
    dict(north=37.9, south=37.3, east=-122.2, west=-122.6),  # SF → Half Moon Bay
]


def _preload_graphs(loader: GraphLoader) -> None:
    for bbox in _DEMO_BBOXES:
        try:
            loader.load(**bbox)
        except Exception:
            pass  # best-effort; pipeline loads on demand if this fails


@st.cache_resource
def _load_lightweight():
    """Lightweight init — runs at page load so the UI appears instantly."""
    _log("_load_lightweight: start")
    graph_loader = GraphLoader()
    _log("_load_lightweight: GraphLoader done")
    builder = MapBuilder()
    _log("_load_lightweight: MapBuilder done")
    preload_thread = threading.Thread(
        target=_preload_graphs, args=(graph_loader,), daemon=True
    )
    preload_thread.start()
    _log("_load_lightweight: done")
    return graph_loader, builder, preload_thread


@st.cache_resource
def _load_heavy():
    """Heavy init (LLM + ChromaDB + pipeline) — deferred until first query."""
    import chromadb
    from langchain_anthropic import ChatAnthropic
    from routeiq.facade import RouteIQFacade
    from routeiq.rag import POIIndexer, VectorBaseline
    from eval.evaluator import _BAY_AREA_SEED_POIS

    _log("_load_heavy: start")
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    llm = ChatAnthropic(model="claude-sonnet-4-6", api_key=api_key or None)
    _log("_load_heavy: LLM ready")

    chroma_client = chromadb.PersistentClient(path="./cache/chroma")
    _log("_load_heavy: ChromaDB client ready")
    graph_loader, _, _ = _load_lightweight()

    shared_indexer = POIIndexer(client=chroma_client)
    _log("_load_heavy: shared_indexer ready")
    facade = RouteIQFacade(llm, poi_indexer=shared_indexer, graph_loader=graph_loader, chroma_client=chroma_client)
    _log("_load_heavy: facade ready")

    vector_indexer = POIIndexer(client=chroma_client, collection_name="routeiq_vector_baseline")
    if vector_indexer.collection.count() == 0:
        _log("_load_heavy: seeding vector baseline…")
        vector_indexer.index(_BAY_AREA_SEED_POIS)
    vbaseline = VectorBaseline(vector_indexer)
    _log("_load_heavy: done")

    return facade, vbaseline


_log("module top-level: before _load_lightweight()")
_graph_loader, map_builder, _preload_thread = _load_lightweight()
_log("module top-level: _load_lightweight() returned")


# ── Header ────────────────────────────────────────────────────────────────────

st.title("🗺 RouteIQ")
st.caption("Scenic route intelligence · GraphRAG + Wikipedia · Bay Area & beyond")

if _preload_thread.is_alive():
    st.info(
        "🔄 Pre-loading map data for demo routes in the background — "
        "first query may take 2–3 min if it hits an uncached corridor.",
        icon=None,
    )

# ── Query input ───────────────────────────────────────────────────────────────

query_input = st.text_input(
    "route_query",
    placeholder="e.g. Drive from San Francisco to Monterey, show coastal landmarks and historic sites",
    label_visibility="collapsed",
)
run_btn = st.button("Find Scenic Stops ›", type="primary")

if run_btn and query_input.strip():
    facade, vector_baseline = _load_heavy()

    stepper_placeholder = st.empty()
    _step_state: dict = {"current": None, "done": set(), "subtask": ""}

    def _on_progress(step: str, subtask: str) -> None:
        if _step_state["current"] and _step_state["current"] != step:
            _step_state["done"].add(_step_state["current"])
        _step_state["current"] = step
        _step_state["subtask"] = subtask
        stepper_placeholder.markdown(_render_stepper(_step_state), unsafe_allow_html=True)

    state = facade.run(query_input.strip(), on_progress=_on_progress)

    _step_state["done"] = {s[0] for s in _STEPS}
    _step_state["current"] = None
    stepper_placeholder.empty()

    st.session_state["result"] = state
    st.session_state["last_query"] = query_input.strip()
    st.session_state.pop("vector_narrative", None)  # clear stale narrative from previous query

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
        _, vector_baseline = _load_heavy()
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

narrative_label = (
    "Route narrative — Vector Baseline (generated by Claude)"
    if view_mode == "Vector Baseline"
    else "Route narrative — GraphRAG (generated by Claude)"
)
with st.expander(narrative_label, expanded=False):
    if view_mode == "Vector Baseline":
        if not st.session_state.get("vector_narrative"):
            facade, vector_baseline = _load_heavy()
            last_query = st.session_state.get("last_query", "")
            v_results = vector_baseline.query(last_query, n_results=5) if last_query else []
            v_context = "\n\n".join(
                f"{r['name']} | {r['category']} | {r['description']}"
                for r in v_results if r.get("description")
            )
            if v_context and not result.get("error") and result.get("route_result"):
                route = result["route_result"]
                with st.spinner("Generating vector baseline narrative…"):
                    st.session_state["vector_narrative"] = facade.generate_narrative(
                        origin=result.get("origin", ""),
                        destination=result.get("destination", ""),
                        distance_km=route.length_km,
                        drive_time_min=route.drive_time_min,
                        poi_context=v_context,
                    )
        st.markdown(st.session_state.get("vector_narrative") or narrative)
    else:
        st.markdown(narrative)
