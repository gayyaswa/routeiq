# Day 1 — Graph Foundation Implementation Plan

## Context

RouteIQ Day 1 goal: build the graph layer that loads an OSM road network, finds an A* shortest
path between two cities, spatially joins POIs along that route, and renders a Folium map to
verify visually. This is the retrieval backbone — the graph pre-filters spatially before the
RAG layer fetches rich descriptions.

## Files to Create

```
routeiq/graph/route_result.py   — RouteResult dataclass (pure data, no logic)
routeiq/graph/poi.py            — POI dataclass (pure data, no logic)
routeiq/graph/graph_loader.py   — GraphLoader (Registry pattern)
routeiq/graph/route_graph.py    — RouteGraph (Strategy pattern)
routeiq/graph/poi_finder.py     — POIFinder (Pipeline pattern)
routeiq/graph/__init__.py       — re-exports all five symbols
tests/test_graph_loader.py      — unit tests (mocked, no network calls)
tests/test_route_graph.py       — unit tests (synthetic graph, no OSMnx)
tests/test_poi_finder.py        — unit tests (mock GeoDataFrame, no network)
day1_verify.py                  — runnable verification script at project root
```

Also update `.gitignore` to add `cache/` and `day1_map.html`.

---

## Step 1 — Install dependencies

```bash
python3 -m pip install -r requirements.txt
```

osmnx, networkx, geopandas, shapely, folium are not yet installed.

---

## Step 2 — Dataclasses (no dependencies, pure Python)

**`route_result.py`:**
```python
from __future__ import annotations
from dataclasses import dataclass

@dataclass
class RouteResult:
    """Typed result from A* pathfinding over an OSM road network (dataclass)."""
    route_nodes: list[int]
    route_coords: list[tuple[float, float]]  # (lat, lon)
    length_km: float
    drive_time_min: float
```

**`poi.py`:**
```python
from __future__ import annotations
from dataclasses import dataclass

@dataclass
class POI:
    """A point of interest extracted from OSM features along a route (dataclass)."""
    name: str
    category: str           # "historic" | "tourism" | "natural"
    lat: float
    lon: float
    osm_id: str
    wikipedia_tag: str | None = None   # populated by RAG layer on Day 3
    image_url: str | None = None       # Wikipedia thumbnail, populated on Day 3
```

---

## Step 3 — GraphLoader (Registry pattern)

**Key design:** disk cache at `./cache/graphs/{key}.graphml` + in-memory `_registry` dict.
Cache key format: `"n30.350_s29.320_e-97.600_w-98.600"`.

**OSMnx version:** pinned to `osmnx>=2.0` in requirements.txt — always uses the 2.x API.
No version detection shim needed. bbox convention is `(west, south, east, north)` throughout.

```python
G = ox.graph_from_bbox(bbox=(west, south, east, north), network_type=network_type)
```

Same convention applies to `features_from_bbox` in POIFinder.

**Load sequence:** registry hit → disk hit (`ox.load_graphml`) → download + save.

**Constructor:** `__init__(self, cache_dir: str = "./cache/graphs")`
— `cache_dir` is injectable so tests can redirect to a temp directory.

---

## Step 4 — RouteGraph (Strategy pattern)

**Constructor:** `__init__(self, graph: nx.MultiDiGraph, avg_speed_kmh: float = 50.0)`
— graph is injected, never fetched internally.

**`find_route(origin_lat, origin_lon, dest_lat, dest_lon) → RouteResult`**

- Snap to nodes: `ox.distance.nearest_nodes(G, X=lon, Y=lat)` — note X=lon, Y=lat (common trap)
- A* path: `nx.astar_path(G, orig, dest, heuristic=self._haversine_heuristic, weight="length")`
- Path length: `nx.path_weight(G, route_nodes, weight="length")` — handles MultiDiGraph correctly
- Drive time: `(length_km / avg_speed_kmh) * 60`
- No-path: catch `nx.NetworkXNoPath` → raise `ValueError` with descriptive message

**Haversine heuristic:**
```python
def _haversine_heuristic(self, u: int, v: int) -> float:
    return ox.distance.great_circle(
        lat1=self._graph.nodes[u]["y"], lon1=self._graph.nodes[u]["x"],
        lat2=self._graph.nodes[v]["y"], lon2=self._graph.nodes[v]["x"],
    )
```

