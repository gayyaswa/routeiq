from __future__ import annotations
from routeiq.graph.poi import POI
from routeiq.activities.base import ActivityClassifier, ClassifiedPOI

_TAG_TO_ACTIVITY: dict[str, str] = {
    "cycling_path":   "biking",
    "track":          "biking",
    "peak":           "hiking",
    "nature_reserve": "hiking",
    "cliff":          "hiking",
    "playground":     "kids",
    "theme_park":     "kids",
    "zoo":            "kids",
    "swimming_pool":  "swimming",
    "beach":          "swimming",
    "water_park":     "swimming",
    "kayaking":       "kayaking",
    "marina":         "kayaking",
    "picnic_site":    "picnic",
    "garden":         "picnic",
}

_CATEGORY_KEYWORDS: dict[str, str] = {
    "bike":   "biking",
    "cycl":   "biking",
    "trail":  "hiking",
    "hike":   "hiking",
    "climb":  "hiking",
    "child":  "kids",
    "family": "kids",
    "play":   "kids",
    "swim":   "swimming",
    "beach":  "swimming",
    "kayak":  "kayaking",
    "canoe":  "kayaking",
    "picnic": "picnic",
}


class OSMActivityClassifier(ActivityClassifier):
    """Classifies activities from OSM tags already present on POI objects (Registry pattern)."""

    def classify_batch(
        self,
        city: str,
        pois: list[POI],
        activities: list[str],
    ) -> list[ClassifiedPOI]:
        activity_set = set(a.lower() for a in activities)
        result = []
        for poi in pois:
            matched = self._match(poi, activity_set)
            evidence = f"OSM tag: {poi.subtype or poi.category}" if matched else None
            result.append(ClassifiedPOI(poi=poi, matched_activities=matched, activity_evidence=evidence))
        return result

    def _match(self, poi: POI, activity_set: set[str]) -> list[str]:
        # Combine category + subtype so both "leisure=cycling_path" style strings
        # and separate subtype fields are searched.
        cat = f"{poi.category or ''} {poi.subtype or ''}".lower()
        matched: set[str] = set()

        for tag_val, activity in _TAG_TO_ACTIVITY.items():
            if activity in activity_set and tag_val in cat:
                matched.add(activity)

        for keyword, activity in _CATEGORY_KEYWORDS.items():
            if activity in activity_set and keyword in cat:
                matched.add(activity)

        # Name-based fallback: catch POIs whose *name* signals an activity even when
        # OSM subtype tags don't (e.g. "Lands End Trail" has subtype=viewpoint, not peak).
        name = (poi.name or "").lower()
        for keyword, activity in _CATEGORY_KEYWORDS.items():
            if activity in activity_set and keyword in name:
                matched.add(activity)

        return list(matched)
