"""RouteIQ Streamlit app — scenic route intelligence with GraphRAG."""
from __future__ import annotations

import os
import time
import threading
import uuid
from pathlib import Path

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

import logging
from logging.handlers import RotatingFileHandler
import os as _os

# Terminal: WARNING+ only — keeps Streamlit output readable
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
# File: DEBUG for routeiq namespace only — grep-friendly, processed by Claude
_os.makedirs("logs", exist_ok=True)
_fh = RotatingFileHandler("logs/routeiq.log", maxBytes=5_000_000, backupCount=2)
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(name)s — %(message)s", datefmt="%H:%M:%S"))
logging.getLogger("routeiq").addHandler(_fh)
logging.getLogger("routeiq").setLevel(logging.DEBUG)
_logger = logging.getLogger("routeiq.app")
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
.riq-timing{font-size:12px;font-weight:400;margin-left:6px;opacity:0.7;}
.riq-timing-live{color:#3b82f6;opacity:1;}
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
    import time as _time
    if steps is None:
        steps = _STEPS
    current = state.get("current")
    done = state.get("done", set())
    subtask = state.get("subtask", "")
    step_times: dict = state.get("step_times") or {}
    step_start: float | None = state.get("step_start")

    rows = [_STEPPER_CSS, '<div class="riq-stepper">']
    for i, (step_id, label, icon) in enumerate(steps):
        if step_id in done:
            icon_cls, label_cls, display_icon = "", "riq-done", "✅"
        elif step_id == current:
            icon_cls, label_cls, display_icon = "riq-blink", "riq-active", icon
        else:
            icon_cls, label_cls, display_icon = "", "riq-pending", "⭕"

        # Timing badge: elapsed for done steps, live counter for active step
        timing_html = ""
        if step_id in step_times:
            t = step_times[step_id]
            timing_html = f'<span class="riq-timing">({t:.0f}s)</span>'
        elif step_id == current and step_start is not None:
            live = _time.perf_counter() - step_start
            timing_html = f'<span class="riq-timing riq-timing-live">({live:.0f}s…)</span>'

        rows.append(
            f'<div class="riq-step">'
            f'<span class="riq-icon {icon_cls}">{display_icon}</span>'
            f'<span class="riq-label {label_cls}">{label}{timing_html}</span>'
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
    from routeiq.graph.knowledge_graph import get_kg
    from routeiq.agent import build_day_trip_graph
    kg = get_kg()
    graph = build_day_trip_graph()
    return kg, graph


def _normalize_city_name(city: str) -> str:
    """Fix run-together city names: 'NewYork, NY' → 'New York, NY'.

    Inserts a space before any uppercase letter that immediately follows a
    lowercase letter in the city part (before the comma).  State/country
    suffixes after the comma are preserved unchanged.
    """
    import re
    parts = city.split(",", 1)
    fixed = re.sub(r"([a-z])([A-Z])", r"\1 \2", parts[0].strip())
    return f"{fixed},{parts[1]}" if len(parts) > 1 else fixed


def _expand_kg_for_city(kg, city: str) -> int:
    """Geocode city and fetch POIs from Overpass into the KG.

    Returns the number of POIs added (0 on any failure or empty result).
    Only registers the city in the KG when at least one POI is found — a city
    node with 0 POIs would be treated as "known" on the next call and silently
    skip the pre-flight, permanently hiding the failure.

    Applies light name normalisation (camelCase fix) before geocoding so that
    inputs like 'NewYork, NY' resolve correctly without requiring an exact spelling.
    """
    import re
    city = _normalize_city_name(city)
    try:
        import osmnx as ox
        from shapely.geometry import Point
        gdf = ox.geocoder.geocode_to_gdf(city)
        city_poly = gdf.geometry.iloc[0]  # actual administrative boundary polygon
        lat = float(gdf.geometry.centroid.y.iloc[0])
        lon = float(gdf.geometry.centroid.x.iloc[0])
    except Exception as exc:
        _logger.warning("_expand_kg_for_city: geocode failed for %r: %s", city, exc)
        return 0

    from routeiq.graph.poi_finder import POIFinder, OverpassUnavailableError
    pad = 0.15
    try:
        pois = POIFinder().find_pois_in_bbox(
            south=lat - pad, north=lat + pad, west=lon - pad, east=lon + pad
        )
    except OverpassUnavailableError:
        st.warning(
            f"⚠️ OpenStreetMap POI service is temporarily unavailable for **{city}**. "
            "Planning will continue — you can still add specific landmarks using the "
            "**Refine** box (e.g. *Add Griffith Observatory*).",
            icon=None,
        )
        return 0
    # Keep only POIs inside the city's administrative boundary — the bbox above
    # is a coarse pre-filter for Overpass; the polygon clip prevents out-of-city
    # attractions (e.g. Marin County POIs for a SF query) from entering the KG.
    pois = [p for p in pois if city_poly.contains(Point(p.lon, p.lat))]
    if not pois:
        _logger.warning("_expand_kg_for_city: 0 POIs found for %r (lat=%.4f lon=%.4f) — city not registered", city, lat, lon)
        return 0
    city_short = city.split(",")[0].strip()
    kg.add_city_pois(city_short, lat, lon, pois)
    _logger.info("_expand_kg_for_city: added %d POIs for %r", len(pois), city)
    return len(pois)


def _render_dt_map(stops: list, route_coords: list, height: int = 340):
    """Build a Folium map for Day Trip stops. AntPath when road coords available, dashed PolyLine otherwise."""
    import folium
    from folium.plugins import AntPath

    lats = [s["lat"] for s in stops if s.get("lat")]
    lons = [s["lon"] for s in stops if s.get("lon")]
    center_lat = sum(lats) / len(lats) if lats else 0
    center_lon = sum(lons) / len(lons) if lons else 0
    m = folium.Map(location=[center_lat, center_lon], zoom_start=13, tiles="CartoDB positron")

    if len(lats) > 1:
        m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])

    if route_coords:
        AntPath(
            locations=route_coords,
            delay=800,
            weight=5,
            color="#6366f1",
            pulse_color="#ffffff",
            dash_array=[10, 20],
        ).add_to(m)
    else:
        # Straight-line fallback — OSM graph not yet cached for this city
        latlon_pairs = [(s["lat"], s["lon"]) for s in stops if s.get("lat") and s.get("lon")]
        if latlon_pairs:
            folium.PolyLine(
                latlon_pairs, color="#6366f1", weight=5, opacity=0.75, dash_array="10 15"
            ).add_to(m)

    for i, s in enumerate(stops, 1):
        lat, lon = s.get("lat"), s.get("lon")
        if lat and lon:
            folium.Marker(
                [lat, lon],
                popup=f"{i}. {s.get('name', '')}",
                icon=folium.DivIcon(
                    html=(
                        f'<div style="background:#6366f1;color:#fff;border-radius:50%;'
                        f'width:24px;height:24px;text-align:center;line-height:24px;'
                        f'font-weight:700;font-size:12px;">{i}</div>'
                    ),
                ),
            ).add_to(m)
    return m


