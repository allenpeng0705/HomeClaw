"""
Reverse geocoding: convert lat/lng to human-readable address (country, city, street).
Used when Companion/mobile app sends location as coordinates; we store an address for plugins and display.
Uses OpenStreetMap Nominatim (no API key). Optional config for alternative provider.
"""
import json
import logging
import re
from typing import Any, Dict, Optional, Tuple

try:
    from loguru import logger
except ImportError:
    logger = logging.getLogger(__name__)

_USER_AGENT = "HomeClaw/1.0 (location-to-address; https://github.com/yourusername/HomeClaw)"
_NOMINATIM_REVERSE = "https://nominatim.openstreetmap.org/reverse"


def parse_lat_lng(value: Any) -> Optional[Tuple[float, float]]:
    """
    Parse latitude and longitude from various formats (Companion/mobile may send string or dict).
    Returns (lat, lng) or None if not recognizable as coordinates.
    """
    if value is None:
        return None
    if isinstance(value, dict):
        lat = value.get("lat") or value.get("latitude")
        lng = value.get("lng") or value.get("lon") or value.get("longitude")
        if lat is not None and lng is not None:
            try:
                return (float(lat), float(lng))
            except (TypeError, ValueError):
                pass
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        # JSON string?
        if value.startswith("{"):
            try:
                d = json.loads(value)
                return parse_lat_lng(d)
            except (json.JSONDecodeError, TypeError):
                pass
        # "lat,lng" or "lat, lng" or "lat lng"
        parts = re.split(r"[\s,]+", value, maxsplit=1)
        if len(parts) >= 2:
            try:
                lat = float(parts[0].strip())
                lng = float(parts[1].strip())
                if -90 <= lat <= 90 and -180 <= lng <= 180:
                    return (lat, lng)
            except (TypeError, ValueError):
                pass
    return None


def reverse_geocode(
    lat: float,
    lng: float,
    *,
    user_agent: Optional[str] = None,
    timeout: float = 5.0,
) -> Optional[str]:
    """
    Convert (lat, lng) to a short address string (e.g. "Street, City, Country").
    Uses Nominatim (OSM); no API key. Respects 1 req/s; best used when storing location, not in tight loops.
    Returns None on failure or timeout. Never raises.
    """
    try:
        import urllib.request
        import urllib.parse

        params = {"lat": lat, "lon": lng, "format": "json", "addressdetails": "1"}
        url = _NOMINATIM_REVERSE + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": user_agent or _USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if not isinstance(data, dict):
            return None
        # Prefer structured address: country, city/town/village, road
        addr = data.get("address")
        if isinstance(addr, dict):
            country = addr.get("country") or ""
            city = (
                addr.get("city")
                or addr.get("town")
                or addr.get("village")
                or addr.get("municipality")
                or addr.get("county")
                or ""
            )
            road = (addr.get("road") or addr.get("street") or "").strip()
            parts = []
            if road:
                parts.append(road)
            if city:
                parts.append(city)
            if country:
                parts.append(country)
            if parts:
                return ", ".join(parts)
        # Fallback: display_name (full string from Nominatim)
        display = (data.get("display_name") or "").strip()
        if display:
            return display[:500]
        return None
    except Exception as e:
        logger.debug("Reverse geocode failed for ({}, {}): {}", lat, lng, e)
        return None


def location_to_address(
    location_input: Any,
    *,
    reverse_geocode_fn: Optional[Any] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Normalize location from request: if it's lat/lng, convert to address; otherwise return as-is.
    Returns (display_location, lat_lng_str).
    - display_location: string to store and show (address or original if already text).
    - lat_lng_str: "lat,lng" if input was coordinates (for plugins that need coords), else None.
    """
    if location_input is None:
        return None, None
    # Already a plain address string (no digits-only comma pair)
    if isinstance(location_input, str):
        s = location_input.strip()
        if not s:
            return None, None
        coords = parse_lat_lng(s)
        if coords is None:
            return s[:2000], None
        lat, lng = coords
    else:
        coords = parse_lat_lng(location_input)
        if coords is None:
            return None, None
        lat, lng = coords

    lat_lng_str = f"{lat},{lng}"
    rev = reverse_geocode_fn or reverse_geocode
    try:
        address = rev(lat, lng) if callable(rev) else None
    except Exception:
        address = None
    if address and address.strip():
        return address.strip()[:500], lat_lng_str
    # Keep coordinates as display if reverse failed (still better than nothing)
    return lat_lng_str, lat_lng_str
