# RouteIQ Tool Routing Eval

*Generated 2026-06-24 23:39*

**Rule:** activities non-empty → `select_pois_for_day`; activities empty → `find_city_pois`

**Pass rate:** 8/8

| ID | City | Activities | Expected Tool | Actual Tool | Routing | Stops | Time |
|----|------|------------|---------------|-------------|---------|-------|------|
| r1 | San Francisco, CA | hiking | `select_pois_for_day` | `select_pois_for_day` | PASS | 9 | 35.8s |
| r2 | San Francisco, CA | hiking, kids | `select_pois_for_day` | `select_pois_for_day` | PASS | 7 | 61.5s |
| r3 | Oakland, CA | biking | `select_pois_for_day` | `select_pois_for_day` | PASS | 6 | 161.1s |
| r4 | San Jose, CA | kids | `select_pois_for_day` | `select_pois_for_day` | PASS | 4 | 84.4s |
| r5 | San Francisco, CA | — | `find_city_pois` | `find_city_pois` | PASS | 9 | 66.2s |
| r6 | Oakland, CA | — | `find_city_pois` | `find_city_pois` | PASS | 6 | 92.6s |
| r7 | Berkeley, CA | — | `find_city_pois` | `find_city_pois` | PASS | 5 | 262.2s |
| r8 | San Jose, CA | — | `find_city_pois` | `find_city_pois` | PASS | 4 | 152.9s |

