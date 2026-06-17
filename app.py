"""RouteIQ Streamlit app — scenic route intelligence with GraphRAG."""
from __future__ import annotations

import os
import time
import threading
import uuid

# _T0 must come before ALL third-party imports — osmnx/pandas/shapely import chains
# previously took 25-30s silently before the timer was set.
_T0 = time.perf_counter()

def _log(msg: str) -> None:
    print(f"[{time.perf_counter()-_T0:6.2f}s] {msg}", flush=True)

_log("import: streamlit")
import streamlit as st
_log("import: streamlit_folium")
from streamlit_folium import st_folium
_log("import: dotenv")
from dotenv import load_dotenv
load_dotenv()
_log("import: routeiq.ui.card_renderer")
from routeiq.ui.card_renderer import render_stop_card, render_vector_card, render_dt_card, IMAGE_MODAL_HTML
_log("imports: light done")

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
.riq-subtask{font-size:13px;color:#6b7280;font-style:italic;margin-left:30px;margin-bottom:4px;}
.riq-slow-warn{font-size:12px;font-weight:600;color:#b45309;background:#fef3c7;border:1px solid #fcd34d;border-radius:6px;padding:5px 10px;margin-left:30px;margin-bottom:8px;}
.riq-connector{width:2px;height:14px;background:#e5e7eb;margin-left:13px;margin-bottom:4px;}
@keyframes riq-pulse{0%,100%{opacity:1}50%{opacity:0.2}}
</style>
"""

# Subtask keywords that indicate a live server fetch (slow outside Bay Area)
_SLOW_SUBTASK_KEYWORDS = (
    "Loading OSM road network",
    "Querying POI server",
    "POI server",
)

_STEPS = [
    ("parse",   "Parsing your query",                  "🔍"),
    ("graph",   "Building route",                      "🗺️"),
    ("rag",     "Enriching with Wikipedia + GraphRAG", "📚"),
    ("narrate", "Generating narrative",                "✍️"),
]

_DT_STEPS = [
    ("find_pois", "Discovering city POIs",  "🏙️"),
    ("rate_pois", "Rating stops",           "⭐"),
    ("extract",   "Finalizing itinerary",   "📋"),
]


def _render_stepper(state: dict, steps=None) -> str:
    if steps is None:
        steps = _STEPS
    current = state.get("current")
    done = state.get("done", set())
    subtask = state.get("subtask", "")

    rows = [_STEPPER_CSS, '<div class="riq-stepper">']
    for i, (step_id, label, icon) in enumerate(steps):
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
            if any(kw in subtask for kw in _SLOW_SUBTASK_KEYWORDS):
                rows.append(
                    '<div class="riq-slow-warn">'
                    "⏳ Fetching from OpenStreetMap server — may take 1–3 min on first run. "
                    "Once downloaded, the graph is cached locally — same route is instant next time."
                    "</div>"
                )
        if i < len(steps) - 1:
            rows.append('<div class="riq-connector"></div>')

    rows.append('</div>')
    return "".join(rows)


# ── Background graph preload ──────────────────────────────────────────────────

# Pre-warm the 4 Day-5 demo route corridors so the OSM graphs are cached before
# the first user query. Each bbox covers origin→destination + 0.1° padding.
_DEMO_BBOXES = [
    dict(north=37.996, south=37.688, east=-122.308, west=-122.680),  # SF → Muir Woods (Golden Gate, Marin Headlands, redwoods)
    dict(north=38.590, south=37.688, east=-122.222, west=-122.508),  # SF → Napa
    dict(north=37.5, south=36.8, east=-121.7, west=-122.2),  # SJ → Santa Cruz
    dict(north=37.9, south=37.3, east=-122.2, west=-122.6),  # SF → Half Moon Bay
    dict(north=37.96, south=37.67, east=-122.32, west=-122.58),  # SF → Sausalito (Golden Gate Bridge)
]

# Short label → full query string for demo hint buttons
_DEMO_ROUTES = [
    ("SF → Muir Woods 🌲", "Drive from San Francisco to Muir Woods, show redwoods and coastal views"),
    ("SF → Napa 🍷", "Road trip from San Francisco to Napa Valley, show wineries and historic towns"),
    ("SJ → Santa Cruz 🏖", "Drive from San Jose to Santa Cruz, show redwoods and beaches"),
    ("SF → Half Moon Bay 🌊", "Road trip from San Francisco to Half Moon Bay, show coastal cliffs and beaches"),
    ("SF → Sausalito 🌉", "Drive from San Francisco to Sausalito via the Golden Gate Bridge, show historic sites and bay views"),
]


# Geographic coverage of the vector baseline seed collection (Bay Area POIs only).
# Routes whose midpoint falls outside this bbox get a "not available" message
# instead of semantically-similar-but-geographically-wrong Bay Area results.
_VECTOR_BASELINE_BBOX = dict(north=38.85, south=36.70, east=-121.50, west=-123.10)


def _route_in_vector_coverage(route_result) -> bool:
    """Return True if the route's midpoint is within the vector baseline's Bay Area coverage."""
    if not route_result or not route_result.route_coords:
        return False
    mid = route_result.route_coords[len(route_result.route_coords) // 2]
    lat, lon = mid
    bb = _VECTOR_BASELINE_BBOX
    return bb["south"] <= lat <= bb["north"] and bb["west"] <= lon <= bb["east"]


def _preload_graphs(loader: GraphLoader) -> None:
    for bbox in _DEMO_BBOXES:
        try:
            loader.load(**bbox)
        except Exception:
            pass  # best-effort; pipeline loads on demand if this fails


@st.cache_resource
def _load_lightweight():
    """Deferred heavy init — osmnx/pandas/shapely imported here, not at module scope."""
    _log("_load_lightweight: start (heavy imports)")
    import osmnx as ox
    _log("_load_lightweight: osmnx done")
    from routeiq.graph import GraphLoader
    from routeiq.ui import MapBuilder
    _log("_load_lightweight: routeiq graph+ui done")

    ox.settings.overpass_url = "https://lz4.overpass-api.de/api"
    ox.settings.overpass_rate_limit = False
    ox.settings.requests_timeout = 30        # per-attempt HTTP timeout
    ox.settings.requests_max_retries = 0     # no OSMnx-internal retries; our mirror loop handles failover
    ox.settings.overpass_settings = "[out:json][timeout:28]"  # server-side limit < client limit

    graph_loader = GraphLoader()
    _log("_load_lightweight: GraphLoader done")
    builder = MapBuilder()
    _log("_load_lightweight: MapBuilder done")
    preload_thread = threading.Thread(
        target=_preload_graphs, args=(graph_loader,), daemon=True
    )
    preload_thread.start()

    # Pre-warm LLM + ChromaDB so first pipeline click has no cold-start delay.
    # Runs in background — page renders immediately regardless.
    def _prewarm_heavy():
        try:
            _load_heavy()
        except Exception:
            pass  # missing API key or import error — pipeline will surface it on first run

    threading.Thread(target=_prewarm_heavy, daemon=True, name="routeiq-prewarm-heavy").start()

    _log("_load_lightweight: done")
    return graph_loader, builder, preload_thread


@st.cache_resource
def _load_heavy():
    """Heavy init (LLM + ChromaDB + pipeline) — deferred until first query."""
    import chromadb
    from routeiq.llm_factory import create_llm
    from routeiq.facade import RouteIQFacade
    from routeiq.rag import POIIndexer, VectorBaseline
    from eval.evaluator import _BAY_AREA_SEED_POIS

    _log("_load_heavy: start")
    llm = create_llm()
    _log("_load_heavy: LLM ready")

    chroma_client = chromadb.PersistentClient(path="./cache/chroma")
    _log("_load_heavy: ChromaDB client ready")
    graph_loader, _, _ = _load_lightweight()

    shared_indexer = POIIndexer(client=chroma_client)
    _log("_load_heavy: shared_indexer ready")
    facade = RouteIQFacade(llm, poi_indexer=shared_indexer, graph_loader=graph_loader, chroma_client=chroma_client)
    _log("_load_heavy: facade ready")

    vector_indexer = POIIndexer(client=chroma_client, collection_name="routeiq_vector_baseline")
    # Re-seed if collection is smaller than half the expected seed size (handles upgrade from 15→95 POIs)
    _needs_enrich = vector_indexer.collection.count() < len(_BAY_AREA_SEED_POIS) // 2
    if _needs_enrich:
        _log(f"_load_heavy: enriching {len(_BAY_AREA_SEED_POIS)} notable Bay Area POIs with Wikipedia…")
        from concurrent.futures import ThreadPoolExecutor
        from routeiq.rag import WikipediaFetcher as _WF
        def _enrich_seed(poi):
            _WF().enrich(poi)
        with ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(_enrich_seed, _BAY_AREA_SEED_POIS))
        _log("_load_heavy: seeding vector baseline…")
        indexed = vector_indexer.index(_BAY_AREA_SEED_POIS)
        _log(f"_load_heavy: seeded {indexed} enriched POIs into vector baseline")
    vbaseline = VectorBaseline(vector_indexer)
    _log("_load_heavy: done")

    return facade, vbaseline


def _run_pipeline_thread(
    query: str,
    cancel_event: threading.Event,
    result_holder: dict,
    progress_dict: dict,
) -> None:
    """Run the RouteIQ pipeline in a background thread; writes status + result to result_holder."""
    facade, _ = _load_heavy()

    def on_progress(step: str, subtask: str) -> None:
        if cancel_event.is_set():
            raise RuntimeError("cancelled")
        if step == "narrate_stream":
            progress_dict["narrative_buffer"] = progress_dict.get("narrative_buffer", "") + subtask
            return
        current = progress_dict.get("current")
        if current and current != step:
            done = set(progress_dict.get("done", set()))
            done.add(current)
            progress_dict["done"] = done
        progress_dict["current"] = step
        progress_dict["subtask"] = subtask

    try:
        state = facade.run(query, on_progress=on_progress)
        result_holder["status"] = "done"
        result_holder["result"] = state
    except RuntimeError as exc:
        if "cancelled" in str(exc).lower():
            result_holder["status"] = "cancelled"
        else:
            result_holder["status"] = "error"
            result_holder["error"] = str(exc)
    except Exception as exc:
        result_holder["status"] = "error"
        result_holder["error"] = str(exc)


_log("starting background init thread")
_bg_init_thread = threading.Thread(
    target=lambda: _load_lightweight(),
    daemon=True,
    name="routeiq-bg-init",
)
_bg_init_thread.start()
_log("background init thread started — page renders now")


# ── Day Trip Planner resources ────────────────────────────────────────────────

@st.cache_resource
def _load_day_trip_resources():
    from routeiq.graph.knowledge_graph import RouteKnowledgeGraph
    from routeiq.agent import build_day_trip_graph
    kg = RouteKnowledgeGraph()
    graph = build_day_trip_graph()
    return kg, graph


def _expand_kg_for_city(kg, city: str) -> None:
    """Geocode city and fetch POIs from Overpass into the KG. Best-effort — silent on failure."""
    try:
        import osmnx as ox
        gdf = ox.geocoder.geocode_to_gdf(city)
        lat = float(gdf.geometry.centroid.y.iloc[0])
        lon = float(gdf.geometry.centroid.x.iloc[0])
    except Exception:
        return

    from routeiq.graph.poi_finder import POIFinder
    pad = 0.15
    pois = POIFinder().find_pois_in_bbox(
        south=lat - pad, north=lat + pad, west=lon - pad, east=lon + pad
    )
    city_short = city.split(",")[0].strip()
    kg.add_city_pois(city_short, lat, lon, pois)


def _dt_stop_card_html(stop: dict, i: int) -> str:
    photo = (stop.get("photo_urls") or [stop.get("image_url")] or [None])[0] or ""
    img_html = (
        f'<img src="{photo}" style="width:96px;height:76px;object-fit:cover;border-radius:8px;flex-shrink:0;">'
        if photo else
        '<div style="width:96px;height:76px;border-radius:8px;background:#f3f4f6;flex-shrink:0;"></div>'
    )
    rating = stop.get("rating")
    review_count = stop.get("review_count")
    review_source = stop.get("review_source") or "Unknown"
    rating_str = f"⭐ {rating:.1f}" if rating is not None else "—"
    count_str = f" ({review_count:,})" if review_count else ""
    activities = stop.get("activities") or []
    act_badges = "".join(
        f'<span style="font-size:11px;background:#e0e7ff;color:#3730a3;border-radius:12px;padding:2px 8px;">{a}</span>'
        for a in activities[:3]
    )
    visitor_quote = stop.get("visitor_quote") or ""
    visitor_summary = stop.get("visitor_summary") or ""
    why_visit = stop.get("why_visit") or ""
    hours = stop.get("hours") or ""

    return f"""
<div style="border:1px solid #e5e7eb;border-radius:12px;padding:14px;margin-bottom:14px;background:#fff;">
  <div style="display:flex;gap:12px;align-items:flex-start;">
    {img_html}
    <div style="flex:1;min-width:0;">
      <div style="font-size:11px;color:#6b7280;">Stop {i} · {stop.get('arrival_time','')} – {stop.get('departure_time','')}</div>
      <div style="font-size:16px;font-weight:700;margin:2px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{stop.get('name','')}</div>
      <div style="font-size:12px;color:#059669;">{rating_str}{count_str} · <span style="color:#9ca3af;">{review_source}</span></div>
    </div>
  </div>
  {f'<div style="font-size:13px;color:#374151;margin-top:10px;line-height:1.5;">{why_visit}</div>' if why_visit else ''}
  {f'<div style="font-size:12px;font-style:italic;color:#4b5563;margin-top:6px;border-left:3px solid #6366f1;padding-left:8px;">{visitor_quote}</div>' if visitor_quote else ''}
  {f'<div style="font-size:12px;color:#6b7280;margin-top:4px;line-height:1.5;">{visitor_summary}</div>' if visitor_summary else ''}
  {f'<div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:4px;">{act_badges}</div>' if act_badges else ''}
  {f'<div style="font-size:11px;color:#9ca3af;margin-top:6px;">🕐 {hours}</div>' if hours else ''}
</div>"""


def _run_dt_planning_thread(initial_state: dict, config: dict, graph, result_holder: dict) -> None:
    try:
        for _ in graph.stream(initial_state, config=config):
            pass
        result_holder["status"] = "interrupted"
    except Exception as exc:
        result_holder["status"] = "error"
        result_holder["error"] = str(exc)


def _run_dt_narrate_thread(config: dict, graph, result_holder: dict) -> None:
    from langgraph.types import Command
    try:
        final = graph.invoke(Command(resume={"approved": True}), config=config)
        result_holder["narrative"] = final.get("narrative")
        result_holder["draft"] = final.get("draft_itinerary")
        result_holder["route_coords"] = final.get("route_coords") or []
        result_holder["status"] = "done"
    except Exception as exc:
        result_holder["status"] = "error"
        result_holder["error"] = str(exc)


def _run_dt_refine_thread(feedback: str, config: dict, graph, result_holder: dict) -> None:
    from langgraph.types import Command
    try:
        for _ in graph.stream(
            Command(resume={"approved": False, "feedback": feedback}),
            config=config,
        ):
            pass
        result_holder["status"] = "interrupted"
    except Exception as exc:
        result_holder["status"] = "error"
        result_holder["error"] = str(exc)


# ── Header ────────────────────────────────────────────────────────────────────

st.title("🗺 RouteIQ")
_provider = os.environ.get("LLM_PROVIDER", "anthropic")
_model = os.environ.get("LLM_MODEL", "claude-sonnet-4-6")
st.caption(f"Scenic route intelligence · GraphRAG + Wikipedia · Bay Area & beyond · Model: **{_provider}/{_model}**")

if _bg_init_thread.is_alive():
    st.info(
        "⏳ Loading RouteIQ components in the background — "
        "first query starts once loading finishes (~15–30 s).",
        icon=None,
    )

# ── Tabs ─────────────────────────────────────────────────────────────────────

tab1, tab2 = st.tabs(["🏙 Day Trip Planner", "🗺 Route Planner"])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Day Trip Planner
# ═══════════════════════════════════════════════════════════════════════════════

with tab1:
    st.markdown("**Plan a scenic day in any city — the agent picks stops, you approve.**")

    # ── Inputs ────────────────────────────────────────────────────────────────

    dt_col1, dt_col2, dt_col3, dt_col4 = st.columns([3, 2, 1, 1])
    with dt_col1:
        dt_city = st.text_input(
            "City", value="San Francisco, CA",
            placeholder="San Francisco, CA", key="dt_city_input"
        )
    with dt_col2:
        dt_prefs = st.multiselect(
            "Interests", options=["nature", "history", "food", "art", "architecture"],
            default=["nature", "history"], key="dt_prefs"
        )
    with dt_col3:
        dt_hours = st.slider("Hours", min_value=4, max_value=12, value=8, step=1, key="dt_hours")
    with dt_col4:
        dt_start = st.selectbox(
            "Start time",
            options=["8:00 AM", "9:00 AM", "10:00 AM", "11:00 AM"],
            index=1, key="dt_start"
        )

    dt_phase = st.session_state.get("dt_phase", "idle")
    dt_thread_id = st.session_state.setdefault("dt_thread_id", str(uuid.uuid4()))

    plan_btn = st.button(
        "Plan My Day ›", type="primary",
        disabled=dt_phase in ("planning", "narrating"),
        key="dt_plan_btn",
    )

    if plan_btn and dt_city.strip() and dt_phase not in ("planning", "narrating"):
        kg, dt_graph = _load_day_trip_resources()

        # Pre-flight KG check — expand for unknown cities
        known = kg.known_cities()
        city_short = dt_city.split(",")[0].strip()
        if city_short not in known:
            with st.spinner(f"Fetching POIs for {dt_city}…"):
                _expand_kg_for_city(kg, dt_city)

        # Reset session for a fresh plan
        new_thread_id = str(uuid.uuid4())
        st.session_state["dt_thread_id"] = new_thread_id
        st.session_state["dt_phase"] = "planning"
        st.session_state.pop("dt_draft", None)
        st.session_state.pop("dt_narrative", None)
        st.session_state.pop("dt_route_coords", None)
        st.session_state["dt_city_val"] = dt_city
        st.session_state["dt_prefs_val"] = dt_prefs
        st.session_state["dt_hours_val"] = dt_hours
        st.session_state["dt_start_val"] = dt_start

        rh: dict = {}
        dt_progress: dict = {"current": None, "done": set(), "subtask": ""}
        from routeiq.agent.day_trip_agent import register_progress as _dt_register
        _dt_register(new_thread_id, dt_progress)
        st.session_state["dt_result_holder"] = rh
        st.session_state["dt_progress"] = dt_progress
        st.session_state["dt_progress_thread_id"] = new_thread_id
        initial_state = {
            "messages": [],
            "city": dt_city,
            "preferences": dt_prefs,
            "time_budget_hours": float(dt_hours),
            "start_time": dt_start,
            "draft_itinerary": None,
            "route_coords": None,
            "approved": False,
            "narrative": None,
        }
        config = {"configurable": {"thread_id": new_thread_id}}
        thread = threading.Thread(
            target=_run_dt_planning_thread,
            args=(initial_state, config, dt_graph, rh),
            daemon=True,
        )
        st.session_state["dt_thread"] = thread
        thread.start()
        st.rerun()

    # ── Planning poll ─────────────────────────────────────────────────────────

    if dt_phase == "planning":
        dt_progress = st.session_state.get("dt_progress", {})
        _dt_stepper_ph = st.empty()
        _dt_stepper_ph.markdown(_render_stepper(dt_progress, steps=_DT_STEPS), unsafe_allow_html=True)

        thread = st.session_state.get("dt_thread")
        if thread and thread.is_alive():
            time.sleep(0.5)
            st.rerun()
        else:
            # Clean up registry entry
            from routeiq.agent.day_trip_agent import unregister_progress as _dt_unreg
            _dt_unreg(st.session_state.get("dt_progress_thread_id", ""))

            rh = st.session_state.get("dt_result_holder", {})
            if rh.get("status") == "interrupted":
                _, dt_graph = _load_day_trip_resources()
                config = {"configurable": {"thread_id": st.session_state["dt_thread_id"]}}
                snapshot = dt_graph.get_state(config)
                draft = snapshot.values.get("draft_itinerary")
                if draft:
                    st.session_state["dt_draft"] = draft
                    st.session_state["dt_route_coords"] = snapshot.values.get("route_coords") or []
                    st.session_state["dt_phase"] = "draft_ready"
                else:
                    st.session_state["dt_phase"] = "idle"
                    st.error("Agent did not produce a draft. Try again.")
            else:
                st.session_state["dt_phase"] = "idle"
                st.error(f"Planning error: {rh.get('error', 'unknown')}")
            st.rerun()

    # ── Draft ready — show cards + approve/refine ─────────────────────────────

    if dt_phase in ("draft_ready", "narrating", "done"):
        draft = st.session_state.get("dt_draft") or {}
        stops = draft.get("stops") or []

        if stops:
            city_val = st.session_state.get("dt_city_val", dt_city)
            hours_val = st.session_state.get("dt_hours_val", dt_hours)
            st.markdown(
                f"**Draft itinerary — {city_val} · {hours_val}h · {len(stops)} stops**"
            )
            cards_html = (
                '<div style="max-height:500px;overflow-y:auto;padding-right:6px;">'
                + "".join(_dt_stop_card_html(s, i) for i, s in enumerate(stops, 1))
                + "</div>"
            )
            st.components.v1.html(cards_html, height=510, scrolling=False)

        # Approve / Refine row (only when waiting for decision)
        if dt_phase == "draft_ready":
            ap_col, rf_col = st.columns([1, 2])
            with ap_col:
                if st.button("✅ Approve & Generate Narrative", type="primary", key="dt_approve"):
                    _, dt_graph = _load_day_trip_resources()
                    config = {"configurable": {"thread_id": st.session_state["dt_thread_id"]}}
                    rh2: dict = {}
                    st.session_state["dt_result_holder"] = rh2
                    st.session_state["dt_phase"] = "narrating"
                    t = threading.Thread(
                        target=_run_dt_narrate_thread,
                        args=(config, dt_graph, rh2), daemon=True
                    )
                    st.session_state["dt_thread"] = t
                    t.start()
                    st.rerun()

            with rf_col:
                feedback_text = st.text_input(
                    "Feedback", placeholder="e.g. Add more outdoor stops, no museums",
                    key="dt_feedback_input", label_visibility="collapsed"
                )
                if st.button("🔄 Refine", key="dt_refine") and feedback_text.strip():
                    _, dt_graph = _load_day_trip_resources()
                    refine_tid = st.session_state["dt_thread_id"]
                    config = {"configurable": {"thread_id": refine_tid}}
                    rh3: dict = {}
                    dt_progress3: dict = {"current": None, "done": set(), "subtask": ""}
                    from routeiq.agent.day_trip_agent import register_progress as _dt_register3
                    _dt_register3(refine_tid, dt_progress3)
                    st.session_state["dt_result_holder"] = rh3
                    st.session_state["dt_progress"] = dt_progress3
                    st.session_state["dt_progress_thread_id"] = refine_tid
                    st.session_state["dt_phase"] = "planning"
                    t = threading.Thread(
                        target=_run_dt_refine_thread,
                        args=(feedback_text.strip(), config, dt_graph, rh3), daemon=True
                    )
                    st.session_state["dt_thread"] = t
                    t.start()
                    st.rerun()

    # ── Narrating poll ────────────────────────────────────────────────────────

    if dt_phase == "narrating":
        st.info("✍️ Writing your narrative…")
        thread = st.session_state.get("dt_thread")
        if thread and thread.is_alive():
            time.sleep(0.5)
            st.rerun()
        else:
            rh = st.session_state.get("dt_result_holder", {})
            if rh.get("status") == "done":
                st.session_state["dt_narrative"] = rh.get("narrative")
                if rh.get("draft"):
                    st.session_state["dt_draft"] = rh["draft"]
                if rh.get("route_coords"):
                    st.session_state["dt_route_coords"] = rh["route_coords"]
                st.session_state["dt_phase"] = "done"
            else:
                st.session_state["dt_phase"] = "draft_ready"
                st.error(f"Narration error: {rh.get('error', 'unknown')}")
            st.rerun()

    # ── Done — map + cards + narrative ───────────────────────────────────────

    if dt_phase == "done":
        draft = st.session_state.get("dt_draft") or {}
        stops = draft.get("stops") or []
        route_coords = st.session_state.get("dt_route_coords") or []
        city_val = st.session_state.get("dt_city_val", "")
        hours_val = st.session_state.get("dt_hours_val", "")

        if stops:
            st.markdown(f"**{city_val} · {hours_val}h · {len(stops)} stops**")
            map_col, cards_col = st.columns([3, 2])

            with map_col:
                import folium
                from folium.plugins import AntPath
                center_lat = sum(s.get("lat", 0) for s in stops) / len(stops)
                center_lon = sum(s.get("lon", 0) for s in stops) / len(stops)
                m = folium.Map(
                    location=[center_lat, center_lon],
                    zoom_start=13,
                    tiles="CartoDB positron",
                )
                if route_coords:
                    AntPath(
                        locations=route_coords,
                        color="#6366f1",
                        weight=4,
                        opacity=0.85,
                    ).add_to(m)
                for i, s in enumerate(stops, 1):
                    lat, lon = s.get("lat"), s.get("lon")
                    if lat and lon:
                        folium.Marker(
                            [lat, lon],
                            popup=f"{i}. {s.get('name','')}",
                            icon=folium.DivIcon(
                                html=(
                                    f'<div style="background:#6366f1;color:#fff;border-radius:50%;'
                                    f'width:24px;height:24px;text-align:center;line-height:24px;'
                                    f'font-weight:700;font-size:12px;">{i}</div>'
                                ),
                            ),
                        ).add_to(m)
                st_folium(m, height=480, use_container_width=True, returned_objects=[])

            with cards_col:
                cards_html = (
                    '<div style="max-height:480px;overflow-y:auto;padding-right:6px;">'
                    + "".join(render_dt_card(s, i) for i, s in enumerate(stops, 1))
                    + "</div>"
                    + IMAGE_MODAL_HTML
                )
                st.components.v1.html(cards_html, height=490, scrolling=False)

        narrative = st.session_state.get("dt_narrative") or ""
        if narrative:
            with st.expander("Trip narrative", expanded=True):
                st.markdown(narrative)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Route Planner (existing code, unchanged)
# ═══════════════════════════════════════════════════════════════════════════════

with tab2:
    # ── Query input ───────────────────────────────────────────────────────────

    _pipeline_status = st.session_state.get("_pipeline_status", "idle")
    _is_running = _pipeline_status == "running"

    # Demo route hint buttons
    st.caption("Try a demo route:")
    hint_cols = st.columns(len(_DEMO_ROUTES))
    for col, (label, route) in zip(hint_cols, _DEMO_ROUTES):
        if col.button(label, key=f"hint_{label}", disabled=_is_running, use_container_width=True):
            st.session_state["route_query"] = route
            st.session_state["_auto_run"] = True
            st.rerun()

    st.markdown(
        '<p style="font-size:12px;color:#6b7280;margin:2px 0 10px 0;">'
        "✅ <b>Bay Area routes above use locally cached OSM data — no server wait.</b> "
        "Routes outside the Bay Area download road network and POI data from OpenStreetMap servers on first run "
        "and <b>may take 1–3 minutes</b>."
        "</p>",
        unsafe_allow_html=True,
    )

    query_input = st.text_input(
        "route_query",
        placeholder="e.g. Drive from San Francisco to Sausalito via the Golden Gate Bridge, show historic sites and bay views",
        label_visibility="collapsed",
        key="route_query",
    )

    run_col, cancel_col = st.columns([4, 1])
    with run_col:
        run_btn = st.button("Find Scenic Stops ›", type="primary", disabled=_is_running, use_container_width=True)
    with cancel_col:
        cancel_btn = st.button("⛔ Cancel", disabled=not _is_running, use_container_width=True)

    _auto_run = st.session_state.pop("_auto_run", False)

    # Cancel: signal the background thread
    if cancel_btn and _is_running:
        cancel_ev = st.session_state.get("_pipeline_cancel")
        if cancel_ev:
            cancel_ev.set()

    # Start a new run
    if (run_btn or _auto_run) and query_input.strip() and not _is_running:
        cancel_event = threading.Event()
        result_holder: dict = {}
        progress_dict: dict = {"current": None, "done": set(), "subtask": "", "narrative_buffer": ""}

        st.session_state["_pipeline_cancel"] = cancel_event
        st.session_state["_pipeline_result_holder"] = result_holder
        st.session_state["_pipeline_progress"] = progress_dict
        st.session_state["_pipeline_status"] = "running"
        st.session_state["_running_query"] = query_input.strip()
        st.session_state.pop("result", None)
        st.session_state.pop("vector_narrative", None)

        thread = threading.Thread(
            target=_run_pipeline_thread,
            args=(query_input.strip(), cancel_event, result_holder, progress_dict),
            daemon=True,
        )
        st.session_state["_pipeline_thread"] = thread
        thread.start()
        st.rerun()

    # Poll while pipeline is running
    if _is_running:
        progress_dict = st.session_state["_pipeline_progress"]
        thread = st.session_state.get("_pipeline_thread")

        stepper_placeholder = st.empty()
        stepper_placeholder.markdown(_render_stepper(progress_dict), unsafe_allow_html=True)

        narrative_buf = progress_dict.get("narrative_buffer", "")
        if narrative_buf:
            tail = narrative_buf[-450:]
            display = ("…" + tail) if len(narrative_buf) > 450 else tail
            st.markdown(
                f'<div style="font-size:13px;line-height:1.7;'
                f'padding:10px 14px;border-radius:8px;border:1px solid rgba(128,128,128,0.2);'
                f'background:rgba(128,128,128,0.06);">'
                f'<span style="font-size:11px;opacity:0.55;display:block;margin-bottom:6px;">Generating narrative…</span>'
                f'{display}</div>',
                unsafe_allow_html=True,
            )

        if thread and thread.is_alive():
            time.sleep(0.35)
            st.rerun()
        else:
            result_holder = st.session_state.get("_pipeline_result_holder", {})
            status = result_holder.get("status")
            if status == "done":
                st.session_state["result"] = result_holder["result"]
                st.session_state["last_query"] = st.session_state.get("_running_query", "")
                st.session_state.pop("vector_narrative", None)
            elif status == "cancelled":
                st.session_state.pop("result", None)
                st.session_state["_pipeline_cancelled"] = True
            else:
                err = result_holder.get("error", "Unknown error")
                st.session_state["result"] = {"error": True, "narrative": f"Pipeline error: {err}"}
            st.session_state["_pipeline_status"] = "idle"
            st.rerun()
        st.stop()

    result = st.session_state.get("result")

    if result is None:
        if st.session_state.get("_pipeline_cancelled"):
            del st.session_state["_pipeline_cancelled"]
            st.info("⛔ Route query was cancelled.")
        else:
            st.info("Enter a route query above, then click **Find Scenic Stops** to begin.")
        st.stop()

    # ── Error path ────────────────────────────────────────────────────────────

    if result.get("error"):
        st.warning(result.get("narrative") or "Something went wrong. Please try a different query.")
        st.stop()

    # ── Successful result ─────────────────────────────────────────────────────

    route_result = result["route_result"]
    top_pois = result.get("top_pois") or []
    narrative = result.get("narrative", "")
    origin = result.get("origin", "")
    destination = result.get("destination", "")

    # ── Controls row ──────────────────────────────────────────────────────────

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

    # ── Two-column layout: map + stop cards ───────────────────────────────────

    map_col, card_col = st.columns([3, 2], gap="medium")

    filtered_pois = [sp for sp in top_pois if sp.poi.category in selected_cats]

    with map_col:
        _, _map_builder, _ = _load_lightweight()  # cached — instant by the time results render
        folium_map = _map_builder.build(
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
                    + IMAGE_MODAL_HTML
                )
                st.components.v1.html(cards_html, height=510, scrolling=False)
            else:
                st.info("No stops match the selected categories.")
        else:
            # Vector baseline — semantic-only, no graph constraints
            if not _route_in_vector_coverage(route_result):
                st.info(
                    "Vector Baseline covers Bay Area demo routes only. "
                    "GraphRAG works for any region."
                )
            else:
                last_query = st.session_state.get("last_query", "")
                _, vector_baseline = _load_heavy()
                vector_results = vector_baseline.query(last_query, n_results=5) if last_query else []

                if vector_results:
                    cards_html = (
                        '<div style="height:500px;overflow-y:auto;padding-right:6px;">'
                        + "".join(render_vector_card(r, i) for i, r in enumerate(vector_results, 1))
                        + "</div>"
                        + IMAGE_MODAL_HTML
                    )
                    st.components.v1.html(cards_html, height=510, scrolling=False)
                else:
                    st.info("Run a route query first to populate the vector baseline.")

    # ── Narrative ─────────────────────────────────────────────────────────────

    narrative_label = (
        "Route narrative — Vector Baseline"
        if view_mode == "Vector Baseline"
        else "Route narrative — GraphRAG"
    )
    with st.expander(narrative_label, expanded=True):
        if view_mode == "Vector Baseline":
            if not _route_in_vector_coverage(route_result):
                st.caption("Vector Baseline seed collection covers Bay Area only. Showing GraphRAG narrative.")
                st.markdown(narrative)
            else:
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
