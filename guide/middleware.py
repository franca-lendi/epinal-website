"""
Besucherzähler (insgesamt).

Eine Middleware läuft bei JEDER Anfrage mit. Diese hier zählt:
- page_views: jede aufgerufene Seite
- visitors:   jede Person nur EINMAL

Wie erkennen wir, ob jemand schon gezählt wurde? Mit einem kleinen Cookie "counted",
in dem nur "1" steht. Es werden KEINE Namen, IP-Adressen oder anderen persönlichen Daten gespeichert.
Wer die Cookies löscht oder ein anderes Gerät benutzt, wird nochmals gezählt.
"""
import re

from django.db.models import F

from .models import VisitCounter

COOKIE_NAME = "counted"
COOKIE_AGE = 60 * 60 * 24 * 365  # 1 Jahr

# Diese Adressen zählen nicht (Admin, Dateien)
IGNORED_PATHS = ("/admin/", "/static/", "/media/", "/favicon")
# Suchmaschinen-Roboter nicht mitzählen
BOT_PATTERN = re.compile(r"bot|crawl|spider|slurp|preview", re.IGNORECASE)


class VisitCounterMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if self.should_count(request, response):
            new_visitor = COOKIE_NAME not in request.COOKIES
            self.count(new_visitor)
            if new_visitor:
                response.set_cookie(COOKIE_NAME, "1", max_age=COOKIE_AGE, samesite="Lax")
        return response

    def should_count(self, request, response):
        if request.method != "GET" or response.status_code != 200:
            return False
        if request.path.startswith(IGNORED_PATHS):
            return False
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return False
        if BOT_PATTERN.search(request.headers.get("User-Agent", "")):
            return False
        if request.user.is_authenticated and request.user.is_staff:
            return False  # dich selbst (Admin) nicht mitzählen
        return "text/html" in response.get("Content-Type", "")

    def count(self, new_visitor):
        VisitCounter.load()  # beim allerersten Mal die Zeile anlegen
        # F() = direkt in der Datenbank +1 rechnen (stimmt auch, wenn zwei gleichzeitig kommen)
        VisitCounter.objects.filter(pk=1).update(
            page_views=F("page_views") + 1,
            visitors=F("visitors") + (1 if new_visitor else 0),
        )
