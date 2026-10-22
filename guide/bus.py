# NEU: «So kommst du hin»: nächste Bushaltestellen und Route-Links
import math
from urllib.parse import urlencode

from django.utils.translation import gettext as _

from .models import BusStop

WALK_METERS_PER_MINUTE = 80   # gemütliches Gehtempo
DETOUR = 1.25                 # Strassen sind länger als die Luftlinie


def distance_m(lat1, lon1, lat2, lon2):
    # Luftlinie in Metern (Haversine-Formel)
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_stops(lat, lon, limit=3, max_distance=800):
    # Die nächsten Haltestellen (mit mindestens einer Linie) im Umkreis von max_distance Metern
    if lat is None or lon is None:
        return []
    lat, lon = float(lat), float(lon)
    # grobe Vorauswahl mit einem Rechteck, damit nicht alle Haltestellen gerechnet werden müssen
    d_lat = max_distance / 111000
    d_lon = max_distance / (111000 * math.cos(math.radians(lat)))
    candidates = BusStop.objects.filter(
        latitude__range=(lat - d_lat, lat + d_lat),
        longitude__range=(lon - d_lon, lon + d_lon),
    ).exclude(lines=[])
    stops = []
    for stop in candidates:
        d = distance_m(lat, lon, stop.latitude, stop.longitude)
        if d <= max_distance:
            stop.distance = int(round(d, -1)) or 10  # auf 10 m gerundet
            stop.minutes = max(1, round(d * DETOUR / WALK_METERS_PER_MINUTE))
            stops.append(stop)
    stops.sort(key=lambda s: s.distance)
    return stops[:limit]


def route_links(lat, lon):
    # Google Maps mit dem Ziel. Ohne Start nimmt Google den eigenen Standort (fragt im Browser nach).
    if lat is None or lon is None:
        return []
    links = []
    for mode, label, icon in (
        ("transit", _("Mit dem Bus"), "bi-bus-front"),
        ("walking", _("Zu Fuss"), "bi-person-walking"),
        ("bicycling", _("Velo"), "bi-bicycle"),
    ):
        query = urlencode({"api": 1, "destination": f"{float(lat):.6f},{float(lon):.6f}", "travelmode": mode})
        links.append({"url": f"https://www.google.com/maps/dir/?{query}", "label": label, "icon": icon})
    return links
