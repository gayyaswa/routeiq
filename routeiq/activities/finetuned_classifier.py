"""Fine-tuned intent classifier for day trip user queries (Strategy pattern)."""
from __future__ import annotations
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a day trip intent classifier. "
    "Given a user query, output the activity tags that match their intent. "
    "Choose from: hiking, biking, swimming, kayaking, kids, picnic, history, food, scenic. "
    "Output matching tags as a comma-separated list, or 'none' if no activity is implied."
)

_ALL_TAGS = frozenset(["hiking", "biking", "swimming", "kayaking", "kids", "picnic", "history", "food", "scenic"])

_DEFAULT_MODEL_PATH = os.getenv("FINETUNED_MODEL_PATH", "./models/intent")


class QueryIntentClassifier:
    """Classifies free-text day trip queries into activity tags using fine-tuned Qwen3-1.7B (Strategy pattern)."""

    def __init__(self, model_path: str = _DEFAULT_MODEL_PATH):
        self._model_path = model_path
        self._pipeline = None

    def _load(self) -> None:
        if self._pipeline is not None:
            return
        try:
            import torch
            from transformers import AutoTokenizer, pipeline
        except ImportError:
            raise RuntimeError("transformers and torch are required: pip install transformers torch")

        if torch.backends.mps.is_available():
            device = "mps"
        elif torch.cuda.is_available():
            device = "cuda"
        else:
            device = "cpu"

        logger.info("Loading fine-tuned intent classifier from %s on %s...", self._model_path, device)
        tokenizer = AutoTokenizer.from_pretrained(self._model_path)
        self._pipeline = pipeline(
            "text-generation",
            model=self._model_path,
            tokenizer=tokenizer,
            device=device,
            torch_dtype=torch.float32,
            max_new_tokens=32,
            do_sample=False,
        )
        logger.info("Intent classifier ready on %s", device)

    def classify(self, text: str) -> dict:
        """Classify a user query into activity tags.

        Returns:
            {
                "activities": ["hiking"],
                "semantic_queries": {"hiking": "<original text>"},
                "user_context": "<original text>"
            }
        """
        self._load()

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": text},
        ]

        try:
            output = self._pipeline(messages)
            raw = output[0]["generated_text"]
            # pipeline returns the full conversation list; last entry is the assistant turn
            if isinstance(raw, list):
                label_text = raw[-1].get("content", "").strip().lower()
            else:
                label_text = str(raw).strip().lower()
        except Exception as e:
            logger.warning("Inference failed for %r: %s — returning empty activities", text, e)
            label_text = "none"

        activities = _parse_tags(label_text)
        return {
            "activities": activities,
            "semantic_queries": {tag: text for tag in activities},
            "user_context": text,
        }


def _parse_tags(label_text: str) -> list[str]:
    if not label_text or label_text.strip() == "none":
        return []
    return [t.strip() for t in label_text.split(",") if t.strip() in _ALL_TAGS]


def create_query_intent_classifier(model_path: Optional[str] = None) -> QueryIntentClassifier:
    """Factory — returns a QueryIntentClassifier (lazy-loads model on first classify call)."""
    return QueryIntentClassifier(model_path=model_path or _DEFAULT_MODEL_PATH)
