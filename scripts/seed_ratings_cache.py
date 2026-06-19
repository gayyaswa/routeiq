#!/usr/bin/env python3
"""Pre-warm TripAdvisor and Foursquare rating caches for all Bay Area demo cities.

Run once before a demo or before giving the app to instructors so all API calls
are cached for 21 days and the Day Trip Planner never triggers live API calls.

Usage:
    python3 scripts/seed_ratings_cache.py

Requires TRIPADVISOR_API_KEY and/or FOURSQUARE_API_KEY set in .env.
Cities without a key for that provider are silently skipped.
"""
from __future__ import annotations
import os
import sys

# Resolve project root so the script runs from any directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from routeiq.graph.knowledge_graph import RouteKnowledgeGraph

DEMO_CITIES = [
    ("San Francisco, CA", 37.7749, -122.4194),
    ("Napa, CA",          38.2975, -122.2869),
    ("San Jose, CA",      37.3382, -121.8863),
    ("Half Moon Bay, CA", 37.4636, -122.4286),
    ("Sausalito, CA",     37.8591, -122.4853),
]


def _seed_city(city_name: str, lat: float, lon: float, providers: list) -> None:
    kg = RouteKnowledgeGraph()
    known_short = {c.split(",")[0].strip() for c in kg.known_cities()}
    city_short = city_name.split(",")[0].strip()

    pois = kg.get_pois_for_city(city_name)
    if not pois:
        print(f"  [{city_short}] No POIs in KG — skipping (run app first to seed KG)", flush=True)
        return

    for provider, name in providers:
        print(f"  [{city_short}] {name}: enriching {len(pois)} POIs…", flush=True)
        try:
            rated = provider.enrich_batch(city_name, pois)
            matched = sum(1 for r in rated if r.rating is not None)
            print(f"  [{city_short}] {name}: {matched}/{len(rated)} matched, cache written.", flush=True)
        except Exception as exc:
            print(f"  [{city_short}] {name}: ERROR — {exc}", flush=True)


def main() -> None:
    providers = []

    ta_key = os.getenv("TRIPADVISOR_API_KEY", "")
    if ta_key:
        from routeiq.ratings.tripadvisor import TripAdvisorRatingProvider
        providers.append((TripAdvisorRatingProvider(api_key=ta_key), "TripAdvisor"))
        print("TripAdvisor: key found.", flush=True)
    else:
        print("TripAdvisor: TRIPADVISOR_API_KEY not set — skipping.", flush=True)

    fs_key = os.getenv("FOURSQUARE_API_KEY", "")
    if fs_key:
        from routeiq.ratings.foursquare import FoursquareRatingProvider
        providers.append((FoursquareRatingProvider(api_key=fs_key), "Foursquare"))
        print("Foursquare: key found.", flush=True)
    else:
        print("Foursquare: FOURSQUARE_API_KEY not set — skipping.", flush=True)

    if not providers:
        print("No provider keys found. Set TRIPADVISOR_API_KEY or FOURSQUARE_API_KEY in .env.")
        return

    print(f"\nSeeding {len(DEMO_CITIES)} cities × {len(providers)} providers…\n", flush=True)
    for city_name, lat, lon in DEMO_CITIES:
        print(f"City: {city_name}", flush=True)
        _seed_city(city_name, lat, lon, providers)
        print("", flush=True)

    print("Done. Cache files written to cache/ratings/.", flush=True)


if __name__ == "__main__":
    main()
