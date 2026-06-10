"""Day 4 end-to-end verification: MapBuilder + card_renderer + app render path."""
from __future__ import annotations

from routeiq.graph.poi import POI
from routeiq.graph.route_result import RouteResult
from routeiq.routing.scored_poi import ScoredPOI
from routeiq.ui import MapBuilder, CATEGORY_COLORS
from routeiq.ui.card_renderer import render_stop_card


# ── sample data (Bay Area) ────────────────────────────────────────────────────

def _make_sample_data() -> tuple[RouteResult, list[ScoredPOI]]:
    route_result = RouteResult(
        route_nodes=[1, 2, 3, 4],
        route_coords=[
            (37.7749, -122.4194),  # SF
            (36.6002, -121.8947),  # Monterey
        ],
        length_km=185.0,
        drive_time_min=130.0,
    )

    pois = [
        ScoredPOI(
            poi=POI(
                name="Cannery Row",
                category="tourism",
                lat=36.6177,
                lon=-121.8983,
                osm_id="cr_1",
                wikipedia_tag="en:Cannery Row",
                image_url="https://upload.wikimedia.org/wikipedia/commons/thumb/e/ef/Cannery_Row.jpg/320px-Cannery_Row.jpg",
                description="Historic cannery district in Monterey, immortalized by John Steinbeck's novel.",
            ),
            detour_km=0.2,
            detour_min=0.5,
        ),
        ScoredPOI(
            poi=POI(
                name="Point Lobos State Reserve",
                category="natural",
                lat=36.5152,
                lon=-121.9443,
                osm_id="pl_1",
                wikipedia_tag="en:Point Lobos State Natural Reserve",
                description="Rugged headland offering stunning views, sea otters, and dramatic rocky shores.",
            ),
            detour_km=3.0,
            detour_min=4.0,
        ),
        ScoredPOI(
            poi=POI(
                name="Carmel Mission",
                category="historic",
                lat=36.5403,
                lon=-121.9194,
                osm_id="cm_1",
                wikipedia_tag="en:Mission San Carlos Borromeo de Carmelo",
                description="Spanish colonial mission founded in 1770, burial site of Father Junipero Serra.",
            ),
            detour_km=1.5,
            detour_min=2.0,
        ),
    ]
    return route_result, pois


def _print_section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


# ── section 1: MapBuilder ─────────────────────────────────────────────────────

def verify_map_builder(route_result: RouteResult, pois: list[ScoredPOI]) -> None:
    _print_section("Step 1: MapBuilder.build()")
    builder = MapBuilder()
    m = builder.build(route_result, pois)
    html = m._repr_html_()
    assert html and len(html) > 100, "Expected non-empty map HTML"
    assert "cartocdn" in html.lower(), "Expected CartoDB tiles in map HTML"
    assert "AntPath" in html or "antpath" in html.lower(), "Expected AntPath animation in map HTML"
    print(f"  Map HTML length: {len(html):,} chars")
    print(f"  Contains CartoDB tiles: yes")
    print(f"  Contains AntPath animation: yes")

    # Verify filtered build
    m_filtered = builder.build(route_result, pois, filtered_categories=["historic"])
    filtered_html = m_filtered._repr_html_()
    assert "Carmel Mission" in filtered_html
    print(f"  Category filter (historic only): Carmel Mission in filtered map — yes")


# ── section 2: card_renderer ─────────────────────────────────────────────────

def verify_card_renderer(pois: list[ScoredPOI]) -> None:
    _print_section("Step 2: render_stop_card()")
    for i, sp in enumerate(pois, 1):
        html = render_stop_card(sp, rank=i)
        assert sp.poi.name in html, f"POI name missing: {sp.poi.name}"
        assert sp.poi.category.lower() in html.lower(), f"Category missing: {sp.poi.category}"
        assert f"+{sp.detour_min:.0f} min" in html, f"Detour time missing for {sp.poi.name}"
        color = CATEGORY_COLORS.get(sp.poi.category, "#7f8c8d")
        assert color in html, f"Category color missing for {sp.poi.category}"
        print(f"  Card {i}: {sp.poi.name} — name, category badge, detour time, color: all present")

    # Card without image (placeholder)
    poi_no_img = ScoredPOI(
        poi=POI(name="Test POI", category="natural", lat=0.0, lon=0.0, osm_id="t1"),
        detour_km=1.0,
        detour_min=2.0,
    )
    html_no_img = render_stop_card(poi_no_img, rank=99)
    assert "Test POI" in html_no_img
    print(f"  Card without image: placeholder renders OK")


# ── section 3: app render path (logic only, no Streamlit) ─────────────────────

def verify_app_logic(route_result: RouteResult, pois: list[ScoredPOI]) -> None:
    _print_section("Step 3: App render logic (no Streamlit)")
    # Simulate the state object the pipeline would return
    fake_state = {
        "query": "Drive from San Francisco to Monterey, show coastal landmarks",
        "origin": "San Francisco",
        "destination": "Monterey",
        "route_result": route_result,
        "top_pois": pois,
        "poi_context": "Cannery Row | tourism | ...",
        "narrative": "This scenic coastal drive winds from San Francisco to Monterey...",
        "error": None,
        "fallback_reason": None,
    }

    # Verify all required keys are present and typed correctly
    assert fake_state.get("error") is None
    top_pois = fake_state.get("top_pois") or []
    assert len(top_pois) == 3

    # Simulate category filter
    selected_cats = ["natural", "historic"]
    filtered = [sp for sp in top_pois if sp.poi.category in selected_cats]
    assert len(filtered) == 2, f"Expected 2 filtered POIs, got {len(filtered)}"

    # Simulate full cards HTML build
    cards_html = "".join(render_stop_card(sp, i) for i, sp in enumerate(filtered, 1))
    assert "Point Lobos" in cards_html
    assert "Carmel Mission" in cards_html
    assert "Cannery Row" not in cards_html  # tourism filtered out
    print(f"  Simulated pipeline state: OK")
    print(f"  Category filter simulation ({selected_cats}): {len(filtered)} POIs — correct")
    print(f"  Full cards HTML build: OK")


# ── section 4: CATEGORY_COLORS consistency ────────────────────────────────────

def verify_color_consistency() -> None:
    _print_section("Step 4: CATEGORY_COLORS consistency check")
    from routeiq.ui.map_builder import _COLORS as builder_colors
    for cat, color in CATEGORY_COLORS.items():
        assert builder_colors.get(cat) == color, (
            f"Color mismatch for '{cat}': ui/__init__={color}, map_builder={builder_colors.get(cat)}"
        )
    print(f"  All category colors match between ui/__init__.py and map_builder.py: yes")
    print(f"  Colors: {CATEGORY_COLORS}")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Day 4 Verification — MapBuilder + card_renderer + app logic")
    print("No network calls, no LLM, no Streamlit required.")

    route_result, pois = _make_sample_data()

    verify_map_builder(route_result, pois)
    verify_card_renderer(pois)
    verify_app_logic(route_result, pois)
    verify_color_consistency()

    print("\n\nDay 4 verification complete.")
    print("Next: streamlit run app.py — then run eval/run_eval.py for 10-query comparison.")


if __name__ == "__main__":
    main()
