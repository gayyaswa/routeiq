from __future__ import annotations
import os
import pickle
import re
import osmnx as ox
import networkx as nx

# Matches both .pkl (fast) and .graphml (legacy) cache files
_BBOX_RE = re.compile(
    r"n(-?[\d.]+)_s(-?[\d.]+)_e(-?[\d.]+)_w(-?[\d.]+)\.(graphml|pkl)$"
)

_OVERPASS_MIRRORS = [
    "https://lz4.overpass-api.de/api",
    "https://z.overpass-api.de/api",
    "https://overpass.openstreetmap.ru/api",
    "https://overpass.kumi.systems/api",
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

        pkl_path = os.path.join(self._cache_dir, f"{key}.pkl")
        graphml_path = os.path.join(self._cache_dir, f"{key}.graphml")

        if os.path.exists(pkl_path):
            G = self._load_file(pkl_path)
            self._registry[key] = G
            return G

        # Migrate legacy graphml to pickle on first access (~5x faster parse next time)
        if os.path.exists(graphml_path):
            G = ox.load_graphml(graphml_path)
            self._save_pkl(G, pkl_path)
            self._registry[key] = G
            return G

        # Use a larger cached graph that fully contains this bbox — avoids a
        # network round-trip when preloaded demo corridors cover the request.
        containing = self._find_containing_cache(north, south, east, west)
        if containing:
            G = self._load_file(containing)
            self._registry[key] = G
            return G

        last_err: Exception | None = None
        for mirror in _OVERPASS_MIRRORS:
            try:
                ox.settings.overpass_url = mirror
                G = ox.graph_from_bbox(bbox=(west, south, east, north), network_type=network_type)
                self._save_pkl(G, pkl_path)
                self._registry[key] = G
                return G
            except Exception as e:
                last_err = e
        raise RuntimeError(f"All Overpass mirrors failed. Last error: {last_err}") from last_err

    def _load_file(self, path: str) -> nx.MultiDiGraph:
        if path.endswith(".pkl"):
            with open(path, "rb") as f:
                return pickle.load(f)
        return ox.load_graphml(path)

    def _save_pkl(self, G: nx.MultiDiGraph, path: str) -> None:
        with open(path, "wb") as f:
            pickle.dump(G, f, protocol=pickle.HIGHEST_PROTOCOL)

    def _find_containing_cache(
        self, north: float, south: float, east: float, west: float
    ) -> str | None:
        """Return path of a cached graph whose bbox fully contains the requested bbox. Prefers .pkl over .graphml."""
        best_pkl: str | None = None
        best_graphml: str | None = None
        for fname in os.listdir(self._cache_dir):
            m = _BBOX_RE.match(fname)
            if not m:
                continue
            cn, cs, ce, cw = (float(x) for x in m.groups()[:4])
            if cn >= north and cs <= south and ce >= east and cw <= west:
                path = os.path.join(self._cache_dir, fname)
                if fname.endswith(".pkl"):
                    best_pkl = path
                else:
                    best_graphml = path
        return best_pkl or best_graphml
