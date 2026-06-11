# Plan: Pre-cached POI + Road Network Strategy

**Status:** Implementing (Session 13)  
**Motivation:** Overpass API is slow (~11–21s) and unreliable during demo. Per-route cache
helps repeat queries but the first hit per route always requires a live call.

---

## POI Master File Strategy (Implementing now)

### Idea
Pre-fetch ALL qualifying Bay Area POIs once → store as `cache/pois/bay_area_all.json.gz` →
commit to repo → `POIFinder.find_pois()` does in-memory spatial filter, never calls Overpass.

### Size estimate
- Individual corridor queries return 153–466 POIs for 0.3°×0.3° to 1°×0.3° areas
- Full Bay Area (4 tiles, ~2°×1.6°): estimated 2,000–5,000 unique POIs after dedup
- Raw JSON: ~600KB–1.5MB → gzip: **~150–350KB** (safe to commit)

### 4 Bay Area tiles
| Tile | Coverage | Bbox (W, S, E, N) |
|---|---|---|
| North Bay / Napa / Marin | Napa, Sonoma, Marin | -123.1, 37.85, -122.1, 38.75 |
| SF / Marin Headlands / Coast | SF, Marin Headlands, Pacifica | -122.75, 37.65, -122.1, 38.0 |
| East Bay / Tri-Valley | Oakland, Berkeley, Livermore | -122.4, 37.35, -121.55, 37.85 |
| South Bay / Santa Cruz / Peninsula | San Jose, Santa Cruz, Palo Alto | -122.55, 36.85, -121.55, 37.55 |

### POIFinder lookup order (after this change)
1. `cache/pois/bay_area_all.json.gz` exists → load all POIs → filter by `buffer_poly` in-memory → return
2. Per-route `pois_n{maxy}...json` exists → load → return (legacy, kept as fallback)
3. Neither → Overpass query + write per-route cache (non-Bay-Area routes, or master missing)

### Tag filters (must stay in sync with POIFinder)
- `tourism`: viewpoint, museum, attraction, aquarium, zoo, theme_park, lighthouse, monument, winery
- `historic`: castle, fort, monument, memorial, ruins, archaeological_site, lighthouse, manor, battlefield
- `natural`: peak, volcano, beach, cape, cliff, waterfall, hot_spring, cave_entrance, bay, glacier, wood

### Files changed
- `routeiq/graph/poi_finder.py` — master file check at top of `find_pois()`
- `scripts/seed_poi_cache.py` — 4-tile fetch + gzip write
- `.gitignore` — `cache/pois/bay_area_all.json.gz` not ignored
- `cache/pois/bay_area_all.json.gz` — committed artifact

---

## OSM Road Network Strategy (TODO — Week 2)

### Problem
Graph `.pkl` files are 10–50 MB each — too large for plain git.

### Current behavior
`_preload_graphs()` runs at server start in a daemon thread; fetches each demo corridor
from Overpass and caches as `.pkl`. First cold start takes 2–5 min; subsequent restarts
are instant (pkl hit). Graph files are gitignored.

### Options evaluated
| Option | Tradeoff |
|---|---|
| Git LFS | Works but requires LFS quota; reviewers need `git lfs pull` |
| Cloud bucket (S3/GCS) | Clean, but adds infra dependency |
| `scripts/seed_graphs.py` + README doc | Zero infra; user pre-generates locally before demo |
| Current: auto-fetch at startup | Already works — pkl cached after first run |

### Decision
**Defer to Week 2.** Current auto-fetch at startup is acceptable for demo (graphs cached
after first run). Add a `# TODO` comment in `_preload_graphs()` and document in README
that graph files must be pre-generated locally (`scripts/seed_graphs.py` — not yet written).

---

## Related files
- `routeiq/graph/poi_finder.py` — POI fetching and caching
- `routeiq/graph/poi.py` — POI dataclass
- `scripts/seed_poi_cache.py` — offline seeder (run once before demo)
- `app.py` → `_DEMO_BBOXES` — graph pre-warm bboxes
- `docs/plan-day1.md` — original Day 1 architecture
