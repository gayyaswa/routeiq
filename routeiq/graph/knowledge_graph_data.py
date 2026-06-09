"""Seed data for the RouteIQ knowledge graph — POIs, Cities, Regions, Categories."""

CATEGORIES = [
    {"name": "historic"},
    {"name": "natural"},
    {"name": "tourism"},
    {"name": "winery"},
    {"name": "state_park"},
    {"name": "mission"},
]

REGIONS = [
    {"name": "Hill Country",           "type": "scenic_region"},
    {"name": "Highland Lakes",         "type": "scenic_region"},
    {"name": "San Antonio Missions",   "type": "historic_district"},
    {"name": "Blanco Valley",          "type": "scenic_region"},
    {"name": "Texas Wine Country",     "type": "scenic_region"},
]

CITIES = [
    {"name": "Austin",         "lat": 30.2672, "lon": -97.7431},
    {"name": "San Antonio",    "lat": 29.4241, "lon": -98.4936},
    {"name": "New Braunfels",  "lat": 29.7030, "lon": -98.1245},
    {"name": "San Marcos",     "lat": 29.8833, "lon": -97.9414},
    {"name": "Fredericksburg", "lat": 30.2752, "lon": -98.8720},
    {"name": "Kerrville",      "lat": 30.0474, "lon": -99.1403},
    {"name": "Marble Falls",   "lat": 30.5782, "lon": -98.2737},
    {"name": "Round Rock",     "lat": 30.5083, "lon": -97.6789},
]

POIS = [
    {
        "osm_id": "kg_alamo",
        "name": "The Alamo",
        "category": "mission",
        "lat": 29.4260, "lon": -98.4861,
        "city": "San Antonio",
        "region": "San Antonio Missions",
        "wikipedia_tag": "en:The Alamo",
    },
    {
        "osm_id": "kg_concepcion",
        "name": "Mission Concepción",
        "category": "mission",
        "lat": 29.4063, "lon": -98.4874,
        "city": "San Antonio",
        "region": "San Antonio Missions",
        "wikipedia_tag": "en:Mission Concepción",
    },
    {
        "osm_id": "kg_sanjuan",
        "name": "Mission San Juan",
        "category": "mission",
        "lat": 29.3630, "lon": -98.4815,
        "city": "San Antonio",
        "region": "San Antonio Missions",
        "wikipedia_tag": "en:Mission San Juan Capistrano (Texas)",
    },
    {
        "osm_id": "kg_natural_bridge",
        "name": "Natural Bridge Caverns",
        "category": "tourism",
        "lat": 29.6927, "lon": -98.3419,
        "city": "New Braunfels",
        "region": "Hill Country",
        "wikipedia_tag": "en:Natural Bridge Caverns",
    },
    {
        "osm_id": "kg_enchanted_rock",
        "name": "Enchanted Rock",
        "category": "natural",
        "lat": 30.5063, "lon": -98.8198,
        "city": "Fredericksburg",
        "region": "Hill Country",
        "wikipedia_tag": "en:Enchanted Rock",
    },
    {
        "osm_id": "kg_luckenbach",
        "name": "Luckenbach Texas",
        "category": "tourism",
        "lat": 30.1849, "lon": -98.7384,
        "city": "Fredericksburg",
        "region": "Texas Wine Country",
        "wikipedia_tag": "en:Luckenbach, Texas",
    },
    {
        "osm_id": "kg_gruene",
        "name": "Gruene Historic District",
        "category": "historic",
        "lat": 29.7380, "lon": -98.1096,
        "city": "New Braunfels",
        "region": "Blanco Valley",
        "wikipedia_tag": "en:Gruene, Texas",
    },
    {
        "osm_id": "kg_pedernales",
        "name": "Pedernales Falls State Park",
        "category": "state_park",
        "lat": 30.3077, "lon": -98.2566,
        "city": "Marble Falls",
        "region": "Hill Country",
        "wikipedia_tag": "en:Pedernales Falls State Park",
    },
    {
        "osm_id": "kg_old_tunnel",
        "name": "Old Tunnel State Park",
        "category": "natural",
        "lat": 30.1716, "lon": -98.7505,
        "city": "Fredericksburg",
        "region": "Texas Wine Country",
        "wikipedia_tag": "en:Old Tunnel State Park",
    },
    {
        "osm_id": "kg_guadalupe",
        "name": "Guadalupe River State Park",
        "category": "state_park",
        "lat": 29.8472, "lon": -98.4896,
        "city": "New Braunfels",
        "region": "Hill Country",
        "wikipedia_tag": "en:Guadalupe River State Park",
    },
    {
        "osm_id": "kg_becker",
        "name": "Becker Vineyards",
        "category": "winery",
        "lat": 30.2208, "lon": -98.8661,
        "city": "Fredericksburg",
        "region": "Texas Wine Country",
        "wikipedia_tag": "en:Becker Vineyards",
    },
    {
        "osm_id": "kg_hamilton",
        "name": "Hamilton Pool Preserve",
        "category": "natural",
        "lat": 30.3427, "lon": -98.1269,
        "city": "Austin",
        "region": "Hill Country",
        "wikipedia_tag": "en:Hamilton Pool Preserve",
    },
    {
        "osm_id": "kg_wimberley",
        "name": "Wimberley",
        "category": "tourism",
        "lat": 29.9977, "lon": -98.0986,
        "city": "San Marcos",
        "region": "Blanco Valley",
        "wikipedia_tag": "en:Wimberley, Texas",
    },
    {
        "osm_id": "kg_national_museum",
        "name": "San Antonio Missions National Historical Park",
        "category": "historic",
        "lat": 29.3596, "lon": -98.4760,
        "city": "San Antonio",
        "region": "San Antonio Missions",
        "wikipedia_tag": "en:San Antonio Missions National Historical Park",
    },
    {
        "osm_id": "kg_canyon_lake",
        "name": "Canyon Lake",
        "category": "natural",
        "lat": 29.8716, "lon": -98.2617,
        "city": "New Braunfels",
        "region": "Highland Lakes",
        "wikipedia_tag": "en:Canyon Lake (Texas)",
    },
]

