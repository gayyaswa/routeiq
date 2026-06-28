"""Provider-agnostic 21-day ChromaDB cache for rated POI data (Registry pattern)."""
from __future__ import annotations

import json
import time

import chromadb

_PERSIST_DIR = "./cache/chroma"
_COLLECTION = "poi_ratings"
_TTL = 21 * 86_400  # 21 days in seconds

# Module-level singleton — same PersistentClient across all rate_pois calls.
_client: chromadb.ClientAPI | None = None


def _get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=_PERSIST_DIR)
    return _client


def _cache_key(city: str, poi_name: str) -> str:
    safe_city = city.lower().replace(" ", "_").replace(",", "")
    return f"{safe_city}||{poi_name}"


class POIRatingStore:
    """Persists rated POI data in ChromaDB with a 21-day TTL (Registry pattern).

    ChromaDB metadata only accepts str/int/float — lists are serialised as JSON strings.
    The Wikipedia description is stored as the document so it is searchable later.
    """

    def __init__(self, client: chromadb.ClientAPI | None = None) -> None:
        c = client or _get_client()
        self._col = c.get_or_create_collection(_COLLECTION)

    def get_batch(self, city: str, poi_names: list[str]) -> dict[str, dict]:
        """Fetch all POI names in one ChromaDB query. Returns {poi_name: entry} for hits within TTL."""
        if not poi_names:
            return {}
        keys = [_cache_key(city, name) for name in poi_names]
        result = self._col.get(ids=keys, include=["metadatas", "documents"])
        if not result["ids"]:
            return {}

        now = time.time()
        stale_keys: list[str] = []
        hits: dict[str, dict] = {}

        for key, meta, doc in zip(result["ids"], result["metadatas"], result["documents"]):
            if now - float(meta.get("cached_at", 0)) > _TTL:
                stale_keys.append(key)
                continue
            entry = _meta_to_entry(meta)
            entry["description"] = doc or None
            # Recover original poi_name from the key
            poi_name = key.split("||", 1)[-1]
            hits[poi_name] = entry

        if stale_keys:
            self._col.delete(ids=stale_keys)

        return hits

    def put_batch(self, city: str, entries: dict[str, dict]) -> None:
        """Upsert all entries in one ChromaDB call. entries = {poi_name: entry_dict}."""
        if not entries:
            return
        now = int(time.time())
        ids, documents, metadatas = [], [], []
        for poi_name, entry in entries.items():
            ids.append(_cache_key(city, poi_name))
            documents.append(entry.get("description") or "")
            meta = _entry_to_meta(entry)
            meta["cached_at"] = now
            metadatas.append(meta)
        self._col.upsert(ids=ids, documents=documents, metadatas=metadatas)


# ── Serialisation helpers ─────────────────────────────────────────────────────
# ChromaDB metadata values must be str, int, or float — no lists or None.

def _entry_to_meta(entry: dict) -> dict:
    meta: dict = {}
    for k, v in entry.items():
        if k == "description":
            continue  # stored as document
        if v is None:
            meta[k] = ""
        elif isinstance(v, list):
            meta[k] = json.dumps(v)
        elif isinstance(v, (str, int, float, bool)):
            meta[k] = v
        else:
            meta[k] = str(v)
    return meta


_LIST_FIELDS = {"all_snippets", "photo_urls", "matched_activities"}
_FLOAT_FIELDS = {"rating", "composite_score"}
_INT_FIELDS = {"review_count", "visit_duration_min"}


def _meta_to_entry(meta: dict) -> dict:
    entry: dict = {}
    for k, v in meta.items():
        if k == "cached_at":
            continue
        if k in _LIST_FIELDS:
            try:
                entry[k] = json.loads(v) if v else []
            except (ValueError, TypeError):
                entry[k] = []
        elif k in _FLOAT_FIELDS:
            entry[k] = float(v) if v not in ("", None) else None
        elif k in _INT_FIELDS:
            entry[k] = int(v) if v not in ("", None) else None
        elif v == "":
            entry[k] = None
        else:
            entry[k] = v
    return entry
