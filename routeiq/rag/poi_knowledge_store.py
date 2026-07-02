"""Unified ChromaDB knowledge store for POI text + structured metadata (Registry pattern).

Replaces the separate POIRatingStore (ratings cache) and the ephemeral Wikipedia collection
used by query_poi_context.  All text sources (Wikipedia + TripAdvisor + Tavily) are
concatenated into one embedding vector per POI, enabling cross-source semantic search.
"""
from __future__ import annotations

import json
import time

import chromadb

_PERSIST_DIR = "./cache/chroma"
_COLLECTION = "poi_knowledge"
_TTL = 50 * 86_400  # 50 days in seconds

_client: chromadb.ClientAPI | None = None


def _get_client() -> chromadb.ClientAPI:
    """Return the module-level PersistentClient singleton, creating it on first use."""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=_PERSIST_DIR)
    return _client


def _city_key(city: str) -> str:
    """Normalize city to a stable key using only the city name (pre-comma), ignoring state/country.

    Strips the state suffix so 'San Francisco, CA' and 'San Francisco' produce the same key.
    This makes the store robust to LLMs that omit the state when calling rate_pois.
    """
    return city.lower().split(",")[0].strip().replace(" ", "_")


def _cache_key(city: str, poi_name: str) -> str:
    """Build the ChromaDB document id for a (city, poi_name) pair."""
    return f"{_city_key(city)}::{poi_name}"


def _build_document(entry: dict) -> tuple[str, list[str]]:
    """Concatenate all text sources into one embedding string.

    Returns (document, text_sources) — text_sources records which providers
    contributed text, so provenance survives the concatenation (e.g. for
    showing "via Wikipedia + TripAdvisor" in the UI later).
    """
    parts: list[str] = []
    sources: list[str] = []
    if entry.get("wikipedia_description"):
        parts.append(entry["wikipedia_description"])
        sources.append("wikipedia")
    snippets = entry.get("all_snippets") or []
    if snippets:
        parts.append(" ".join(snippets))
        sources.append((entry.get("review_source") or "provider").lower())
    if entry.get("tavily_highlights"):
        parts.append(entry["tavily_highlights"])
        sources.append("tavily")
    if not parts:
        # Minimal fallback — ChromaDB rejects empty documents
        parts.append(f"{entry.get('poi_name', '')} {entry.get('category', '')}".strip() or "unknown")
        sources.append("none")
    return "\n".join(parts), sources


_LIST_FIELDS = {"all_snippets", "photo_urls", "activity_tags", "text_sources"}
_FLOAT_FIELDS = {"rating", "composite_score", "lat", "lon", "scenic_score"}
_INT_FIELDS = {"review_count", "visit_duration_min", "timestamp"}


def _to_meta(entry: dict) -> dict:
    """Flatten entry to ChromaDB-safe metadata (str / int / float only)."""
    skip = {"wikipedia_description", "tavily_highlights"}
    meta: dict = {}
    for k, v in entry.items():
        if k in skip:
            continue
        if v is None:
            meta[k] = ""
        elif isinstance(v, list):
            meta[k] = json.dumps(v)
        elif isinstance(v, dict):
            meta[k] = json.dumps(v)
        elif isinstance(v, (str, int, float, bool)):
            meta[k] = v
        else:
            meta[k] = str(v)
    return meta


def _from_meta(meta: dict) -> dict:
    """Restore Python types from ChromaDB metadata."""
    out: dict = {}
    for k, v in meta.items():
        if k in _LIST_FIELDS:
            try:
                out[k] = json.loads(v) if v else []
            except (ValueError, TypeError):
                out[k] = []
        elif k in _FLOAT_FIELDS:
            out[k] = float(v) if v not in ("", None) else None
        elif k in _INT_FIELDS:
            out[k] = int(v) if v not in ("", None) else None
        elif v == "":
            out[k] = None
        else:
            out[k] = v
    return out


