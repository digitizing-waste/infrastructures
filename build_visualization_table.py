#!/usr/bin/env python3
"""
Build the static data file for the map visualization.

Joins Infrastructure, Location, and Entity JSON exports into a single
docs/data.json that the Leaflet map can load directly.

Usage:
    python3 build_visualization_table.py
"""

import json
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).parent / "data" / "JSON"
DOCS_DIR = Path(__file__).parent / "docs"
OUTPUT_FILE = DOCS_DIR / "data.json"

# ---------------------------------------------------------------------------
# Type → colour mapping (mirrors index.html)
# ---------------------------------------------------------------------------
TYPE_COLORS = {
    "oil field":               "#8B4513",
    "refinery":                "#FF6B35",
    "pipeline":                "#4ECDC4",
    "natural gas deposit":     "#95E1D3",
    "nuclear center":          "#FFDA33",
    "distribution point":      "#A8E6CF",
    "Gas liquefaction plant":  "#FF8B94",
    "pumping station":         "#B4A7D6",
    "oil well":                "#704214",
}


def load_json(filename: str) -> list:
    path = DATA_DIR / filename
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_location_lookup(locations: list) -> dict:
    """Return {location_id: {name, lat, lon}} — only for records with valid coordinates."""
    lookup = {}
    for loc in locations:
        lat = loc.get("latitude (N)")
        lon = loc.get("longitude (E)")
        # Validate coordinate ranges
        if (
            lat is not None and lon is not None
            and -90 <= lat <= 90
            and -180 <= lon <= 180
        ):
            lookup[loc["Id"]] = {
                "name": loc.get("location", ""),
                "lat": lat,
                "lon": lon,
            }
        elif lat is not None or lon is not None:
            print(f"  Warning: bad coords for location '{loc.get('location')}' "
                  f"(Id={loc['Id']}): lat={lat}, lon={lon} — skipped")
    return lookup


def build_entity_lookup(entities: list) -> dict:
    """Return {entity_id: entity_name}."""
    return {e["Id"]: e.get("name", "Unknown") for e in entities}


def resolve_locations(infra: dict, loc_lookup: dict) -> list:
    """Return list of {name, lat, lon} for an infrastructure record."""
    points = []
    for link in infra.get("_nc_m2m_infrastructure_locations", []):
        lid = link.get("location_id")
        if lid and lid in loc_lookup:
            points.append(loc_lookup[lid])
    return points


def resolve_entities(infra: dict, entity_lookup: dict) -> list:
    """Return list of entity names linked to an infrastructure record."""
    names = []
    for link in infra.get("_nc_m2m_entity_infrastructures", []):
        eid = link.get("entity_id")
        if eid and eid in entity_lookup:
            names.append(entity_lookup[eid])
    return names


def centroid(points: list) -> tuple:
    """Return the average lat/lon of a list of {lat, lon} dicts."""
    lat = sum(p["lat"] for p in points) / len(points)
    lon = sum(p["lon"] for p in points) / len(points)
    return lat, lon


def build_feature(infra: dict, loc_lookup: dict, entity_lookup: dict) -> dict | None:
    """
    Build a GeoJSON-style feature dict for one infrastructure record.
    Returns None if no coordinate data is available.
    """
    infra_type = infra.get("infrastructure_type") or "unknown"
    is_pipeline = infra_type.lower() == "pipeline"

    location_points = resolve_locations(infra, loc_lookup)
    if not location_points:
        return None  # nothing to plot

    entity_names = resolve_entities(infra, entity_lookup)

    # Location label(s)
    location_label = ", ".join(p["name"] for p in location_points)

    # Compute display position
    lat, lon = centroid(location_points)

    # For pipelines with 2+ points, keep the ordered coordinate list
    coordinates = [[p["lon"], p["lat"]] for p in location_points] if is_pipeline else None

    return {
        "id":              infra["Id"],
        "name":            (infra.get("infrastructure_name") or "Unnamed").strip(),
        "type":            infra_type,
        "color":           TYPE_COLORS.get(infra_type, "#888888"),
        "status":          infra.get("status"),
        "notes":           infra.get("notes"),
        "entities":        entity_names,
        "location_label":  location_label,
        # Point (all types, used as marker / tooltip anchor)
        "lat":             lat,
        "lon":             lon,
        # Polyline (pipelines only; null for everything else)
        "is_pipeline":     is_pipeline,
        "coordinates":     coordinates,  # [[lon, lat], ...] or null
        # Counts
        "actions_count":   infra.get("actions- timeline", 0),
        "events_count":    infra.get("related_events", 0),
        "licenses_count":  infra.get("licenses", 0),
    }


def main():
    print("Loading source JSON files …")
    infrastructures = load_json("Infrastructure_data.json")
    locations       = load_json("Location_data.json")
    entities        = load_json("Entity_data.json")

    print(f"  Infrastructure records : {len(infrastructures)}")
    print(f"  Location records       : {len(locations)}")
    print(f"  Entity records         : {len(entities)}")

    loc_lookup    = build_location_lookup(locations)
    entity_lookup = build_entity_lookup(entities)

    print(f"  Locations with coords  : {len(loc_lookup)}")

    features = []
    skipped  = []

    for infra in infrastructures:
        feature = build_feature(infra, loc_lookup, entity_lookup)
        if feature:
            features.append(feature)
        else:
            skipped.append(infra.get("infrastructure_name") or f"Id={infra['Id']}")

    if skipped:
        print(f"\nSkipped (no coordinates): {len(skipped)}")
        for name in skipped:
            print(f"  - {name}")

    DOCS_DIR.mkdir(exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(features, f, ensure_ascii=False, indent=2)

    print(f"\nWrote {len(features)} features → {OUTPUT_FILE}")

    # Summary by type
    from collections import Counter
    types = Counter(f["type"] for f in features)
    print("\nFeatures by type:")
    for t, n in sorted(types.items()):
        print(f"  {t:<30} {n}")


if __name__ == "__main__":
    main()