def _run_dt_planning_thread(initial_state: dict, config: dict, graph, result_holder: dict) -> None:
    from langgraph.errors import GraphInterrupt
    try:
        chunk_count = 0
        for chunk in graph.stream(initial_state, config=config):
            chunk_count += 1
            _logger.debug("dt_plan_thread chunk #%d: %s", chunk_count, list(chunk.keys()))
        _logger.debug("dt_plan_thread stream exhausted normally after %d chunks", chunk_count)
        result_holder["status"] = "interrupted"
    except GraphInterrupt as gi:
        _logger.debug("dt_plan_thread GraphInterrupt: %s", gi)
        result_holder["status"] = "interrupted"
    except Exception as exc:
        _logger.exception("dt_plan_thread EXCEPTION: %s", exc)
        result_holder["status"] = "error"
        result_holder["error"] = str(exc)
    _logger.debug("dt_plan_thread final status=%s", result_holder.get("status"))


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
    from langgraph.errors import GraphInterrupt
    try:
        for _ in graph.stream(
            Command(resume={"approved": False, "feedback": feedback}),
            config=config,
        ):
            pass
        result_holder["status"] = "interrupted"
    except GraphInterrupt:
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

import re as _re
import json as _json
_US_CITIES: list[str] = _json.load(open("data/us_cities.json"))
_OTHER_CITY_OPTION = "✈ Other city (type below)…"
_CITY_OPTIONS = _US_CITIES + [_OTHER_CITY_OPTION]

