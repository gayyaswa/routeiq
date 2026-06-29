"""Generate intent classifier training data via Claude Haiku API.

Produces ~1000 ShareGPT-format examples for fine-tuning Qwen3-1.7B on 9 activity tags.
Output: data/intent_train.json (800 examples) + data/intent_val.json (200 examples).

Usage:
    python3 scripts/generate_intent_training_data.py
    python3 scripts/generate_intent_training_data.py --dry-run   # 5 examples per tag only
    python3 scripts/generate_intent_training_data.py --out-dir ./data

Requirements:
    ANTHROPIC_API_KEY — Claude Haiku for generation
"""
from __future__ import annotations
import argparse
import json
import logging
import os
import random
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TAGS = ["hiking", "biking", "swimming", "kayaking", "kids", "picnic", "history", "food", "scenic"]

SYSTEM_PROMPT = (
    "You are a day trip intent classifier. "
    "Given a user query, output the activity tags that match their intent. "
    "Choose from: hiking, biking, swimming, kayaking, kids, picnic, history, food, scenic. "
    "Output matching tags as a comma-separated list, or 'none' if no activity is implied."
)

# Per-tag generation prompts — describe what kinds of queries to produce
_TAG_DESCRIPTIONS: dict[str, str] = {
    "hiking": (
        "trails, nature walks, peaks, waterfalls, bouldering, scenic hikes, forest paths, "
        "wilderness walks, national park visits. Include indirect phrasings like "
        "'somewhere with a waterfall', 'bouldering spot', 'want to see the redwoods'."
    ),
    "biking": (
        "cycling paths, bike routes, mountain biking, road cycling, cycling tours. "
        "Include indirect phrasings like 'ride along the coast', 'want to rent a bike', "
        "'something on two wheels'."
    ),
    "swimming": (
        "beaches for swimming, pools, snorkeling, diving, ocean swimming, lake swimming. "
        "Include indirect phrasings like 'want to cool off', 'splash around', "
        "'somewhere to get in the water'."
    ),
    "kayaking": (
        "kayaking, paddleboarding, canoeing, stand-up paddle boarding, water sports on calm water. "
        "Include indirect phrasings like 'paddle around the bay', 'something on a kayak', "
        "'rent a paddleboard'."
    ),
    "kids": (
        "playgrounds, zoos, theme parks (Disney, LEGOLAND, Six Flags, Universal), "
        "family attractions, children's museums, aquariums. Include indirect phrasings like "
        "'my 6-year-old would love it', 'little ones', 'something the whole family can enjoy', "
        "'rollercoasters', 'rides for kids'."
    ),
    "picnic": (
        "picnic areas, parks for relaxing, botanical gardens, meadows, scenic spots to sit and eat. "
        "Include indirect phrasings like 'somewhere to spread out a blanket', 'pack a lunch', "
        "'sit outside and enjoy the day'."
    ),
    "history": (
        "historic sites, missions, battlefields, museums, cultural landmarks, old town districts, "
        "heritage sites, ancient ruins. Include indirect phrasings like 'old town', "
        "'somewhere with history', 'learning about the area', 'explore the past'."
    ),
    "food": (
        "wineries, breweries, food markets, farm stands, tasting rooms, foodie destinations, "
        "restaurant districts, culinary tours, craft beer. Include indirect phrasings like "
        "'wine country tour', 'brewery district', 'somewhere with local food', "
        "'tasting experiences', 'farm to table'."
    ),
    "scenic": (
        "overlooks, viewpoints, coastal vistas, scenic drives, panoramic views, "
        "sunset spots, ocean views, mountain views. Include indirect phrasings like "
        "'somewhere with great views', 'best overlook', 'where can I watch the sunset', "
        "'great ocean views', 'scenic spot'."
    ),
}

