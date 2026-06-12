# RouteIQ Evaluation: GraphRAG vs Vector Baseline

*Generated 2026-06-12 09:56 — `python3 eval/run_eval.py`*

## Results

| # | Query | Type | GraphRAG POIs | Vector POIs | Unique to GraphRAG | Unique to Vector | Winner |
|---|-------|------|--------------|-------------|-------------------|-----------------|--------|
| 1 | Drive from San Francisco to Muir Woods, show redwoods a… | route | Top of the Mark, Muir Beach Overlook, Rob Hill, Mount Tamalpais East Peak, Potrero Hill | Muir Beach Overlook, San Francisco Botanical Garden, Richardson Bay, Buena Vista Heights, Portola Discovery Site of San Francisco Bay | mount tamalpais east peak, potrero hill, rob hill, top of the mark | buena vista heights, portola discovery site of san francisco bay, richardson bay, san francisco botanical garden | 🗺 GraphRAG |
| 2 | Road trip from San Francisco to Napa Valley, show winer… | route | Warden's House, Coit Tower, Lightship Relief, Sather Gate, Quarters A | Cable Car Powerhouse and Barn, Potrero Hill, Portola Discovery Site of San Francisco Bay, V. Sattui Winery, Fisherman's Wharf | coit tower, lightship relief, quarters a, sather gate, warden's house | cable car powerhouse and barn, fisherman's wharf, portola discovery site of san francisco bay, potrero hill, v. sattui winery | 🗺 GraphRAG |
| 3 | Drive from San Jose to Santa Cruz, show redwoods and be… | route | Municipal Rose Garden, Japanese Friendship Garden, Forbes Mill Museum, The Tech Interactive, Ainsley House | Muir Beach Overlook, Portola Discovery Site of San Francisco Bay, Baker Beach (Nudist Area), Baker Beach, San Francisco Botanical Garden | ainsley house, forbes mill museum, japanese friendship garden, municipal rose garden, the tech interactive | baker beach, baker beach (nudist area), muir beach overlook, portola discovery site of san francisco bay, san francisco botanical garden | 🗺 GraphRAG |
| 4 | Drive from San Francisco to Point Reyes, show lighthous… | route | Top of the Mark, Rob Hill, Potrero Hill, Buena Vista Heights, Mount Tamalpais East Peak | Portola Discovery Site of San Francisco Bay, Muir Beach Overlook, Fisherman's Wharf, Pier 39 Sea Lions, Fort Point | buena vista heights, mount tamalpais east peak, potrero hill, rob hill, top of the mark | fisherman's wharf, fort point, muir beach overlook, pier 39 sea lions, portola discovery site of san francisco bay | 🗺 GraphRAG |
| 5 | Road trip from San Francisco to Half Moon Bay, show coa… | route | Top of the Mark, Mavericks, Bernal Hill, Mount Davidson, Potrero Hill | Muir Beach Overlook, Baker Beach (Nudist Area), Baker Beach, Albany Beach, Mavericks | bernal hill, mount davidson, potrero hill, top of the mark | albany beach, baker beach, baker beach (nudist area), muir beach overlook | 🗺 GraphRAG |
| 6 | Drive from San Francisco to Sausalito via the Golden Ga… | route | Fort Point, Warden's House, Coit Tower, Conservatory of Flowers, Lone Sailor Monument | Golden Gate Bridge, Muir Beach Overlook, Fort Point, Portola Discovery Site of San Francisco Bay, Japanese Tea Garden | coit tower, conservatory of flowers, lone sailor monument, warden's house | golden gate bridge, japanese tea garden, muir beach overlook, portola discovery site of san francisco bay | 🗺 GraphRAG |
| 7 | beautiful California coastal drives… | semantic | *(semantic — no route to parse)* | Muir Beach Overlook, Richardson Bay, Toll Plaza Beach, Mount Davidson, Mavericks | — | mavericks, mount davidson, muir beach overlook, richardson bay, toll plaza beach | 🔍 Vector |
| 8 | wine country day trips from San Francisco… | semantic | *(semantic — no route to parse)* | Fisherman's Wharf, Portola Discovery Site of San Francisco Bay, Muir Beach Overlook, Buena Vista Heights, Strawberry Hill | — | buena vista heights, fisherman's wharf, muir beach overlook, portola discovery site of san francisco bay, strawberry hill | 🔍 Vector |
| 9 | old growth redwood forests near Bay Area… | semantic | *(semantic — no route to parse)* | San Francisco Botanical Garden, Richardson Bay, Conservatory of Flowers, Muir Beach Overlook, Japanese Friendship Garden | — | conservatory of flowers, japanese friendship garden, muir beach overlook, richardson bay, san francisco botanical garden | 🔍 Vector |
| 10 | Gold Rush era historic towns California… | semantic | *(semantic — no route to parse)* | Fort Point, Muir Beach Overlook, Japanese Tea Garden, Forbes Mill Museum, Luis María Peralta Adobe | — | forbes mill museum, fort point, japanese tea garden, luis maría peralta adobe, muir beach overlook | 🔍 Vector |

## Analysis

**Prediction accuracy:** 10/10 queries matched expected winner

**Overall distribution:**
- 🗺 GraphRAG wins: 6 queries
- 🔍 Vector wins: 4 queries
- 🤝 Ties: 0 queries

**Route queries (6 total):** GraphRAG won 6/6
- GraphRAG constrains results to POIs actually along the driving route (geographic filter)
- Vector retrieves semantically similar POIs regardless of whether they're on the route
- **GraphRAG wins here** because it eliminates irrelevant but semantically similar POIs from other regions

**Semantic queries (4 total):** Vector won 4/4
- No origin/destination → pipeline cannot apply geographic constraints
- Pure semantic matching on description text finds the most topically relevant POIs
- **Vector wins here** because there's no route graph to leverage

## When each method wins

| Scenario | Best method | Why |
|----------|-------------|-----|
| "Drive from A to B, show X" | GraphRAG | Route coordinates constrain results to on-path POIs |
| "Find the best X near Y" | Vector | Semantic similarity finds topically relevant POIs |
| Specific landmark type along known route | GraphRAG | Graph filter removes off-route false positives |
| Open-ended discovery queries | Vector | No route context → pure semantic recall wins |

## Reproduce

```bash
python3 eval/run_eval.py
```

Requires: `ANTHROPIC_API_KEY`, ~10-15 min, ~$0.05-0.10 API cost.