_ACTIVITY_TEXT_KEYWORDS: dict[str, list[str]] = {
    "hiking":    ["hiking", "hike", "trail", "trails", "trek", "trekking"],
    "biking":    ["biking", "bike", "cycling", "cycle"],
    "swimming":  ["swimming", "swim"],
    "kayaking":  ["kayaking", "kayak"],
    "kids":      ["kids", "kid", "family", "families", "children", "child", "toddler"],
    "picnic":    ["picnic"],
    "history":   ["history", "historic", "museum", "mission", "ruins", "castle", "fort", "heritage", "battlefield"],
    "food":      ["food", "restaurant", "winery", "brewery", "bar", "nightlife", "cocktail", "jazz", "lunch", "dinner", "coffee", "cafe"],
    "scenic":    ["scenic", "viewpoint", "overlook", "panoram", "vista", "view", "attraction", "attractions", "sightseeing", "places to visit"],
}

def _infer_activities_from_text(text: str) -> list[str]:
    """Return activity tags detected in a free-text style phrase."""
    low = text.lower()
    return [act for act, kws in _ACTIVITY_TEXT_KEYWORDS.items() if any(kw in low for kw in kws)]


def _cached_city_names() -> list[str]:
    """Cities already in the local KG + rating cache — shown as hint under city selectbox."""
    from routeiq.graph.knowledge_graph import get_kg
    names: set[str] = set(get_kg().known_cities())
    rating_dir = Path("cache/ratings")
    if rating_dir.exists():
        for f in rating_dir.glob("llm_synthetic_*.json"):
            m = _re.match(r"llm_synthetic_(.+)_([a-z]{2})\.json", f.name)
            if m:
                names.add(f"{m.group(1).replace('_', ' ').title()}, {m.group(2).upper()}")
    return sorted(names)

