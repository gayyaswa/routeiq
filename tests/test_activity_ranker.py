"""Tests for ActivityRanker strategies and create_ranker factory."""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock

from routeiq.graph.poi import POI
from routeiq.activities.base import ClassifiedPOI
from routeiq.activities.ranker import (
    RatingRanker, SemanticRanker, LLMRanker, create_ranker,
)


def _cpoi(name, osm_id, subtype="peak", evidence=None, activities=None):
    poi = POI(name=name, category="natural", lat=0.0, lon=0.0, osm_id=osm_id, subtype=subtype)
    return ClassifiedPOI(
        poi=poi,
        matched_activities=activities or ["hiking"],
        activity_evidence=evidence,
    )


class TestRatingRanker:
    def test_sorted_by_rating_descending(self):
        candidates = [_cpoi("Low", "1"), _cpoi("High", "2"), _cpoi("Mid", "3")]
        ratings = {"1": 2.0, "2": 4.5, "3": 3.0}
        result = RatingRanker().rank(candidates, "hiking", "", ratings)
        assert [c.poi.osm_id for c in result] == ["2", "3", "1"]

    def test_unrated_goes_last(self):
        candidates = [_cpoi("Unrated", "1"), _cpoi("Rated", "2")]
        ratings = {"2": 3.0}
        result = RatingRanker().rank(candidates, "hiking", "", ratings)
        assert result[-1].poi.osm_id == "1"

    def test_score_normalised_to_0_to_1(self):
        candidates = [_cpoi("Spot", "1")]
        RatingRanker().rank(candidates, "hiking", "", {"1": 5.0})
        assert candidates[0].activity_rank_score == pytest.approx(1.0)

    def test_empty_candidates_returns_empty(self):
        assert RatingRanker().rank([], "hiking", "", {}) == []

    def test_zero_rating_handled(self):
        candidates = [_cpoi("Zero", "1")]
        RatingRanker().rank(candidates, "hiking", "", {"1": 0.0})
        assert candidates[0].activity_rank_score == 0.0


class TestSemanticRanker:
    def test_coastal_evidence_ranks_above_inland(self):
        candidates = [
            _cpoi("Inland Peak", "1", evidence="A dry mountain far inland"),
            _cpoi("Coastal Cliff", "2", evidence="A scenic coastal cliff trail by the sea"),
        ]
        result = SemanticRanker().rank(candidates, "hiking", "coastal scenic hiking", {})
        assert result[0].poi.osm_id == "2"

    def test_scores_set_on_all_candidates(self):
        candidates = [
            _cpoi("A", "1", evidence="forest trail hiking"),
            _cpoi("B", "2", evidence="mountain climb adventure"),
        ]
        SemanticRanker().rank(candidates, "hiking", "scenic", {})
        for c in candidates:
            assert c.activity_rank_score >= 0.0

    def test_empty_candidates_returns_empty(self):
        assert SemanticRanker().rank([], "hiking", "scenic", {}) == []

    def test_single_candidate_ranked(self):
        candidates = [_cpoi("Only", "1", evidence="forest walk")]
        result = SemanticRanker().rank(candidates, "hiking", "forest", {})
        assert len(result) == 1

    def test_rating_bonus_blended_into_score(self):
        candidates = [
            _cpoi("A", "1", evidence="coastal beach walk"),
            _cpoi("B", "2", evidence="coastal beach walk"),
        ]
        ratings = {"1": 0.0, "2": 5.0}
        result = SemanticRanker().rank(candidates, "hiking", "coastal", ratings)
        # Same text evidence — B should rank higher due to rating bonus
        assert result[0].poi.osm_id == "2"


class TestLLMRanker:
    def test_rank_by_llm_order(self):
        candidates = [_cpoi("A", "1"), _cpoi("B", "2"), _cpoi("C", "3")]
        llm = MagicMock()
        llm.invoke.return_value = MagicMock(content="[2, 0, 1]")
        result = LLMRanker(llm).rank(candidates, "hiking", "adventurous", {})
        assert result[0].poi.osm_id == "3"
        assert result[1].poi.osm_id == "1"
        assert result[2].poi.osm_id == "2"

    def test_fallback_on_json_parse_error(self):
        candidates = [_cpoi("A", "1"), _cpoi("B", "2")]
        llm = MagicMock()
        llm.invoke.return_value = MagicMock(content="not json at all")
        result = LLMRanker(llm).rank(candidates, "hiking", "", {})
        # Fallback: original order preserved
        assert len(result) == 2
        assert result[0].poi.osm_id == "1"

    def test_fallback_on_llm_exception(self):
        candidates = [_cpoi("A", "1")]
        llm = MagicMock()
        llm.invoke.side_effect = RuntimeError("API down")
        result = LLMRanker(llm).rank(candidates, "hiking", "", {})
        assert result == candidates

    def test_empty_candidates_returns_empty(self):
        llm = MagicMock()
        assert LLMRanker(llm).rank([], "hiking", "", {}) == []


class TestCreateRanker:
    def test_returns_semantic_for_adjective_words(self):
        assert isinstance(create_ranker("scenic coastal hiking"), SemanticRanker)

    def test_returns_semantic_for_hidden(self):
        assert isinstance(create_ranker("hidden gem mountain"), SemanticRanker)

    def test_returns_rating_when_ratings_available(self):
        assert isinstance(create_ranker("plain trip", ratings_available=True), RatingRanker)

    def test_returns_llm_when_provided_and_no_other_signal(self):
        llm = MagicMock()
        assert isinstance(create_ranker("a trip", ratings_available=False, llm=llm), LLMRanker)

    def test_default_is_rating_ranker(self):
        assert isinstance(create_ranker(""), RatingRanker)

    def test_adjective_takes_precedence_over_ratings(self):
        # SemanticRanker wins even when ratings_available=True if user_context has adjectives
        assert isinstance(create_ranker("quiet waterfront", ratings_available=True), SemanticRanker)
