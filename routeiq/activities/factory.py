from __future__ import annotations
import os

from routeiq.activities.base import ActivityClassifier
from routeiq.activities.ranker import ActivityRanker, create_ranker as _create_ranker


def create_activity_classifier(llm=None) -> ActivityClassifier:
    provider = os.getenv("ACTIVITY_PROVIDER", "osm").lower()

    if provider == "tavily":
        from routeiq.activities.tavily_classifier import TavilyActivityClassifier
        _llm = llm or _get_llm()
        return TavilyActivityClassifier(api_key=os.getenv("TAVILY_API_KEY", ""), llm=_llm)

    if provider == "perplexity":
        from routeiq.activities.perplexity_classifier import PerplexityActivityClassifier
        _llm = llm or _get_llm()
        return PerplexityActivityClassifier(api_key=os.getenv("PERPLEXITY_API_KEY", ""), llm=_llm)

    from routeiq.activities.osm_classifier import OSMActivityClassifier
    return OSMActivityClassifier()


def create_ranker(user_context: str, ratings_available: bool = False, llm=None) -> ActivityRanker:
    return _create_ranker(user_context, ratings_available, llm)


def _get_llm():
    from routeiq.llm_factory import create_llm
    return create_llm()
