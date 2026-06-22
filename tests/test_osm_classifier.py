"""Tests for OSMActivityClassifier — zero-API tag-based activity matching."""
from __future__ import annotations
import pytest

from routeiq.graph.poi import POI
from routeiq.activities.osm_classifier import OSMActivityClassifier


def _poi(name, category="natural", subtype=None, osm_id=None):
    return POI(
        name=name, category=category, lat=0.0, lon=0.0,
        osm_id=osm_id or name.lower().replace(" ", "_"),
        subtype=subtype,
    )


@pytest.fixture
def clf():
    return OSMActivityClassifier()


class TestTagMatching:
    def test_biking_cycling_path_tag(self, clf):
        results = clf.classify_batch("City", [_poi("Bike Path", subtype="cycling_path")], ["biking"])
        assert "biking" in results[0].matched_activities

    def test_biking_track_tag(self, clf):
        results = clf.classify_batch("City", [_poi("Mountain Track", subtype="track")], ["biking"])
        assert "biking" in results[0].matched_activities

    def test_hiking_peak_tag(self, clf):
        results = clf.classify_batch("City", [_poi("Summit", subtype="peak")], ["hiking"])
        assert results[0].matched_activities == ["hiking"]

    def test_hiking_nature_reserve_tag(self, clf):
        results = clf.classify_batch("City", [_poi("Wild Reserve", subtype="nature_reserve")], ["hiking"])
        assert "hiking" in results[0].matched_activities

    def test_kids_playground_tag(self, clf):
        results = clf.classify_batch("City", [_poi("Fun Zone", category="leisure", subtype="playground")], ["kids"])
        assert results[0].matched_activities == ["kids"]

    def test_kids_zoo_tag(self, clf):
        results = clf.classify_batch("City", [_poi("City Zoo", subtype="zoo")], ["kids"])
        assert "kids" in results[0].matched_activities

    def test_swimming_beach_tag(self, clf):
        results = clf.classify_batch("City", [_poi("Sandy Beach", subtype="beach")], ["swimming"])
        assert "swimming" in results[0].matched_activities


class TestKeywordMatching:
    def test_keyword_trail_gives_hiking(self, clf):
        pois = [_poi("Hill Trail", category="trail hiking area")]
        results = clf.classify_batch("City", pois, ["hiking"])
        assert "hiking" in results[0].matched_activities

    def test_keyword_bike_gives_biking(self, clf):
        pois = [_poi("Bike Route", category="bike path")]
        results = clf.classify_batch("City", pois, ["biking"])
        assert "biking" in results[0].matched_activities

    def test_keyword_family_gives_kids(self, clf):
        pois = [_poi("Family Resort", category="family resort")]
        results = clf.classify_batch("City", pois, ["kids"])
        assert "kids" in results[0].matched_activities


class TestNoMatch:
    def test_no_match_returns_empty_list(self, clf):
        pois = [_poi("Random Museum", category="tourism", subtype="museum")]
        results = clf.classify_batch("City", pois, ["biking"])
        assert results[0].matched_activities == []

    def test_evidence_none_on_no_match(self, clf):
        pois = [_poi("Office Tower", category="building")]
        results = clf.classify_batch("City", pois, ["hiking"])
        assert results[0].activity_evidence is None

    def test_activity_not_requested_not_matched(self, clf):
        pois = [_poi("Bike Path", subtype="cycling_path")]
        results = clf.classify_batch("City", pois, ["hiking"])
        assert results[0].matched_activities == []


class TestBatchBehaviour:
    def test_returns_all_pois_including_unmatched(self, clf):
        pois = [
            _poi("Peak", subtype="peak", osm_id="1"),
            _poi("Museum", subtype="museum", osm_id="2"),
        ]
        results = clf.classify_batch("City", pois, ["hiking"])
        assert len(results) == 2

    def test_evidence_set_on_match(self, clf):
        pois = [_poi("Bike Path", subtype="cycling_path")]
        results = clf.classify_batch("City", pois, ["biking"])
        assert results[0].activity_evidence is not None
        assert "OSM tag" in results[0].activity_evidence

    def test_multiple_pois_multiple_activities(self, clf):
        pois = [
            _poi("Trail Peak", subtype="peak", osm_id="1"),
            _poi("Playground", subtype="playground", osm_id="2"),
            _poi("Museum", subtype="museum", osm_id="3"),
        ]
        results = clf.classify_batch("City", pois, ["hiking", "kids"])
        by_id = {r.poi.osm_id: r for r in results}
        assert "hiking" in by_id["1"].matched_activities
        assert "kids" in by_id["2"].matched_activities
        assert by_id["3"].matched_activities == []

    def test_empty_pois_returns_empty(self, clf):
        assert clf.classify_batch("City", [], ["hiking"]) == []

    def test_empty_activities_nothing_matched(self, clf):
        pois = [_poi("Peak", subtype="peak")]
        results = clf.classify_batch("City", pois, [])
        assert results[0].matched_activities == []
