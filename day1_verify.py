"""Day 1 end-to-end verification: OSMnx download → A* route → POI spatial join → Folium map."""
import sys
from collections import Counter

import folium

from routeiq.graph import GraphLoader, POIFinder, RouteGraph

NORTH, SOUTH, EAST, WEST = 30.35, 29.32, -97.60, -98.60

# Austin City Hall → San Antonio City Hall (approx)
ORIGIN_LAT, ORIGIN_LON = 30.267, -97.743
DEST_LAT, DEST_LON = 29.424, -98.495

CATEGORY_COLORS = {
    "historic": "red",
    "natural": "green",
    "tourism": "orange",
}


def main():
    print("Step 1: Loading road network (first run ~2-5 min, cached after)...")
    loader = GraphLoader()
    G = loader.load(north=NORTH, south=SOUTH, east=EAST, west=WEST)
    print(f"  Graph loaded: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")

    print("Step 2: Finding A* route Austin → San Antonio...")
    rg = RouteGraph(G)
    result = rg.find_route(ORIGIN_LAT, ORIGIN_LON, DEST_LAT, DEST_LON)
    print(f"  Route: {result.length_km:.1f} km, {result.drive_time_min:.0f} min")
    print(f"  Nodes in path: {len(result.route_nodes)}")

    print("Step 3: Finding POIs within 5 km buffer...")
    finder = POIFinder(buffer_km=5.0)
    pois = finder.find_pois(result.route_coords)
    counts = Counter(p.category for p in pois)
    print(f"  POIs found: {len(pois)} total")
    for cat, n in sorted(counts.items()):
        print(f"    {cat}: {n}")

    print("Step 4: Building Folium map...")
    center_lat = (ORIGIN_LAT + DEST_LAT) / 2
    center_lon = (ORIGIN_LON + DEST_LON) / 2
    m = folium.Map(location=[center_lat, center_lon], zoom_start=9)

    folium.PolyLine(result.route_coords, color="blue", weight=3, opacity=0.8).add_to(m)

    folium.CircleMarker(
        location=[ORIGIN_LAT, ORIGIN_LON],
        radius=10,
        color="blue",
        fill=True,
        fill_opacity=0.9,
        popup="Austin (origin)",
    ).add_to(m)

    folium.CircleMarker(
        location=[DEST_LAT, DEST_LON],
        radius=10,
        color="blue",
        fill=True,
        fill_opacity=0.9,
        popup="San Antonio (destination)",
    ).add_to(m)

    for poi in pois:
        color = CATEGORY_COLORS.get(poi.category, "gray")
        folium.CircleMarker(
            location=[poi.lat, poi.lon],
            radius=8,
            color=color,
            fill=True,
            fill_opacity=0.7,
            popup=f"{poi.name} ({poi.category})",
        ).add_to(m)

    m.save("day1_map.html")
    print("  Saved: day1_map.html")
    print("\nDay 1 verification complete.")
    print("Open day1_map.html to inspect route + POI markers.")
    print("Legend: red=historic  green=natural  orange=tourism")


if __name__ == "__main__":
    main()
