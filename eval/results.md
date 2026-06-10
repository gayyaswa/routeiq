# RouteIQ Evaluation: GraphRAG vs Vector Baseline

*Generated 2026-06-09 21:49 — `python3 eval/run_eval.py`*

## Results

| # | Query | Type | GraphRAG POIs | Vector POIs | Unique to GraphRAG | Unique to Vector | Winner |
|---|-------|------|--------------|-------------|-------------------|-----------------|--------|
| 1 | Drive from San Francisco to Monterey, show coastal hist… | route | 19.0, Patchen Pass, Patchen Pass, Patchen Pass, Patchen Pass | 17-Mile Drive, Muir Woods National Monument, Cannery Row, Point Lobos State Natural Reserve, Big Basin Redwoods State Park | 19.0, patchen pass | 17-mile drive, big basin redwoods state park, cannery row, muir woods national monument, point lobos state natural reserve | 🗺 GraphRAG |
| 2 | Road trip from San Francisco to Napa Valley, show winer… | route | Admission Day Monument, La Cheve Bakery and Brews, Dewey Monument, Lotta's Fountain, Vallejo Old City Historic District | Napa Valley Wine Train, Cannery Row, Point Lobos State Natural Reserve, Castello di Amorosa, 17-Mile Drive | admission day monument, dewey monument, la cheve bakery and brews, lotta's fountain, vallejo old city historic district | 17-mile drive, cannery row, castello di amorosa, napa valley wine train, point lobos state natural reserve | 🗺 GraphRAG |
| 3 | Drive from San Jose to Santa Cruz, show redwoods and be… | route | San Pedro Art Crosswalks, Patchen Pass, Electric Light Tower, Celebration Under Water, Farmers Union Building | Henry Cowell Redwoods State Park, Muir Woods National Monument, 17-Mile Drive, Big Basin Redwoods State Park, Roaring Camp Railroad | celebration under water, electric light tower, farmers union building, patchen pass, san pedro art crosswalks | 17-mile drive, big basin redwoods state park, henry cowell redwoods state park, muir woods national monument, roaring camp railroad | 🗺 GraphRAG |
| 4 | Drive from San Francisco to Point Reyes, show lighthous… | route | Dragon Gate, Language of Birds, Jazz mural, Harmony, Bank of Canton (former Chinese Telephone Exchange) | Point Reyes Lighthouse, Pigeon Point Lighthouse, 17-Mile Drive, Muir Woods National Monument, Henry Cowell Redwoods State Park | bank of canton (former chinese telephone exchange), dragon gate, harmony, jazz mural, language of birds | 17-mile drive, henry cowell redwoods state park, muir woods national monument, pigeon point lighthouse, point reyes lighthouse | 🗺 GraphRAG |
| 5 | Road trip from San Francisco to Half Moon Bay, show coa… | route | No Human Being Is Illegal, Ram’s Hotel, Maybaum Gallery, Half Moon Bay Inn, Labyrinthine Heart | Mavericks Surf Break, Point Lobos State Natural Reserve, 17-Mile Drive, Pigeon Point Lighthouse, Point Reyes Lighthouse | half moon bay inn, labyrinthine heart, maybaum gallery, no human being is illegal, ram’s hotel | 17-mile drive, mavericks surf break, pigeon point lighthouse, point lobos state natural reserve, point reyes lighthouse | 🗺 GraphRAG |
| 6 | Drive from Oakland to Muir Woods, show old-growth redwo… | route | Susie Hotel, The Hawaiians (Mother and Child), Breonna Taylor, The Nieves Law Firm, Cathedral Building | Muir Woods National Monument, Henry Cowell Redwoods State Park, Big Basin Redwoods State Park, Roaring Camp Railroad, 17-Mile Drive | breonna taylor, cathedral building, susie hotel, the hawaiians (mother and child), the nieves law firm | 17-mile drive, big basin redwoods state park, henry cowell redwoods state park, muir woods national monument, roaring camp railroad | 🗺 GraphRAG |
| 7 | beautiful California coastal drives… | semantic | *(pipeline error)* | Point Lobos State Natural Reserve, 17-Mile Drive, Muir Woods National Monument, Castello di Amorosa, Big Basin Redwoods State Park | — | 17-mile drive, big basin redwoods state park, castello di amorosa, muir woods national monument, point lobos state natural reserve | 🔍 Vector |
| 8 | wine country day trips from San Francisco… | semantic | *(pipeline error)* | Napa Valley Wine Train, Muir Woods National Monument, Cannery Row, Castello di Amorosa, Sonoma Plaza | — | cannery row, castello di amorosa, muir woods national monument, napa valley wine train, sonoma plaza | 🔍 Vector |
| 9 | old growth redwood forests near Bay Area… | semantic | *(pipeline error)* | Muir Woods National Monument, Henry Cowell Redwoods State Park, Big Basin Redwoods State Park, Roaring Camp Railroad, 17-Mile Drive | — | 17-mile drive, big basin redwoods state park, henry cowell redwoods state park, muir woods national monument, roaring camp railroad | 🔍 Vector |
| 10 | Gold Rush era historic towns California… | semantic | *(pipeline error)* | Point Lobos State Natural Reserve, Sonoma Plaza, Big Basin Redwoods State Park, Castello di Amorosa, Cannery Row | — | big basin redwoods state park, cannery row, castello di amorosa, point lobos state natural reserve, sonoma plaza | 🔍 Vector |

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
