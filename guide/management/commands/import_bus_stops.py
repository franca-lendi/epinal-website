# NEU: Bushaltestellen und Linien vom Imagine-Netz (Épinal) aus den offenen Fahrplandaten laden.
# Daten: transport.data.gouv.fr, Licence Ouverte 2.0 (Etalab). Ändert sich der Fahrplan, einfach nochmals ausführen.
#   python manage.py import_bus_stops                 (lädt die aktuelle Datei herunter)
#   python manage.py import_bus_stops --file gtfs.zip (eine heruntergeladene Datei verwenden)
import csv
import io
import re
import urllib.request
import zipfile
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from guide.models import BusStop

GTFS_URL = "https://transport.data.gouv.fr/resources/80461/download"
# Schulbusse fahren nur ein paar Mal am Tag. Linien mit weniger Fahrten lassen wir weg.
MIN_TRIPS = 10


def read_csv(archive, name):
    with archive.open(name) as f:
        return list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig")))


def clean_color(value, fallback):
    value = (value or "").strip().lstrip("#")
    return f"#{value.upper()}" if re.fullmatch(r"[0-9A-Fa-f]{6}", value) else fallback


def text_color(background):
    # schwarze oder weisse Schrift, je nachdem was auf der Linienfarbe besser lesbar ist
    r, g, b = (int(background[i:i + 2], 16) for i in (1, 3, 5))
    return "#000000" if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else "#FFFFFF"


def line_sort_key(line):
    # 1, 2, 3 ... vor den Buchstaben-Linien
    return (0, int(line["name"]), "") if line["name"].isdigit() else (1, 0, line["name"])


class Command(BaseCommand):
    help = "Lädt die Bushaltestellen und Linien von Imagine (Épinal) aus den GTFS-Fahrplandaten."

    def add_arguments(self, parser):
        parser.add_argument("--file", help="Pfad zu einer GTFS-ZIP-Datei statt herunterladen")

    def handle(self, *args, **options):
        if options["file"]:
            data = open(options["file"], "rb").read()
        else:
            self.stdout.write("Lade Fahrplandaten herunter ...")
            request = urllib.request.Request(GTFS_URL, headers={"User-Agent": "Epinal-Guide (Maturaarbeit)"})
            try:
                data = urllib.request.urlopen(request, timeout=60).read()
            except OSError as error:
                raise CommandError(f"Download ging nicht: {error}")
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            raise CommandError("Das ist keine GTFS-ZIP-Datei.")

        routes = {r["route_id"]: r for r in read_csv(archive, "routes.txt")}
        trips = read_csv(archive, "trips.txt")
        trip_count = Counter(t["route_id"] for t in trips)
        trip_route = {t["trip_id"]: t["route_id"] for t in trips if trip_count[t["route_id"]] >= MIN_TRIPS}

        stops = {s["stop_id"]: s for s in read_csv(archive, "stops.txt")}

        def station_id(stop_id):
            # Haltekanten (Quai A, Quai B ...) zur Haltestelle zusammenfassen
            parent = stops.get(stop_id, {}).get("parent_station")
            return parent if parent in stops else stop_id

        station_routes = defaultdict(set)
        for row in read_csv(archive, "stop_times.txt"):
            route_id = trip_route.get(row["trip_id"])
            if route_id and row["stop_id"] in stops:
                station_routes[station_id(row["stop_id"])].add(route_id)

        new_stops = []
        for sid, route_ids in station_routes.items():
            stop = stops[sid]
            lines = []
            for route_id in route_ids:
                route = routes[route_id]
                name = route["route_short_name"].strip() or route_id
                if name.isdigit():
                    name = str(int(name))  # "04" -> "4"
                color = clean_color(route.get("route_color"), "#55704F")
                lines.append({"name": name, "color": color,
                              "text": clean_color(route.get("route_text_color"), text_color(color))})
            lines.sort(key=line_sort_key)
            stop_name = stop["stop_name"].strip()
            if stop_name.islower():
                stop_name = stop_name.title()  # "maurice ravel" -> "Maurice Ravel"
            new_stops.append(BusStop(name=stop_name, latitude=float(stop["stop_lat"]),
                                     longitude=float(stop["stop_lon"]), lines=lines))

        if not new_stops:
            raise CommandError("Keine Haltestellen gefunden, alte Daten bleiben.")
        with transaction.atomic():
            BusStop.objects.all().delete()
            BusStop.objects.bulk_create(new_stops)
        self.stdout.write(self.style.SUCCESS(f"{len(new_stops)} Haltestellen gespeichert."))
