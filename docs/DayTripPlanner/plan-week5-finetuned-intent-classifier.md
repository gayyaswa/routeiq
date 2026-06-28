# Plan: Fine-Tuned Day Trip Intent Classifier (Week 5)

## Context

Every user query passes through the ReAct orchestrator before any tool is called.
At `iter=0` the LLM spends **3.70s** reading the query and deciding to call
`find_city_pois`. At `iter=1` it spends another **3.70s** parsing results and
deciding to call `rate_pois`. A pre-classification step that injects structured
intent into `DayTripState` before the loop starts gives the orchestrator a head
start — it no longer derives `activities` and `user_context` from scratch each turn.

This doubles as the Week 5 submission: fine-tune Qwen3-1.7B-Base (same LoRA
workflow as the IT ticket router) on day-trip query examples to produce a
lightweight, local intent classifier.

---

## What the Classifier Does

**Input:** raw user query — `"I want scenic view trails and maybe a picnic spot"`

**Output:** structured intent
```json
{
  "primary_activity": "Nature & Outdoors",
  "labels": ["Nature & Outdoors", "Scenic Drive"],
  "user_context": "scenic view trails picnic outdoor"
}
```

**7 labels (mirrors the IT ticket router structure):**

| Label | Example queries |
|---|---|
| Nature & Outdoors | "hike, swim, state parks, waterfalls" |
| History & Culture | "historic towns, museums, old missions" |
| Food & Wine | "wine tasting, farm-to-table, food markets" |
| Adventure | "kayaking, rock climbing, cycling routes" |
| Family Activities | "kid-friendly, zoos, splash pads, playgrounds" |
| Urban Exploration | "murals, coffee shops, breweries, street art" |
| Scenic Drive | "beautiful views, overlooks, coastal roads" |

---

## Architecture

```
User query
    → FineTunedIntentClassifier.classify_query(query)   ← NEW (local Qwen3-1.7B)
        → {primary_activity, labels, user_context}
    → injected into DayTripState.activities + DayTripState.user_context
    → ReAct loop starts with pre-populated intent
        → orchestrator LLM skips intent derivation → faster iter=0, iter=1
```

No schema change needed — `activities: List[str]` and `user_context: str` already
exist in `DayTripState` ([agent_state.py:19-20](../../../routeiq/agent/agent_state.py#L19-L20)).

---

## Files to Create / Modify

### New: `routeiq/activities/finetuned_classifier.py`
Implements the `ActivityClassifier` base class
([routeiq/activities/base.py:18-29](../../../routeiq/activities/base.py#L18-L29)).

```python
class FineTunedIntentClassifier(ActivityClassifier):
    """Classifies day-trip query intent using a LoRA-merged Qwen3-1.7B model (Strategy pattern)."""

    def __init__(self, model_path: str):
        from transformers import pipeline
        self._pipe = pipeline("text-generation", model=model_path, device_map="auto")

    def classify_query(self, query: str) -> IntentResult:
        prompt = f"Classify this day trip request into one category:\n\n{query}\n\nCategory:"
        out = self._pipe(prompt, max_new_tokens=10)[0]["generated_text"]
        label = _extract_label(out)
        return IntentResult(primary_activity=label, labels=[label],
                            user_context=query.lower())
```

### Modify: `routeiq/activities/factory.py`
Add `ACTIVITY_CLASSIFIER=finetuned` branch:
```python
if provider == "finetuned":
    from routeiq.activities.finetuned_classifier import FineTunedIntentClassifier
    return FineTunedIntentClassifier(os.getenv("FINETUNED_MODEL_PATH", "./models/intent"))
```

### Modify: Agent entry point (where initial DayTripState is built)
```python
intent = classifier.classify_query(user_query)
initial_state["activities"]    = intent.labels
initial_state["user_context"]  = intent.user_context
```

---

## Fine-Tuning Workflow (same as Week 5 IT ticket notebook)

### Step 1 — Generate training data
`scripts/generate_intent_training_data.py` — use Claude/GPT-4 to generate 700
labelled examples (100 per category) in ShareGPT format:
```json
{"conversations": [
  {"from": "human", "value": "I want to hike and find a waterfall near the city"},
  {"from": "gpt",   "value": "Nature & Outdoors"}
]}
```
Output: `data/intent_train.json` (80%) + `data/intent_val.json` (20% stratified hold-out).

### Step 2 — Register in LLaMA Factory
```json
"day_trip_intent": {"file_name": "intent_train.json", "formatting": "sharegpt"}
```

### Step 3 — Train via LLaMA Board (Google Colab, free T4)
- Base model: `Qwen/Qwen3-1.7B-Base`
- Dataset: `day_trip_intent`
- Method: LoRA, rank 8
- Epochs: 3, LR: 2e-4 (defaults)
- Expected: loss drops ~2.0 → ~0.3

### Step 4 — Merge + smoke test
5 obvious queries should route correctly before running full eval.

### Step 5 — Evaluate
Classification report (precision/recall/F1 per label) + confusion matrix.
Compare baseline Qwen3-1.7B-Base (zero-shot) vs fine-tuned.
Expect most confusion: "Nature & Outdoors" ↔ "Scenic Drive".

---

## Expected Impact

| Metric | Before | After |
|---|---|---|
| Intent classification | ~1-2s inside orchestrator LLM per turn | <100ms local inference |
| iter=0 LLM think | 3.70s | ~2-3s (intent pre-populated in state) |
| iter=1 LLM think | 3.70s | ~2-3s (activities field pre-set) |
| Estimated total saving | — | ~2-4s per query |

Not addressed: `rate_pois llm_synthetic=4.94s` — that is the synthetic ratings
generator, a separate LLM call. See [plan-poi-rating-cache.md](plan-poi-rating-cache.md).

---

## Verification

1. `python scripts/generate_intent_training_data.py` → 700 examples, 7 labels balanced
2. Train on Colab T4 → loss curve drops and levels off
3. Smoke test 5 queries → all route correctly
4. `pytest tests/ -v` → no regressions
5. Start app → confirm `DayTripState.activities` pre-populated before iter=0
6. Compare `logs/timing.log` before/after

---

## Week 5 Submission Assets

- `data/intent_train.json` + `data/intent_val.json`
- `scripts/generate_intent_training_data.py`
- `routeiq/activities/finetuned_classifier.py`
- Classification report screenshot
- Confusion matrix screenshot
- Baseline vs fine-tuned accuracy delta
- Colab notebook link