_STYLE_VARIANTS = [
    "casual first-person",
    "formal request",
    "indirect/implied (no explicit activity word)",
    "question form",
    "short phrase (3–6 words)",
    "with a companion mentioned (partner, kids, dog, friends)",
    "regional/location-specific (mention a city or region)",
    "expressing a feeling or mood rather than an activity",
]


def _build_generation_prompt(tag: str, n: int, style_hint: str) -> str:
    return (
        f"Generate {n} diverse user queries for a day trip planner where the user wants to do "
        f"'{tag}' activities. Activity description: {_TAG_DESCRIPTIONS[tag]}\n\n"
        f"Style: {style_hint}\n\n"
        f"Rules:\n"
        f"- Each query should sound like something a real person would type\n"
        f"- Do NOT use the tag word '{tag}' directly in most queries\n"
        f"- Vary phrasing, length, and style\n"
        f"- Output one query per line, no numbering, no extra text\n"
        f"- Queries should be 5–20 words typically"
    )


def _build_multi_label_prompt(tags: list[str], n: int) -> str:
    tag_str = " + ".join(tags)
    descs = "; ".join(f"{t}: {_TAG_DESCRIPTIONS[t][:80]}" for t in tags)
    return (
        f"Generate {n} diverse user queries for a day trip planner where the user wants BOTH "
        f"'{tag_str}' activities in the same day.\n\n"
        f"Descriptions: {descs}\n\n"
        f"Rules:\n"
        f"- Both activities should be clearly implied (can be indirect)\n"
        f"- Sound natural and conversational\n"
        f"- Output one query per line, no numbering, no extra text"
    )


def _build_none_prompt(n: int) -> str:
    return (
        f"Generate {n} user queries for a day trip planner where the user has NO specific "
        f"activity in mind — just wants a general nice day out.\n\n"
        f"Examples of the vibe: 'show me a nice day in SF', 'plan a relaxing afternoon', "
        f"'just want to get out of the house', 'find me something fun to do'.\n\n"
        f"Rules:\n"
        f"- Must NOT imply any of: hiking, biking, swimming, kayaking, kids, picnic, history, food, scenic\n"
        f"- Sound natural\n"
        f"- Output one query per line, no numbering, no extra text"
    )


def _call_claude(client: anthropic.Anthropic, user_prompt: str) -> list[str]:
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw = response.content[0].text.strip()
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    return lines


def _make_example(query: str, label: str) -> dict:
    return {
        "conversations": [
            {"from": "system", "value": SYSTEM_PROMPT},
            {"from": "human",  "value": query},
            {"from": "gpt",    "value": label},
        ]
    }


