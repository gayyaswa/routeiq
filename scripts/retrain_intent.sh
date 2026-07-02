#!/bin/bash
# Full retrain pipeline for day-trip intent classifier.
# Step 1: regenerate training data (requires ANTHROPIC_API_KEY)
# Step 2: LoRA fine-tune Qwen3-1.7B-Base via LLaMA Factory
# Step 3: merge adapter into full model weights
#
# Usage:
#   bash scripts/retrain_intent.sh           # full pipeline
#   SKIP_DATAGEN=1 bash scripts/retrain_intent.sh   # skip data gen, retrain on existing data

set -e
cd "$(dirname "$0")/.."

LOG_DIR="logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/retrain_intent_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

echo "=== RouteIQ intent classifier retrain ==="
echo "$(date): started"

# ── Step 1: generate training data ───────────────────────────────────────────
if [ "${SKIP_DATAGEN:-0}" != "1" ]; then
    if [ -z "$ANTHROPIC_API_KEY" ]; then
        echo "WARNING: ANTHROPIC_API_KEY not set — skipping data generation, using existing data/intent_train.json"
    else
        echo "$(date): generating training data..."
        python3 scripts/generate_intent_training_data.py
        echo "$(date): training data generated"
    fi
else
    echo "$(date): SKIP_DATAGEN=1 — using existing training data"
fi

# ── Step 2: LoRA fine-tune ────────────────────────────────────────────────────
echo "$(date): starting LoRA fine-tune (Qwen3-1.7B-Base, 3 epochs)..."
llamafactory-cli train scripts/train_intent_lora.yaml
echo "$(date): training complete — adapter saved to models/intent_adapter_v2/"

# ── Step 3: merge adapter → full model ───────────────────────────────────────
echo "$(date): merging adapter into models/intent/..."
llamafactory-cli export scripts/export_intent_lora.yaml
echo "$(date): export complete — models/intent/ updated"

echo ""
echo "=== Retrain done. Next steps ==="
echo "  1. Run: python3 eval/intent_eval_golden.py"
echo "  2. Confirm nightlife queries now map to 'food'"
echo "  3. Copy adapter: cp -r models/intent_adapter_v2 models/intent_adapter"
