from __future__ import annotations
from routeiq.graph.poi import POI
from routeiq.activities.base import ActivityClassifier, ClassifiedPOI

# Values may be a single activity string or a list for POI types that serve multiple intents
# (e.g. nature_reserve → hiking + nature; hot_spring → swimming + nature).
_TAG_TO_ACTIVITY: dict[str, str | list[str]] = {
    # biking
    "cycling_path":        "biking",
    "track":               "biking",
    # hiking
    "peak":                "hiking",
    "cliff":               ["hiking", "nature"],
    # nature — parks/reserves/water features; reserves also match hiking
    "nature_reserve":      ["hiking", "nature"],
    "park":                "nature",
    "garden":              ["picnic", "nature"],
    "wood":                "nature",
    "waterfall":           ["hiking", "nature"],
    "lake":                "nature",
    "hot_spring":          ["swimming", "nature"],
    "cave_entrance":       "nature",
    "volcano":             "nature",
    "glacier":             "nature",
    "dune":                "nature",
    # kids
    "playground":          "kids",
    "theme_park":          "kids",
    "zoo":                 "kids",
    # swimming
    "swimming_pool":       "swimming",
    "beach":               "swimming",
    "water_park":          "swimming",
    # kayaking
    "kayaking":            "kayaking",
    "marina":              "kayaking",
    # picnic
    "picnic_site":         "picnic",
    # landmarks — iconic tourist attractions and structures OSM tags as tourism/infrastructure
    "attraction":          "landmarks",
    "landmark":            "landmarks",
    "aquarium":            "landmarks",
    # food / nightlife
    "restaurant":          "food",
    "cafe":                "food",
    "bar":                 "food",
    "pub":                 "food",
    "nightclub":           "food",
    "winery":              "food",
    "brewery":             "food",
    "food_court":          "food",
    "marketplace":         "food",
    # history — built heritage and cultural sites
    "museum":              "history",
    "ruins":               "history",
    "castle":              "history",
    "fort":                "history",
    "archaeological_site": "history",
    "monument":            "history",
    "memorial":            "history",
    "battlefield":         "history",
    "mission":             "history",
    "historic":            "history",
    # scenic — viewpoints and coastal geography
    "viewpoint":           "scenic",
    "lighthouse":          "scenic",
    "cape":                "scenic",
    "bay":                 "scenic",
    "overlook":            "scenic",
    # arts — galleries, performing arts, cultural venues
    "gallery":             "arts",
    "theatre":             "arts",
    "arts_centre":         "arts",
}

_CATEGORY_KEYWORDS: dict[str, str | list[str]] = {
    # biking
    "bike":     "biking",
    "cycl":     "biking",
    # hiking
    "trail":    "hiking",
    "hike":     "hiking",
    "climb":    "hiking",
    # nature
    "wildlif":  "nature",
    "forest":   "nature",
    # kids
    "child":    "kids",
    "family":   "kids",
    "play":     "kids",
    # swimming
    "swim":     "swimming",
    "beach":    "swimming",
    # kayaking
    "kayak":    "kayaking",
    "canoe":    "kayaking",
    # picnic
    "picnic":   "picnic",
    # landmarks
    "landmark": "landmarks",
    "attract":  "landmarks",
    "tower":    "landmarks",
    "bridge":   "landmarks",
    "pier":     "landmarks",
    # food / nightlife
    "winer":    "food",
    "brew":     "food",
    "restaur":  "food",
    "nightcl":  "food",
    # history
    "histor":   "history",
    "museum":   "history",
    "mission":  "history",
    "castle":   "history",
    "battlef":  "history",
    # scenic
    "view":     "scenic",
    "overlook": "scenic",
    "vista":    "scenic",
    "panoram":  "scenic",
    # arts
    "galleri":  "arts",
    "theatr":   "arts",
    "exhibit":  "arts",
    "arts_c":   "arts",
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
            matched, source = self._match(poi, activity_set)
            evidence = f"{source}: {poi.subtype or poi.category}" if matched else None
            result.append(ClassifiedPOI(poi=poi, matched_activities=matched, activity_evidence=evidence))
        return result

    def _match(self, poi: POI, activity_set: set[str]) -> tuple[list[str], str]:
        """Return (matched_activities, source) where source is 'osm', 'name', or 'description'."""
        cat = f"{poi.category or ''} {poi.subtype or ''}".lower()
        matched: set[str] = set()

        for tag_val, activities in _TAG_TO_ACTIVITY.items():
            acts = [activities] if isinstance(activities, str) else activities
            for activity in acts:
                if activity in activity_set and tag_val in cat:
                    matched.add(activity)

        for keyword, activities in _CATEGORY_KEYWORDS.items():
            acts = [activities] if isinstance(activities, str) else activities
            for activity in acts:
                if activity in activity_set and keyword in cat:
                    matched.add(activity)

        if matched:
            return list(matched), "osm"

        # Name-based fallback: catch POIs whose *name* signals an activity even when
        # OSM subtype tags don't (e.g. "Lands End Trail" has subtype=viewpoint, not peak).
        name = (poi.name or "").lower()
        for keyword, activities in _CATEGORY_KEYWORDS.items():
            acts = [activities] if isinstance(activities, str) else activities
            for activity in acts:
                if activity in activity_set and keyword in name:
                    matched.add(activity)

        if matched:
            return list(matched), "name"

        # Description-text fallback: reuse the same _CATEGORY_KEYWORDS on the Wikipedia
        # or synthetic description so we don't duplicate the keyword vocabulary.
        desc = (poi.description or "").lower()
        if desc:
            for keyword, activities in _CATEGORY_KEYWORDS.items():
                acts = [activities] if isinstance(activities, str) else activities
                for activity in acts:
                    if activity in activity_set and keyword in desc:
                        matched.add(activity)

        return list(matched), "description" if matched else ""
