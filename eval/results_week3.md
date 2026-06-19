# RouteIQ Week 3 Agent Eval — Day Trip Planner

*Generated 2026-06-18 23:21 — `python3 eval/run_agent_eval.py`*

## Section 1: Single-Pass Results

| # | City | Preferences | Stop Count | Pref Match % | Faithful % | Plan Time | Tool Calls | Pass/Fail |
|---|------|-------------|------------|--------------|------------|-----------|------------|-----------|
| 1 | San Francisco, CA | history, art | 5 | 100% | 100% | 37.2s | 11 | FAIL |
| 2 | San Francisco, CA | nature, outdoor, viewpoints | 7 | 100% | 14% | 31.2s | 3 | FAIL |
| 3 | Oakland, CA | food, art, waterfront | 5 | 67% | 100% | 14.7s | 6 | FAIL |
| 4 | Berkeley, CA | nature, food, culture | 4 | 67% | 0% | 17.7s | 15 | FAIL |
| 5 | San Jose, CA | parks, food | 6 | 50% | 0% | 14.9s | 1 | FAIL |
| 6 | San Francisco, CA | history, museums | 5 | 100% | 100% | 150.4s | 6 | FAIL |

## Section 2: Refinement Results (Query 6)

| Phase | Stops | Beach stops | Museum stops | Delta % |
|-------|-------|-------------|--------------|---------|
| Before | 5 | 1 | 4 | — |
| After  | 8 | 3 | 0 | 92% |

**Refinement verdict: YES**
- Beach preference gained: yes
- Museum preference reduced: yes

## Summary

**Queries run:** 6  
**Pass/Fail:** 0/6  
**Avg preference match:** 81%  
**Avg faithfulness:** 52%  
**Avg plan time:** 44.4s  
**Avg tool calls:** 7.0  
**Refinement delta:** 92%  
**Refinement verdict:** YES  
