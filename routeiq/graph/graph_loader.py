from __future__ import annotations
import os
import re
import osmnx as ox
import networkx as nx

_BBOX_RE = re.compile(
    r"n(-?[\d.]+)_s(-?[\d.]+)_e(-?[\d.]+)_w(-?[\d.]+)\.graphml$"
)

_OVERPASS_MIRRORS = [
    "https://overpass.kumi.systems/api",
    "https://lz4.overpass-api.de/api",
    "https://z.overpass-api.de/api",
    "https://overpass.openstreetmap.ru/api",
]


class GraphLoader:
    """Loads and caches OSM road network graphs by bbox (Registry pattern)."""

    def __init__(self, cache_dir: str = "./cache/graphs"):
        self._cache_dir = cache_dir
        self._registry: dict[str, nx.MultiDiGraph] = {}
        os.makedirs(cache_dir, exist_ok=True)

    def load(
        self,
        north: float,
        south: float,
        east: float,
        west: float,
        network_type: str = "drive",
    ) -> nx.MultiDiGraph:
        key = f"n{north:.3f}_s{south:.3f}_e{east:.3f}_w{west:.3f}"

        if key in self._registry:
            return self._registry[key]

        path = os.path.join(self._cache_dir, f"{key}.graphml")
        if os.path.exists(path):
            G = ox.load_graphml(path)
            self._registry[key] = G
            return G

        # Use a larger cached graph that fully contains this bbox — avoids a
        # network round-trip when preloaded demo corridors cover the request.
        containing = self._find_containing_cache(north, south, east, west)
        if containing:
            G = ox.load_graphml(containing)
            self._registry[key] = G
            return G

        last_err: Exception | None = None
        for mirror in _OVERPASS_MIRRORS:
            try:
                ox.settings.overpass_url = mirror
                G = ox.graph_from_bbox(bbox=(west, south, east, north), network_type=network_type)
                ox.save_graphml(G, path)
                self._registry[key] = G
                return G
            except Exception as e:
                last_err = e
        raise RuntimeError(f"All Overpass mirrors failed. Last error: {last_err}") from last_err

    def _find_containing_cache(
        self, north: float, south: float, east: float, west: float
    ) -> str | None:
        """Return path of a cached graphml whose bbox fully contains the requested bbox."""
        for fname in os.listdir(self._cache_dir):
            m = _BBOX_RE.match(fname)
            if not m:
                continue
            cn, cs, ce, cw = (float(x) for x in m.groups())
            if cn >= north and cs <= south and ce >= east and cw <= west:
                return os.path.join(self._cache_dir, fname)
        return None