with tab1:
    st.markdown("**Plan a scenic day in any city — the agent picks stops, you approve.**")

    # ── Inputs ────────────────────────────────────────────────────────────────

    dt_col1, dt_col3, dt_col4 = st.columns([4, 1, 1])
    with dt_col1:
        dt_city_sel = st.selectbox(
            "City",
            options=_CITY_OPTIONS,
            index=0,
            key="dt_city_sel",
        )
        if dt_city_sel == _OTHER_CITY_OPTION:
            dt_city = st.text_input(
                "City name",
                placeholder="e.g. Boston, MA or Tokyo, Japan",
                key="dt_city_custom",
            )
            st.caption("Any city worldwide — spelling is auto-corrected. First use ~30 s.")
        else:
            dt_city = dt_city_sel
            _cached = _cached_city_names()
            if _cached:
                st.caption("✅ Cached locally: " + " · ".join(_cached))
    with dt_col3:
        dt_hours = st.slider("Hours", min_value=4, max_value=12, value=8, step=1, key="dt_hours")
    with dt_col4:
        dt_start = st.selectbox(
            "Start time",
            options=["8:00 AM", "9:00 AM", "10:00 AM", "11:00 AM"],
            index=1, key="dt_start"
        )

    dt_user_context = st.text_input(
        "What do you want to do? (optional)",
        placeholder="e.g. top attractions and a nice lunch spot, scenic coastal hike with kids",
        key="dt_user_context",
    )
    if dt_user_context:
        _preview = _infer_activities_from_text(dt_user_context)
        if _preview:
            st.caption(f"→ {', '.join(_preview)}  (will be refined by classifier on plan)")
        else:
            st.caption("→ top scenic spots  (no specific activity detected — 5 scenic fills)")

    dt_phase = st.session_state.get("dt_phase", "idle")
    dt_thread_id = st.session_state.setdefault("dt_thread_id", str(uuid.uuid4()))

    _city_missing = dt_city_sel == _OTHER_CITY_OPTION and not dt_city.strip()
    plan_btn = st.button(
        "Plan My Day ›", type="primary",
        disabled=dt_phase in ("planning", "narrating") or _city_missing,
        key="dt_plan_btn",
    )
    if _city_missing:
        st.caption("Enter a city name above to enable planning.")

    # Show persisted planning error (cleared when user tries again)
    if dt_phase == "idle":
        _last_err = st.session_state.pop("dt_last_error", None)
        if _last_err:
            _err_str = str(_last_err)
            if "stops" in _last_err and "missing" in _last_err:
                st.error(
                    "The planner couldn't build an itinerary for that request — "
                    "the activity or context wasn't specific enough for the available POIs. "
                    "Try selecting an interest above (e.g. Food & Drink, History) or rephrasing your context."
                )
            else:
                st.error(f"Planning error: {_err_str[:300]}")

    if plan_btn and dt_city.strip() and dt_phase not in ("planning", "narrating"):
        kg, dt_graph = _load_day_trip_resources()

        # Pre-flight KG check — normalize name, expand KG for unknown cities
        dt_city_norm = _normalize_city_name(dt_city)
        known = kg.known_cities()
        city_short = dt_city_norm.split(",")[0].strip()
        if city_short not in known:
            spinner_label = f"Fetching POIs for {dt_city_norm}…" + (
                f" (corrected from '{dt_city}')" if dt_city_norm != dt_city else ""
            )
            with st.spinner(spinner_label):
                poi_count = _expand_kg_for_city(kg, dt_city_norm)
            if poi_count == 0:
                st.error(
                    f"Could not find any landmarks for **{dt_city_norm}**. "
                    "Try a more specific city name (e.g. \"New York, NY, USA\") or check your spelling."
                )
                st.stop()

        # Plan A — prefetch POI knowledge (Wikipedia + ratings + activity tags) for this
        # city before the agent runs. Warm cities (within the 21-day TTL) return instantly;
        # cold cities pay the provider-call cost here instead of inside the ReAct loop.
        from routeiq.rag.city_prefetcher import CityPrefetcher
        city_pois = kg.get_pois_for_city(city_short)
        with st.spinner(f"Building POI knowledge base for {dt_city_norm}…"):
            CityPrefetcher().prefetch(dt_city_norm, city_pois)

        _logger.info("plan_btn clicked city=%r start_time=%r hours=%s phase_was=%s",
                     dt_city, dt_start, dt_hours, dt_phase)

        # Reset session for a fresh plan
        new_thread_id = str(uuid.uuid4())
        st.session_state["dt_thread_id"] = new_thread_id
        st.session_state["dt_phase"] = "planning"
        st.session_state.pop("dt_draft", None)
        st.session_state.pop("dt_narrative", None)
        st.session_state.pop("dt_route_coords", None)
        st.session_state["dt_city_val"] = dt_city
        st.session_state["dt_hours_val"] = dt_hours
        st.session_state["dt_start_val"] = dt_start

        rh: dict = {}
        dt_progress: dict = {"current": None, "done": set(), "subtask": ""}
        from routeiq.agent.day_trip_agent import register_progress as _dt_register
        _dt_register(new_thread_id, dt_progress)
        st.session_state["dt_result_holder"] = rh
        st.session_state["dt_progress"] = dt_progress
        st.session_state["dt_progress_thread_id"] = new_thread_id
        _explicit: list[str] = []
        _semantic_queries: dict = {}
        if os.getenv("ACTIVITY_PROVIDER", "osm").lower() == "finetuned" and not _explicit:
            from routeiq.activities.finetuned_classifier import create_query_intent_classifier
            _clf = create_query_intent_classifier()
            _clf_result = _clf.classify(dt_user_context)
            final_activities = _clf_result["activities"]
            _semantic_queries = _clf_result["semantic_queries"]
            _logger.info("plan_btn: finetuned classifier → activities=%s", final_activities)
        else:
            _inferred = _infer_activities_from_text(dt_user_context) if not _explicit else []
            final_activities = _explicit or _inferred
            if _inferred:
                _logger.info("plan_btn: inferred activities from user_context text: %s", _inferred)

        initial_state = {
            "messages": [],
            "city": dt_city_norm,
            "preferences": final_activities,
            "time_budget_hours": float(dt_hours),
            "start_time": dt_start,
            "draft_itinerary": None,
            "route_coords": None,
            "approved": False,
            "narrative": None,
            "activities": final_activities,
            "user_context": dt_user_context.strip(),
            "activity_fallback_note": None,
            "poi_cache": {},
            "semantic_queries": _semantic_queries,
        }
        config = {"configurable": {"thread_id": new_thread_id}}
        thread = threading.Thread(
            target=_run_dt_planning_thread,
            args=(initial_state, config, dt_graph, rh),
            daemon=True,
        )
        st.session_state["dt_thread"] = thread
        st.session_state["dt_plan_start"] = time.perf_counter()
        thread.start()
        st.rerun()

    # Single container for all phase-specific content — Streamlit replaces it
    # atomically on phase transitions, preventing old iframe components from
    # lingering in the DOM while new content loads.
    _dt_area = st.empty()

    # ── Planning poll ─────────────────────────────────────────────────────────

    if dt_phase == "planning":
        with _dt_area.container():
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
            _logger.debug("dt_poll thread done — status=%s error=%s", rh.get("status"), rh.get("error"))
            if rh.get("status") == "interrupted":
                _, dt_graph = _load_day_trip_resources()
                config = {"configurable": {"thread_id": st.session_state["dt_thread_id"]}}
                snapshot = dt_graph.get_state(config)
                _logger.debug("dt_poll snapshot.next=%s", snapshot.next)
                _logger.debug("dt_poll snapshot.values keys=%s", list(snapshot.values.keys()))
                _logger.debug("dt_poll draft_itinerary present=%s", snapshot.values.get("draft_itinerary") is not None)
                if snapshot.values.get("draft_itinerary"):
                    stops = snapshot.values["draft_itinerary"].get("stops") or []
                    _logger.debug("dt_poll stops count=%d", len(stops))
                draft = snapshot.values.get("draft_itinerary")
                if draft:
                    st.session_state["dt_draft"] = draft
                    st.session_state["dt_route_coords"] = snapshot.values.get("route_coords") or []
                    # Planning time
                    plan_start = st.session_state.pop("dt_plan_start", None)
                    st.session_state["dt_plan_elapsed"] = (
                        round(time.perf_counter() - plan_start) if plan_start else None
                    )
                    # Per-step timing breakdown from the progress dict
                    _prog = st.session_state.get("dt_progress", {})
                    _step_times: dict = dict(_prog.get("step_times") or {})
                    # Record the final active step's elapsed if it wasn't closed
                    _final_step = _prog.get("current")
                    _final_start = _prog.get("step_start")
                    if _final_step and _final_start and _final_step not in _step_times:
                        _step_times[_final_step] = time.perf_counter() - _final_start
                    st.session_state["dt_step_times"] = _step_times
                    # Tool call count from agent messages
                    from langchain_core.messages import ToolMessage as _ToolMessage
                    msgs = snapshot.values.get("messages") or []
                    st.session_state["dt_tool_call_count"] = sum(
                        1 for m in msgs if isinstance(m, _ToolMessage)
                    )
                    st.session_state["dt_phase"] = "draft_ready"
                else:
                    st.session_state["dt_phase"] = "idle"
                    _dt_area.empty()
                    st.error("Agent did not produce a draft. Try again.")
            else:
                st.session_state["dt_phase"] = "idle"
                st.session_state["dt_last_error"] = rh.get("error", "unknown")
                _dt_area.empty()
            st.rerun()

    # ── Draft ready / narrating — map + cards + approve/refine/poll ─────────────

    elif dt_phase in ("draft_ready", "narrating"):
        with _dt_area.container():
            draft = st.session_state.get("dt_draft") or {}
            stops = draft.get("stops") or []

            if stops:
                city_val = st.session_state.get("dt_city_val", dt_city)
                hours_val = st.session_state.get("dt_hours_val", dt_hours)
                st.markdown(
                    f"**Draft itinerary — {city_val} · {hours_val}h · {len(stops)} stops**"
                )
                _elapsed = st.session_state.get("dt_plan_elapsed")
                _tool_calls = st.session_state.get("dt_tool_call_count")
                if _elapsed is not None or _tool_calls is not None:
                    _mc1, _mc2, _mc3 = st.columns(3)
                    _mc1.metric("⏱ Planned in", f"{_elapsed}s" if _elapsed is not None else "—")
                    _mc2.metric("🔧 Tool calls", str(_tool_calls) if _tool_calls is not None else "—")
                    _mc3.metric("📍 Stops", str(len(stops)))
                    # Per-step timing breakdown
                    _step_times = st.session_state.get("dt_step_times") or {}
                    if _step_times:
                        _step_labels = {s[0]: s[1] for s in _DT_STEPS}
                        _ls_project = "routeiq-week4"
                        _ls_url = f"https://smith.langchain.com/projects/p?name={_ls_project}"
                        _breakdown_lines = " · ".join(
                            f"{_step_labels.get(k, k)}: **{v:.0f}s**"
                            for k, v in _step_times.items()
                        )
                        st.caption(
                            f"Step breakdown — {_breakdown_lines} · "
                            f"[View in LangSmith ↗]({_ls_url})"
                        )
                route_coords_draft = st.session_state.get("dt_route_coords") or []
                m_draft = _render_dt_map(stops, route_coords_draft, height=300)
                st_folium(m_draft, height=300, use_container_width=True, returned_objects=[])

                cards_html = (
                    '<div style="max-height:420px;overflow-y:auto;padding-right:6px;">'
                    + "".join(render_dt_card(s, i) for i, s in enumerate(stops, 1))
                    + "</div>"
                    + IMAGE_MODAL_HTML
                )
                st.components.v1.html(cards_html, height=430, scrolling=False)

            if dt_phase == "draft_ready":
                # Approve / Refine row
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
                    st.caption(
                        "💡 Try: &nbsp;"
                        "**Add Central Park** · "
                        "**Skip museums** · "
                        "**More nature spots** · "
                        "**Fewer stops** · "
                        "**Include the High Line** &nbsp;·&nbsp; "
                        "⚠️ To change start time, use the selector above and click **Plan My Day** again."
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
                        st.session_state.pop("dt_draft", None)
                        t = threading.Thread(
                            target=_run_dt_refine_thread,
                            args=(feedback_text.strip(), config, dt_graph, rh3), daemon=True
                        )
                        st.session_state["dt_thread"] = t
                        st.session_state["dt_plan_start"] = time.perf_counter()
                        t.start()
                        st.rerun()

            elif dt_phase == "narrating":
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

    elif dt_phase == "done":
        with _dt_area.container():
            draft = st.session_state.get("dt_draft") or {}
            stops = draft.get("stops") or []
            route_coords = st.session_state.get("dt_route_coords") or []
            city_val = st.session_state.get("dt_city_val", "")
            hours_val = st.session_state.get("dt_hours_val", "")

            if stops:
                st.markdown(f"**{city_val} · {hours_val}h · {len(stops)} stops**")
                map_col, cards_col = st.columns([3, 2])

                with map_col:
                    m_done = _render_dt_map(stops, route_coords, height=480)
                    st_folium(m_done, height=480, use_container_width=True, returned_objects=[])

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