**Coord extraction:** `[(G.nodes[n]["y"], G.nodes[n]["x"]) for n in route_nodes]`

---

## Step 5 — POIFinder (Pipeline pattern)

**Constructor:** `__init__(self, buffer_km: float = 5.0)`

**`find_pois(route_coords) → list[POI]`** — pipeline:

1. Build Shapely buffer:
   ```python
   line = LineString([(lon, lat) for lat, lon in route_coords])  # Shapely uses (x=lon, y=lat)
   buffer_deg = self._buffer_km / 111.0
   buffer_poly = line.buffer(buffer_deg)
   ```

2. Fetch features via OSMnx (osmnx>=2.0 bbox convention: west, south, east, north):
   ```python
   tags = {"tourism": True, "historic": True, "natural": True}
   minx, miny, maxx, maxy = buffer_poly.bounds   # west, south, east, north
   gdf = ox.features_from_bbox(...)
   ```
   Wrap in `try/except` → return `[]` on any OSMnx error.

3. Centroid extraction for mixed geometry types:
   - `Point` → use coordinates directly
   - All others (`Polygon`, `MultiPolygon`, `LineString`) → `.centroid`

4. Per-row filtering:
   - Skip if `name` is NaN or missing
   - Skip if centroid not inside `buffer_poly`
   - Category priority: `historic` → `tourism` → `natural`
   - `wikipedia_tag`: set from `row.get("wikipedia")`, None if NaN

5. `osm_id = str(row.name)` — GeoDataFrame index is the OSM element ID in OSMnx

---

## Step 6 — `routeiq/graph/__init__.py`

```python
from routeiq.graph.route_result import RouteResult
from routeiq.graph.poi import POI
from routeiq.graph.graph_loader import GraphLoader
from routeiq.graph.route_graph import RouteGraph
from routeiq.graph.poi_finder import POIFinder

__all__ = ["RouteResult", "POI", "GraphLoader", "RouteGraph", "POIFinder"]
```

---

## Step 7 — Unit Tests (no network calls)

**`test_graph_loader.py`** — mock `ox.graph_from_bbox`, `ox.save_graphml`, `ox.load_graphml`, `os.path.exists`:
- cache miss: verifies download + save called
- disk hit: verifies `load_graphml` called, download NOT called
- in-memory hit: two calls same bbox → download called once only
- key format: exact string `"n30.350_s29.320_e-97.600_w-98.600"`
- different bboxes: two separate download calls

**`test_route_graph.py`** — 5-node synthetic `nx.MultiDiGraph` with `x`/`y` node attrs
and `length` edge attrs; mock `ox.distance.nearest_nodes`:
- returns `RouteResult` instance
- `route_nodes[0]` is origin, `[-1]` is destination
- `len(route_coords) == len(route_nodes)`
- `length_km > 0`
- `drive_time_min == (length_km / 50.0) * 60` within float tolerance
- disconnected node raises `ValueError`

**`test_poi_finder.py`** — mock `ox.features_from_bbox` with hand-crafted `gpd.GeoDataFrame`:
- POIs inside buffer are returned
- POIs outside buffer excluded
- NaN name rows skipped
- Polygon centroid included when inside buffer
- `wikipedia_tag` preserved
- empty route returns `[]`
- OSMnx exception returns `[]`

---

## Step 8 — `day1_verify.py`

Standalone script at project root. Runs the full Day 1 pipeline and saves `day1_map.html`:
- Step 1: `GraphLoader.load(north=30.35, south=29.32, east=-97.60, west=-98.60)`
- Step 2: `RouteGraph.find_route(30.267, -97.743, 29.424, -98.495)` (Austin → San Antonio)
- Step 3: `POIFinder(buffer_km=5.0).find_pois(result.route_coords)`
- Step 4: Folium map — blue polyline route + color-coded CircleMarker POIs
  (red=historic, green=natural, orange=tourism)
- Print summary: node/edge count, route km/min, POI count by category

---

## Verification

```bash
python3 -m pip install -r requirements.txt
python3 -m pytest tests/ -v          # all pass with mocks (fast, no network)
python3 day1_verify.py               # real OSMnx download (~2-5 min first run)
open day1_map.html                   # inspect route + POI markers visually
```

First `day1_verify.py` run downloads ~50k-node graph and caches to `./cache/graphs/`.
Subsequent runs load from disk in seconds.
