"""Unit tests for POIKnowledgeStore — uses in-memory ChromaDB EphemeralClient."""
import time
import uuid

import chromadb
import pytest

from routeiq.rag.poi_knowledge_store import POIKnowledgeStore, _build_document, _city_key, _cache_key


def _ephemeral_store():
    # unique collection name per call prevents state leaking across tests
    # (EphemeralClient instances can share an underlying in-process store)
    client = chromadb.EphemeralClient()
    return POIKnowledgeStore(client=client, collection_name=f"test_{uuid.uuid4().hex}")


def _make_entry(poi_name="Alamo", **overrides):
    entry = {
        "poi_name": poi_name,
        "category": "historic",
        "subtype": "mission",
        "lat": 29.42,
        "lon": -98.48,
        "osm_id": "r1",
        "wikipedia_description": "The Alamo is a historic mission in San Antonio.",
        "rating": 4.7,
        "review_count": 1200,
        "all_snippets": ["A must-see historic site."],
        "review_source": "tripadvisor",
        "tavily_highlights": "",
        "photo_urls": [],
        "activity_tags": ["history"],
    }
    entry.update(overrides)
    return entry


class TestBuildDocument:
    def test_concatenates_all_text_sources(self):
        entry = _make_entry(tavily_highlights="Great views at sunset.")
        document, sources = _build_document(entry)
        assert "Alamo is a historic mission" in document
        assert "A must-see historic site." in document
        assert "Great views at sunset." in document
        assert sources == ["wikipedia", "tripadvisor", "tavily"]

    def test_falls_back_to_name_and_category_when_no_text(self):
        entry = _make_entry(wikipedia_description="", all_snippets=[], tavily_highlights="")
        document, sources = _build_document(entry)
        assert document == "Alamo historic"
        assert sources == ["none"]


class TestUpsertAndGetMetadata:
    def test_upsert_then_get_metadata_round_trips(self):
        store = _ephemeral_store()
        store.upsert_batch("San Antonio, TX", [_make_entry()])
        hits = store.get_metadata("San Antonio, TX", ["Alamo"])
        assert "Alamo" in hits
        assert hits["Alamo"]["rating"] == 4.7
        assert hits["Alamo"]["all_snippets"] == ["A must-see historic site."]
        assert hits["Alamo"]["text_sources"] == ["wikipedia", "tripadvisor"]

    def test_get_metadata_missing_poi_returns_empty_dict(self):
        store = _ephemeral_store()
        store.upsert_batch("San Antonio, TX", [_make_entry()])
        hits = store.get_metadata("San Antonio, TX", ["Nonexistent POI"])
        assert hits == {}

    def test_get_metadata_empty_poi_list_returns_empty_dict(self):
        store = _ephemeral_store()
        assert store.get_metadata("San Antonio, TX", []) == {}

    def test_get_metadata_purges_stale_entries_past_ttl(self):
        store = _ephemeral_store()
        store.upsert_batch("San Antonio, TX", [_make_entry()])
        # backdate the timestamp past the 21-day TTL directly in the collection
        key = _cache_key("San Antonio, TX", "Alamo")
        stale_time = int(time.time()) - (51 * 86_400)  # 50-day TTL, so 51 days is stale
        meta = store._col.get(ids=[key], include=["metadatas"])["metadatas"][0]
        meta["timestamp"] = stale_time
        store._col.update(ids=[key], metadatas=[meta])

        hits = store.get_metadata("San Antonio, TX", ["Alamo"])
        assert hits == {}
        # purge should have deleted the stale doc from the collection entirely
        assert store._col.get(ids=[key])["ids"] == []

    def test_upsert_is_idempotent(self):
        store = _ephemeral_store()
        store.upsert_batch("San Antonio, TX", [_make_entry()])
        store.upsert_batch("San Antonio, TX", [_make_entry(rating=4.9)])
        hits = store.get_metadata("San Antonio, TX", ["Alamo"])
        assert hits["Alamo"]["rating"] == 4.9

    def test_city_key_normalizes_separately_from_other_cities(self):
        store = _ephemeral_store()
        store.upsert_batch("Austin, TX", [_make_entry(poi_name="Zilker Park")])
        assert store.get_metadata("San Antonio, TX", ["Zilker Park"]) == {}
        assert "Zilker Park" in store.get_metadata("Austin, TX", ["Zilker Park"])

    def test_city_key_strips_state_suffix_so_both_forms_hit(self):
        store = _ephemeral_store()
        store.upsert_batch("San Francisco, CA", [_make_entry(poi_name="Painted Ladies")])
        # Both 'San Francisco, CA' and bare 'San Francisco' must resolve to the same entry
        assert "Painted Ladies" in store.get_metadata("San Francisco, CA", ["Painted Ladies"])
        assert "Painted Ladies" in store.get_metadata("San Francisco", ["Painted Ladies"])


class TestMissingOrExpired:
    def test_returns_all_names_when_store_empty(self):
        store = _ephemeral_store()
        missing = store.missing_or_expired("San Antonio, TX", ["Alamo", "Tower of the Americas"])
        assert set(missing) == {"Alamo", "Tower of the Americas"}

    def test_returns_only_names_not_yet_warm(self):
        store = _ephemeral_store()
        store.upsert_batch("San Antonio, TX", [_make_entry(poi_name="Alamo")])
        missing = store.missing_or_expired("San Antonio, TX", ["Alamo", "Tower of the Americas"])
        assert missing == ["Tower of the Americas"]

    def test_returns_empty_list_when_all_warm(self):
        store = _ephemeral_store()
        store.upsert_batch("San Antonio, TX", [_make_entry()])
        assert store.missing_or_expired("San Antonio, TX", ["Alamo"]) == []


class TestQuery:
    def test_query_returns_hits_scoped_to_city(self):
        store = _ephemeral_store()
        store.upsert_batch("San Antonio, TX", [_make_entry()])
        store.upsert_batch("Austin, TX", [_make_entry(poi_name="Zilker Park", category="park",
                                                        wikipedia_description="A large park with a natural spring.")])
        hits = store.query("San Antonio, TX", "historic mission", n=5)
        assert len(hits) == 1
        assert hits[0]["poi_name"] == "Alamo"
        assert 0.0 <= hits[0]["score"] <= 1.0

    def test_query_empty_text_returns_empty_list(self):
        store = _ephemeral_store()
        store.upsert_batch("San Antonio, TX", [_make_entry()])
        assert store.query("San Antonio, TX", "", n=5) == []

    def test_query_unknown_city_returns_empty_list(self):
        store = _ephemeral_store()
        store.upsert_batch("San Antonio, TX", [_make_entry()])
        assert store.query("Houston, TX", "historic mission", n=5) == []


class TestQueryWithin:
    def test_query_within_scopes_to_given_poi_names(self):
        store = _ephemeral_store()
        store.upsert_batch("San Antonio, TX", [
            _make_entry(poi_name="Alamo"),
            _make_entry(poi_name="Tower of the Americas", category="observation_tower",
                        wikipedia_description="A tall observation tower with panoramic views."),
        ])
        hits = store.query_within(["Alamo"], "historic mission", n=5)
        assert len(hits) == 1
        assert hits[0]["poi_name"] == "Alamo"

    def test_query_within_empty_poi_names_returns_empty_list(self):
        store = _ephemeral_store()
        store.upsert_batch("San Antonio, TX", [_make_entry()])
        assert store.query_within([], "historic mission", n=5) == []
