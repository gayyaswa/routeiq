from __future__ import annotations
from abc import ABC, abstractmethod

from routeiq.activities.base import ClassifiedPOI

_DESCRIPTION_ADJECTIVES = {
    "scenic", "coastal", "challenging", "easy", "hidden", "quiet", "family",
    "kid", "historic", "waterfront", "mountain", "forest", "urban",
}


class ActivityRanker(ABC):
    """Ranks ClassifiedPOI candidates for a single activity slot (Strategy pattern)."""

    @abstractmethod
    def rank(
        self,
        candidates: list[ClassifiedPOI],
        activity: str,
        user_context: str,
        ratings: dict[str, float],
    ) -> list[ClassifiedPOI]:
        """Return candidates sorted best-first. Sets activity_rank_score on each."""
        ...


class RatingRanker(ActivityRanker):
    """Ranks by available rating descending; unrated POIs go last."""

    def rank(self, candidates, activity, user_context, ratings):
        def score(c):
            r = ratings.get(c.poi.osm_id, 0.0) or 0.0
            c.activity_rank_score = r / 5.0
            return r
        return sorted(candidates, key=score, reverse=True)


class SemanticRanker(ActivityRanker):
    """Ranks by cosine similarity between user_context and activity_evidence text."""

    def rank(self, candidates, activity, user_context, ratings):
        import chromadb
        from uuid import uuid4
        if not candidates:
            return candidates

        client = chromadb.EphemeralClient()
        col = client.create_collection(f"rank_{uuid4().hex}")

        docs = [c.activity_evidence or c.poi.name for c in candidates]
        ids = [str(i) for i in range(len(candidates))]
        col.add(documents=docs, ids=ids)

        results = col.query(query_texts=[f"{activity} {user_context}"], n_results=len(candidates))
        distances = results["distances"][0]
        order = results["ids"][0]

        max_d = max(distances) + 1e-6
        id_to_score = {ids[int(oid)]: 1.0 - (distances[i] / max_d) for i, oid in enumerate(order)}

        for c in candidates:
            idx = ids[candidates.index(c)]
            base = id_to_score.get(idx, 0.0)
            rating_bonus = (ratings.get(c.poi.osm_id, 0.0) or 0.0) / 5.0 * 0.4
            c.activity_rank_score = round(base * 0.6 + rating_bonus, 4)

        return sorted(candidates, key=lambda c: c.activity_rank_score, reverse=True)


class LLMRanker(ActivityRanker):
    """Asks the LLM to rank candidates given full user context."""

    def __init__(self, llm):
        self._llm = llm

    def rank(self, candidates, activity, user_context, ratings):
        import json
        from langchain_core.messages import HumanMessage
        if not candidates:
            return candidates

        lines = "\n".join(
            f"{i}. {c.poi.name}: {c.activity_evidence or 'no evidence'}"
            for i, c in enumerate(candidates)
        )
        prompt = (
            f"User wants: '{user_context}' (activity: {activity})\n\n"
            f"Rank these candidates best to worst:\n{lines}\n\n"
            f"Return JSON array of indices in ranked order, e.g. [2, 0, 1]"
        )
        try:
            resp = self._llm.invoke([HumanMessage(content=prompt)])
            raw = resp.content.strip().strip("```json").strip("```").strip()
            order = json.loads(raw)
            ranked = [candidates[i] for i in order if 0 <= i < len(candidates)]
            for score, c in enumerate(reversed(ranked)):
                c.activity_rank_score = round(score / len(ranked), 4)
            return ranked
        except Exception:
            return candidates


def create_ranker(user_context: str, ratings_available: bool = False, llm=None) -> ActivityRanker:
    words = set(user_context.lower().split())
    if words & _DESCRIPTION_ADJECTIVES:
        return SemanticRanker()
    if ratings_available:
        return RatingRanker()
    if llm:
        return LLMRanker(llm)
    return RatingRanker()
