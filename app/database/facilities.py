"""Static registry of supported parking facilities.

Facility *keys* (e.g. "city_center") are the stable identifiers stored in the
database and on reservation records; facility *names* are what's shown to
users/admins. Kept dependency-free (no SQLAlchemy) so it can be imported from
the reservation agent, the graph, and the MCP client/server alike.
"""

from __future__ import annotations

DEFAULT_FACILITY = "city_center"

FACILITIES: dict[str, dict[str, str]] = {
    "city_center": {
        "name": "City Center Parking",
        "address": "100 Main Street, City Center",
    },
    "airport": {
        "name": "Airport Parking",
        "address": "25 Terminal Road, International Airport",
    },
    "railway_station": {
        "name": "Railway Station Parking",
        "address": "8 Platform Avenue, Central Railway Station",
    },
    "mall": {
        "name": "Mall Parking",
        "address": "500 Commerce Boulevard, Grand Mall",
    },
}

_FACILITY_ALIASES: dict[str, tuple[str, ...]] = {
    "city_center": ("city center", "city centre", "city-center"),
    "airport": ("airport",),
    "railway_station": ("railway station", "railway", "train station"),
    "mall": ("mall", "shopping mall"),
}


def match_facility(text: str | None) -> str | None:
    """Best-effort match of a facility key from free text: case-insensitive
    substring match against each facility's known aliases. Returns None if no
    facility is mentioned."""
    if not text:
        return None
    lowered = text.lower()
    for key, aliases in _FACILITY_ALIASES.items():
        if any(alias in lowered for alias in aliases):
            return key
    return None


def facility_name(key: str | None) -> str | None:
    """Human-readable display name for a facility key, or the key itself if
    unknown, or None if `key` is falsy."""
    if not key:
        return None
    return FACILITIES.get(key, {}).get("name", key)