# Typed relationships: (source_id, rel_type, target_id)
# source/target ids are osm_id for POIs, name for City/Region/Category
RELATIONSHIPS = (
    # POI -[LOCATED_IN]→ City
    [("kg_alamo",           "LOCATED_IN", "San Antonio")]
  + [("kg_concepcion",      "LOCATED_IN", "San Antonio")]
  + [("kg_sanjuan",         "LOCATED_IN", "San Antonio")]
  + [("kg_national_museum", "LOCATED_IN", "San Antonio")]
  + [("kg_natural_bridge",  "LOCATED_IN", "New Braunfels")]
  + [("kg_gruene",          "LOCATED_IN", "New Braunfels")]
  + [("kg_guadalupe",       "LOCATED_IN", "New Braunfels")]
  + [("kg_canyon_lake",     "LOCATED_IN", "New Braunfels")]
  + [("kg_enchanted_rock",  "LOCATED_IN", "Fredericksburg")]
  + [("kg_luckenbach",      "LOCATED_IN", "Fredericksburg")]
  + [("kg_old_tunnel",      "LOCATED_IN", "Fredericksburg")]
  + [("kg_becker",          "LOCATED_IN", "Fredericksburg")]
  + [("kg_pedernales",      "LOCATED_IN", "Marble Falls")]
  + [("kg_hamilton",        "LOCATED_IN", "Austin")]
  + [("kg_wimberley",       "LOCATED_IN", "San Marcos")]
  # POI -[HAS_CATEGORY]→ Category
  + [(p["osm_id"], "HAS_CATEGORY", p["category"]) for p in POIS]
  # City -[IN_REGION]→ Region
  + [("San Antonio",    "IN_REGION", "San Antonio Missions")]
  + [("New Braunfels",  "IN_REGION", "Hill Country")]
  + [("Fredericksburg", "IN_REGION", "Hill Country")]
  + [("Fredericksburg", "IN_REGION", "Texas Wine Country")]
  + [("Marble Falls",   "IN_REGION", "Highland Lakes")]
  + [("San Marcos",     "IN_REGION", "Blanco Valley")]
  + [("Austin",         "IN_REGION", "Hill Country")]
)