class POIKnowledgeStore:
    """Unified ChromaDB store — single embedding per POI from all text sources (Registry pattern)."""

    def __init__(self, client: chromadb.ClientAPI | None = None, collection_name: str = _COLLECTION) -> None:
        # collection_name is overridable so tests can isolate state — EphemeralClient
        # instances can share an underlying in-process store, so a fixed name would
        # leak documents across test cases (see POIIndexer's test fixture for the same issue).
        c = client or _get_client()
        self._col = c.get_or_create_collection(collection_name)

    # ── Write ─────────────────────────────────────────────────────────────────

    def upsert_batch(self, city: str, entries: list[dict]) -> None:
        """Upsert enriched POI entries. Each dict must have 'poi_name'."""
        if not entries:
            return
        now = int(time.time())
        city_safe = _city_key(city)
        ids, documents, metadatas = [], [], []
        for entry in entries:
            poi_name = entry.get("poi_name") or entry.get("name", "")
            document, text_sources = _build_document(entry)
            ids.append(_cache_key(city, poi_name))
            documents.append(document)
            meta = _to_meta(entry)
            meta["poi_name"] = poi_name
            meta["city"] = city_safe
            meta["timestamp"] = now
            meta["text_sources"] = json.dumps(text_sources)
            metadatas.append(meta)
        self._col.upsert(ids=ids, documents=documents, metadatas=metadatas)

    # ── Read (metadata-only lookup) ───────────────────────────────────────────

    def get_metadata(self, city: str, poi_names: list[str]) -> dict[str, dict]:
        """Batch fetch structured metadata for POIs within TTL.

        Returns {poi_name: metadata_dict}. Purges stale entries automatically.
        """
        if not poi_names:
            return {}
        keys = [_cache_key(city, n) for n in poi_names]
        result = self._col.get(ids=keys, include=["metadatas"])
        if not result["ids"]:
            return {}

        now = time.time()
        stale: list[str] = []
        hits: dict[str, dict] = {}

        for key, meta in zip(result["ids"], result["metadatas"]):
            if now - float(meta.get("timestamp", 0)) > _TTL:
                stale.append(key)
                continue
            poi_name = meta.get("poi_name") or key.split("::", 1)[-1]
            hits[poi_name] = _from_meta(meta)

        if stale:
            self._col.delete(ids=stale)
        return hits

    def missing_or_expired(self, city: str, poi_names: list[str]) -> list[str]:
        """Return POI names absent from the store or past the 50-day TTL — these need prefetch."""
        present = set(self.get_metadata(city, poi_names).keys())
        return [n for n in poi_names if n not in present]

    # ── Read (semantic search) ────────────────────────────────────────────────

    def query(self, city: str, query_text: str, n: int = 10) -> list[dict]:
        """Semantic search within a city's POIs.

        Returns up to n dicts sorted by similarity, each with all metadata fields
        plus 'score' (0–1, higher = better) and 'text_sources' provenance.
        """
        if not query_text:
            return []
        city_safe = _city_key(city)
        try:
            result = self._col.query(
                query_texts=[query_text],
                n_results=min(n * 3, 100),
                where={"city": city_safe},
                include=["metadatas", "distances"],
            )
        except Exception:
            return []

        if not result["ids"] or not result["ids"][0]:
            return []

        hits = []
        for meta, dist in zip(result["metadatas"][0], result["distances"][0]):
            entry = _from_meta(meta)
            # ChromaDB returns L2 distance; map to 0–1 similarity
            entry["score"] = max(0.0, 1.0 - dist / 2.0)
            hits.append(entry)

        return sorted(hits[:n], key=lambda x: x["score"], reverse=True)

    def query_within(self, poi_names: list[str], query_text: str, n: int = 10) -> list[dict]:
        """Semantic search scoped to a specific candidate set of POI names.

        Used by callers (like query_poi_context) that already have a POI shortlist
        — e.g. the output of rate_pois, already scoped to one city — and want to
        rank/filter it by relevance to a preference string.
        """
        if not query_text or not poi_names:
            return []
        try:
            result = self._col.query(
                query_texts=[query_text],
                n_results=min(len(poi_names), 100),
                where={"poi_name": {"$in": poi_names}},
                include=["metadatas", "distances"],
            )
        except Exception:
            return []

        if not result["ids"] or not result["ids"][0]:
            return []

        hits = []
        for meta, dist in zip(result["metadatas"][0], result["distances"][0]):
            entry = _from_meta(meta)
            entry["score"] = max(0.0, 1.0 - dist / 2.0)
            hits.append(entry)

        return sorted(hits[:n], key=lambda x: x["score"], reverse=True)
