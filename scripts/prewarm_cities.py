"""One-off script: prewarm the unified poi_knowledge store for the 7 primary demo cities.

Run with:
    set -a && source .env && set +a && python3 scripts/prewarm_cities.py

Uses RATING_PROVIDER env var (currently tripadvisor). Overpass fetch only runs for
cities not already seeded in the static KG master (LA, NY, Seattle). Bay Area cities
(SF, San Jose, Berkeley, Santa Cruz) are pre-loaded — no Overpass call needed.

Idempotent: POIs already within the 21-day TTL are skipped by CityPrefetcher.
"""
from __future__ import annotations
import logging
import re
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TARGET_CITIES = [
    "San Francisco, CA",
    "San Jose, CA",
    "Berkeley, CA",
    "Santa Cruz, CA",
    "Los Angeles, CA",
    "New York, NY",
    "Seattle, WA",
]


def _normalize(city: str) -> str:
    """Fix camelCase city names (mirrors app.py's _normalize_city_name)."""
    parts = city.split(",", 1)
    fixed = re.sub(r"([a-z])([A-Z])", r"\1 \2", parts[0].strip())
    return f"{fixed},{parts[1]}" if len(parts) > 1 else fixed


def _expand_city(kg, city_norm: str) -> int:
    """Geocode city and fetch POIs from Overpass into the KG. Returns # POIs added."""
    import osmnx as ox
    from shapely.geometry import Point
    from routeiq.graph.poi_finder import POIFinder, OverpassUnavailableError

    try:
        gdf = ox.geocoder.geocode_to_gdf(city_norm)
    except Exception as exc:
        logger.error("geocode failed for %r: %s", city_norm, exc)
        return 0

    city_poly = gdf.geometry.iloc[0]
    lat = float(gdf.geometry.centroid.y.iloc[0])
    lon = float(gdf.geometry.centroid.x.iloc[0])
    pad = 0.15

    try:
        pois = POIFinder().find_pois_in_bbox(south=lat - pad, north=lat + pad, west=lon - pad, east=lon + pad)
    except OverpassUnavailableError:
        logger.error("Overpass unavailable for %r — skipping", city_norm)
        return 0

    pois = [p for p in pois if city_poly.contains(Point(p.lon, p.lat))]
    if not pois:
        logger.warning("0 POIs after polygon filter for %r", city_norm)
        return 0

    city_short = city_norm.split(",")[0].strip()
    kg.add_city_pois(city_short, lat, lon, pois)
    return len(pois)


def main() -> None:
    from routeiq.graph.knowledge_graph import get_kg
    from routeiq.rag.city_prefetcher import CityPrefetcher

    kg = get_kg()
    prefetcher = CityPrefetcher()
    seeded = kg.known_cities()
    total_new = 0

    for city in TARGET_CITIES:
        city_norm = _normalize(city)
        city_short = city_norm.split(",")[0].strip()
        t0 = time.perf_counter()

        # ── Step 1: ensure POIs are in the KG ──
        if city_short not in seeded:
            logger.info("%s: not in KG seed — fetching from Overpass…", city_short)
            n_pois = _expand_city(kg, city_norm)
            logger.info("%s: %d POIs added via Overpass (%.1fs)", city_short, n_pois, time.perf_counter() - t0)
        else:
            logger.info("%s: already in KG seed — skipping Overpass", city_short)

        # ── Step 2: get the POI list for this city ──
        pois = kg.get_pois_for_city(city_norm)
        if not pois:
            logger.warning("%s: 0 POIs in KG — skipping prefetch", city_short)
            continue
        logger.info("%s: %d POIs to enrich", city_short, len(pois))

        # ── Step 3: prefetch → Wikipedia + ratings + activity tags → poi_knowledge ──
        new_count = prefetcher.prefetch(city_norm, pois)
        elapsed = time.perf_counter() - t0
        logger.info("%s: prefetched %d new entries  (%.1fs total)", city_short, new_count, elapsed)
        total_new += new_count

    logger.info("Done. Total new poi_knowledge entries: %d", total_new)


if __name__ == "__main__":
    main()