def generate_single_label(
    client: anthropic.Anthropic,
    tag: str,
    n: int,
    dry_run: bool,
) -> list[dict]:
    """Generate n single-label examples for one tag."""
    target = min(n, 5) if dry_run else n
    examples: list[dict] = []
    batch_size = 10

    styles = random.sample(_STYLE_VARIANTS, min(len(_STYLE_VARIANTS), (target + batch_size - 1) // batch_size))
    for i, style in enumerate(styles):
        remaining = target - len(examples)
        if remaining <= 0:
            break
        count = min(batch_size, remaining)
        prompt = _build_generation_prompt(tag, count, style)
        try:
            queries = _call_claude(client, prompt)
            for q in queries[:count]:
                examples.append(_make_example(q, tag))
        except Exception as e:
            logger.warning("Claude call failed for tag=%s style=%s: %s", tag, style, e)

    logger.info("  %s: generated %d/%d examples", tag, len(examples), target)
    return examples


def generate_multi_label(
    client: anthropic.Anthropic,
    pairs: list[tuple[str, str]],
    n_per_pair: int,
    dry_run: bool,
) -> list[dict]:
    """Generate multi-label examples for tag pairs."""
    examples: list[dict] = []
    target_per_pair = min(n_per_pair, 3) if dry_run else n_per_pair

    for tag_a, tag_b in pairs:
        prompt = _build_multi_label_prompt([tag_a, tag_b], target_per_pair)
        try:
            queries = _call_claude(client, prompt)
            label = f"{tag_a}, {tag_b}"
            for q in queries[:target_per_pair]:
                examples.append(_make_example(q, label))
        except Exception as e:
            logger.warning("Claude call failed for pair=%s+%s: %s", tag_a, tag_b, e)

    logger.info("  multi-label: generated %d examples across %d pairs", len(examples), len(pairs))
    return examples


def generate_none_label(
    client: anthropic.Anthropic,
    n: int,
    dry_run: bool,
) -> list[dict]:
    """Generate 'none' examples — no activity implied."""
    target = min(n, 5) if dry_run else n
    examples: list[dict] = []
    prompt = _build_none_prompt(target)
    try:
        queries = _call_claude(client, prompt)
        for q in queries[:target]:
            examples.append(_make_example(q, "none"))
    except Exception as e:
        logger.warning("Claude call failed for none label: %s", e)

    logger.info("  none: generated %d/%d examples", len(examples), target)
    return examples


def split_and_save(examples: list[dict], out_dir: Path, val_ratio: float = 0.2) -> None:
    random.shuffle(examples)
    split_idx = int(len(examples) * (1 - val_ratio))
    train = examples[:split_idx]
    val = examples[split_idx:]

    out_dir.mkdir(parents=True, exist_ok=True)
    train_path = out_dir / "intent_train.json"
    val_path = out_dir / "intent_val.json"

    train_path.write_text(json.dumps(train, indent=2, ensure_ascii=False))
    val_path.write_text(json.dumps(val, indent=2, ensure_ascii=False))

    logger.info("Saved %d train → %s", len(train), train_path)
    logger.info("Saved %d val   → %s", len(val), val_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate intent classifier training data via Claude Haiku")
    parser.add_argument("--dry-run", action="store_true", help="Generate ~5 per tag only for testing")
    parser.add_argument("--out-dir", default="data", help="Output directory for train/val JSON files")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()

    random.seed(args.seed)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error(
            "ANTHROPIC_API_KEY not set. Add it to .env:\n"
            "  ANTHROPIC_API_KEY=sk-ant-..."
        )
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    out_dir = Path(args.out_dir)

    logger.info("Generating intent training data (dry_run=%s)...", args.dry_run)

    all_examples: list[dict] = []

    # Single-label: 100 per tag (9 tags = 900 examples target)
    single_label_n = 5 if args.dry_run else 100
    for tag in TAGS:
        logger.info("Generating single-label for tag: %s", tag)
        examples = generate_single_label(client, tag, single_label_n, args.dry_run)
        all_examples.extend(examples)

    # Multi-label pairs: representative combinations (~70 total = 10 pairs × 7 each)
    multi_pairs = [
        ("hiking", "kids"),
        ("hiking", "scenic"),
        ("food", "history"),
        ("swimming", "kids"),
        ("food", "hiking"),
        ("kayaking", "swimming"),
        ("scenic", "food"),
        ("history", "hiking"),
        ("kids", "picnic"),
        ("biking", "scenic"),
    ]
    multi_n = 2 if args.dry_run else 7
    logger.info("Generating multi-label examples for %d pairs...", len(multi_pairs))
    multi_examples = generate_multi_label(client, multi_pairs, multi_n, args.dry_run)
    all_examples.extend(multi_examples)

    # None label: 30 examples
    none_n = 5 if args.dry_run else 30
    logger.info("Generating 'none' examples...")
    none_examples = generate_none_label(client, none_n, args.dry_run)
    all_examples.extend(none_examples)

    logger.info("Total examples generated: %d", len(all_examples))

    if not all_examples:
        logger.error("No examples generated — check API key and Claude API access")
        sys.exit(1)

    split_and_save(all_examples, out_dir)
    logger.info("Done.")


if __name__ == "__main__":
    main()
