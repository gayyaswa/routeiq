"""Agent evaluation queries and preference keyword map for Week 3 eval."""

PREFERENCE_KEYWORDS: dict[str, list[str]] = {
    "history": ["historic", "museum", "monument", "memorial", "mission"],
    "art": ["museum", "gallery", "art", "mural", "theater"],
    "nature": ["park", "garden", "forest", "lake", "trail", "hill", "natural"],
    "outdoor": ["park", "beach", "trail", "garden", "viewpoint"],
    "viewpoints": ["vista", "overlook", "viewpoint", "lookout", "peak", "tower"],
    "food": ["restaurant", "market", "food", "cafe", "bakery"],
    "music": ["jazz", "music", "concert", "venue"],
    "culture": ["museum", "gallery", "theater", "library", "cultural"],
    "parks": ["park", "garden", "green"],
    "beaches": ["beach", "ocean", "cove", "waterfront", "shore"],
    "waterfront": ["waterfront", "bay", "harbor", "pier", "embarcadero"],
    "museums": ["museum", "gallery", "exhibit"],
    "scenic": ["view", "scenic", "panorama", "overlook"],
}

AGENT_EVAL_QUERIES: list[dict] = [
    {
        "id": 1,
        "city": "San Francisco, CA",
        "preferences": ["history", "art"],
        "hours": 8.0,
        "start_time": "9:00 AM",
        "notes": "Classic SF cultural day",
    },
    {
        "id": 2,
        "city": "San Francisco, CA",
        "preferences": ["nature", "outdoor", "viewpoints"],
        "hours": 6.0,
        "start_time": "10:00 AM",
        "notes": "SF parks and panoramas",
    },
    {
        "id": 3,
        "city": "Oakland, CA",
        "preferences": ["food", "art", "waterfront"],
        "hours": 7.0,
        "start_time": "11:00 AM",
        "notes": "Oakland food and culture",
    },
    {
        "id": 4,
        "city": "Berkeley, CA",
        "preferences": ["nature", "food", "culture"],
        "hours": 5.0,
        "start_time": "9:00 AM",
        "notes": "Berkeley mix",
    },
    {
        "id": 5,
        "city": "San Jose, CA",
        "preferences": ["parks", "food"],
        "hours": 6.0,
        "start_time": "9:00 AM",
        "notes": "San Jose outdoors + food",
    },
    {
        "id": 6,
        "city": "San Francisco, CA",
        "preferences": ["history", "museums"],
        "hours": 8.0,
        "start_time": "9:00 AM",
        "refine_feedback": "Skip museums, add beaches and waterfront stops instead",
        "notes": "Refinement test — validates Phase 1+2 fix",
    },
]
