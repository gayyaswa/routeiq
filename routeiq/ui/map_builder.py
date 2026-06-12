"""Builds a Folium map from route + POI data (Builder pattern)."""
from __future__ import annotations

import folium
import folium.plugins

from routeiq.graph.route_result import RouteResult
from routeiq.routing.scored_poi import ScoredPOI


# Matches CATEGORY_COLORS in __init__.py — keep in sync
_COLORS: dict[str, str] = {
    "historic": "#c0392b",
    "tourism": "#2980b9",
    "natural": "#27ae60",
}
_DEFAULT_COLOR = "#7f8c8d"


class MapBuilder:
    """Assembles a Folium map with an animated route polyline and color-coded POI markers (Builder pattern)."""

    def build(
        self,
        route_result: RouteResult,
        top_pois: list[ScoredPOI],
        *,
        filtered_categories: list[str] | None = None,
    ) -> folium.Map:
        """Return a Folium map centred on the route with AntPath animation and POI markers.

        filtered_categories: if provided, only render markers for those categories.
        """
        coords = route_result.route_coords  # list of (lat, lon)

        mid = len(coords) // 2
        center_lat, center_lon = coords[mid] if coords else (37.75, -122.42)

        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=10,
            tiles="CartoDB positron",
        )

        if coords:
            folium.plugins.AntPath(
                locations=coords,
                delay=800,
                weight=5,
                color="#0066cc",
                pulse_color="#ffffff",
                dash_array=[10, 20],
            ).add_to(m)

        visible_pois = top_pois
        if filtered_categories:
            visible_pois = [sp for sp in top_pois if sp.poi.category in filtered_categories]

        for sp in visible_pois:
            p = sp.poi
            color = _COLORS.get(p.category, _DEFAULT_COLOR)
            desc_snippet = (p.description or "")[:80]
            popup_html = f"<b>{p.name}</b><br/>{desc_snippet}"

            folium.CircleMarker(
                location=[p.lat, p.lon],
                radius=10,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.85,
                popup=folium.Popup(popup_html, max_width=220),
                tooltip=p.name,
            ).add_to(m)

        return m
