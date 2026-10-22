from django.contrib.auth.models import User
from django.db import models
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _


class Category(models.Model):
    name = models.CharField(max_length=100)
    # NEU: eigene Reihenfolge im Filter und im Formular (1 = ganz oben), im Admin änderbar
    position = models.PositiveSmallIntegerField("Reihenfolge", default=0)
    # NEU: Unterkategorien, z.B. Sport & Bewegung -> Fussball. Hauptkategorien haben kein parent.
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT,
                               related_name="children", verbose_name="Hauptkategorie")
    # NEU: Vorschläge von Nutzer:innen ("Andere" + eigene Sportart) erscheinen erst nach der Freigabe im Filter
    approved = models.BooleanField("freigegeben", default=True)
    # NEU: Name auf Französisch (leer = deutscher Name wird angezeigt)
    name_fr = models.CharField("Name auf Französisch", max_length=100, blank=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["position", "name"]

    def __str__(self):
        # im Admin: "Sport & Bewegung › Fussball"
        return f"{self.parent.name} › {self.name}" if self.parent_id else self.name

    @property
    def display_name(self):
        # NEU: Name in der gewählten Sprache (Französisch, wenn vorhanden)
        if self.name_fr and (get_language() or "").startswith("fr"):
            return self.name_fr
        return self.name

    @property
    def label(self):
        # auf der Website: die Unterkategorie, bei "Andere" aber die Hauptkategorie
        if self.parent_id and self.name == "Andere":
            return self.parent.display_name
        return self.display_name


class Location(models.Model):
    address = models.CharField(max_length=255, blank=True)
    postal_code = models.CharField(max_length=10, blank=True)  # NEU (steht so im ERM)
    city = models.CharField(max_length=100, default="Épinal")
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)

    def __str__(self):
        # z.B. "2 Faubourg de Poissompré, 88000 Épinal"
        place = f"{self.postal_code} {self.city}".strip()
        return f"{self.address}, {place}" if self.address else place


# NEU: Wochentage für die Öffnungszeiten (Kürzel im JSON, kurz für die Anzeige, lang fürs Formular)
WEEKDAYS = [
    ("mo", _("Mo"), _("Montag")),
    ("di", _("Di"), _("Dienstag")),
    ("mi", _("Mi"), _("Mittwoch")),
    ("do", _("Do"), _("Donnerstag")),
    ("fr", _("Fr"), _("Freitag")),
    ("sa", _("Sa"), _("Samstag")),
    ("so", _("So"), _("Sonntag")),
]


def shows_translation(obj):
    # NEU: Übersetzung zeigen, wenn die Seite in der anderen Sprache ist als der Text geschrieben wurde
    language = (get_language() or "de")[:2]
    return bool(obj.source_lang) and language != obj.source_lang


# NEU: Preis als Stufe statt genauer Betrag (Preise ändern sich, Kinder/Erwachsene ...).
# Zahl = Stufe, damit man im Filter «höchstens bis ...» einfach mit <= vergleichen kann.
PRICE_LEVELS = [
    (0, _("Gratis")),
    (1, _("bis 10 €")),
    (2, _("10–20 €")),
    (3, _("20–30 €")),
    (4, _("30–50 €")),
    (5, _("50–100 €")),
    (6, _("über 100 €")),
]


class Activity(models.Model):
    STATUS_CHOICES = [
        ("published", _("Veröffentlicht")),
        ("draft", _("Entwurf")),
        ("review", _("In Prüfung")),  # NEU: als unangemessen gemeldet, ausgeblendet bis Admin prüft
        ("pending", _("Wartet auf Freigabe")),  # NEU: neu gesendet, erscheint erst, wenn der Admin sie freigibt
        ("returned", _("Zurückgeschickt")),     # NEU: der Admin hat sie zum Überarbeiten zurückgeschickt
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="activities")
    # NEU: bis zu 3 Kategorien pro Aktivität (n:m-Beziehung, Django legt dafür eine Zwischentabelle an)
    categories = models.ManyToManyField(Category, related_name="activities", verbose_name="Kategorien")
    location = models.ForeignKey(Location, on_delete=models.PROTECT)
    title = models.CharField(max_length=200)
    description = models.TextField()
    price_level = models.PositiveSmallIntegerField("Preis", choices=PRICE_LEVELS, default=0)
    duration_minutes = models.IntegerField(null=True, blank=True)
    event_date = models.DateField(null=True, blank=True)
    image = models.ImageField(upload_to="activities/", null=True, blank=True)
    # NEU: automatische Übersetzung (DeepL). source_lang = Sprache, in der es geschrieben wurde ("de"/"fr"),
    # die *_tr-Felder enthalten die Übersetzung in die andere Sprache.
    source_lang = models.CharField("Originalsprache", max_length=2, blank=True)
    title_tr = models.CharField("Name übersetzt", max_length=200, blank=True)
    description_tr = models.TextField("Beschreibung übersetzt", blank=True)
    hours_note_tr = models.TextField("Bemerkung übersetzt", blank=True)
    transport_note_tr = models.TextField("Anreise übersetzt", blank=True)
    # NEU: welcher Teil vom Titelbild zu sehen ist, wenn es zugeschnitten wird (CSS object-position, z.B. "50% 30%")
    image_position = models.CharField("Bildausschnitt", max_length=20, default="50% 50%")

    # NEU (Schritt 2 vom Formular: Kontakt und Öffnungszeiten)
    website = models.URLField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    # NEU: Öffnungszeiten pro Wochentag als JSON, z.B.
    # {"always_open": false, "days": {"mo": {"closed": false, "slots": [["09:00", "12:00"], ["14:00", "18:00"]]},
    #                                 "so": {"closed": true, "slots": []}}}
    # Tage, die fehlen, sind unbekannt. "always_open": true = 24/7 offen.
    opening_hours = models.JSONField("Öffnungszeiten", null=True, blank=True)
    # früher das freie Textfeld für die Öffnungszeiten, jetzt für Ausnahmen (Feiertage, Winter ...)
    hours_note = models.TextField("Bemerkung zu den Öffnungszeiten", blank=True)
    # NEU: Anreise von Hand (freiwillig). Haltestellen und Route kommen automatisch, siehe BusStop.
    transport_note = models.TextField("So kommst du hin", blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="published")
    # NEU: was der Admin beim Zurückschicken geschrieben hat (sieht nur die Person, die sie hinzugefügt hat)
    return_note = models.TextField("Grund fürs Zurückschicken", blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def is_open_at(self, moment):
        # NEU: ist die Aktivität zu diesem Zeitpunkt offen? True / False, None = keine Öffnungszeiten bekannt.
        # Zeiten über Mitternacht (z.B. Bar 18:00–02:00) zählen auch noch am nächsten Morgen.
        data = self.opening_hours
        if not data:
            return None
        if data.get("always_open"):
            return True
        days = data.get("days", {})
        codes = [code for code, _short, _name in WEEKDAYS]
        today = codes[moment.weekday()]
        yesterday = codes[(moment.weekday() - 1) % 7]
        now = moment.strftime("%H:%M")
        for start, end in days.get(today, {}).get("slots", []):
            if start < end and start <= now < end:
                return True
            if end <= start and now >= start:  # über Mitternacht, Teil vor Mitternacht
                return True
        for start, end in days.get(yesterday, {}).get("slots", []):
            if end <= start and now < end:     # über Mitternacht, Teil nach Mitternacht
                return True
        return False

    def opening_hours_lines(self):
        # Für die Anzeige: gleiche Zeiten an aufeinanderfolgenden Tagen zusammenfassen,
        # z.B. [{"days": "Mo–Fr", "text": "09:00–12:00, 14:00–18:00"}, {"days": "So", "text": "geschlossen"}]
        data = self.opening_hours
        if not data:
            return []
        if data.get("always_open"):
            return [{"days": _("Mo–So"), "text": _("24 Stunden offen")}]

        lines = []
        previous_index = None
        for index, (code, short, _name) in enumerate(WEEKDAYS):
            day = data.get("days", {}).get(code)
            if not day:
                previous_index = None  # unbekannter Tag unterbricht die Gruppe
                continue
            if day.get("closed"):
                text = _("geschlossen")
            else:
                text = ", ".join(f"{start}–{end}" for start, end in day.get("slots", []))
            if lines and previous_index == index - 1 and lines[-1]["text"] == text:
                lines[-1]["last"] = short  # gleich wie gestern: Gruppe verlängern
            else:
                lines.append({"first": short, "last": short, "text": text})
            previous_index = index

        return [
            {"days": line["first"] if line["first"] == line["last"] else f"{line['first']}–{line['last']}",
             "text": line["text"]}
            for line in lines
        ]

    # ---------- NEU: Texte in der gewählten Sprache (Übersetzung, wenn vorhanden) ----------
    def _pick(self, original, translated):
        return translated if shows_translation(self) and translated else original

    @property
    def display_title(self):
        return self._pick(self.title, self.title_tr)

    @property
    def display_description(self):
        return self._pick(self.description, self.description_tr)

    @property
    def display_hours_note(self):
        return self._pick(self.hours_note, self.hours_note_tr)

    @property
    def display_transport_note(self):
        return self._pick(self.transport_note, self.transport_note_tr)

    @property
    def is_translated(self):
        return shows_translation(self) and bool(self.description_tr or self.title_tr)

    def average_rating(self):
        avg = self.ratings.aggregate(models.Avg("rating"))["rating__avg"]
        return round(avg, 1) if avg else None


# NEU: weitere Fotos von Nutzern auf der Detailseite
class ActivityImage(models.Model):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name="images")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    image = models.ImageField(upload_to="activities/extra/")
    created_at = models.DateTimeField(auto_now_add=True)


# NEU: Bewertung (Sterne, Titel, Text)
class Rating(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name="ratings")
    rating = models.PositiveSmallIntegerField()  # 1 bis 5
    title = models.CharField(max_length=150, blank=True)
    text = models.TextField(blank=True)
    # NEU (wie bei Tripadvisor): wann war man dort
    visited_on = models.DateField(null=True, blank=True)  # nur Monat und Jahr zählen
    created_at = models.DateTimeField(auto_now_add=True)
    # NEU: automatische Übersetzung (wie bei Activity)
    source_lang = models.CharField("Originalsprache", max_length=2, blank=True)
    title_tr = models.CharField("Titel übersetzt", max_length=150, blank=True)
    text_tr = models.TextField("Text übersetzt", blank=True)

    class Meta:
        unique_together = ("user", "activity")  # eine Bewertung pro Person

    @property
    def display_title(self):
        return self.title_tr if shows_translation(self) and self.title_tr else self.title

    @property
    def display_text(self):
        return self.text_tr if shows_translation(self) and self.text_tr else self.text

    @property
    def is_translated(self):
        return shows_translation(self) and bool(self.text_tr or self.title_tr)


# NEU: Melden und Fehler melden
class Report(models.Model):
    REASON_CHOICES = [
        ("inappropriate", _("Unangemessen")),
        ("spam", _("Spam")),
        ("error", _("Fehler / falsche Info")),
        ("other", _("Anderes")),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name="reports")
    reason = models.CharField(max_length=30, choices=REASON_CHOICES)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=30, default="open")
    created_at = models.DateTimeField(auto_now_add=True)


# NEU: Favoriten
class Favorite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "activity")

# NEU: Inhalt von "Über mich" und "Kontakt" (gibt es nur einmal, Zeile mit id=1)
class SiteInfo(models.Model):
    name = models.CharField("Name", max_length=100, blank=True)
    tagline = models.CharField("Zeile unter dem Namen", max_length=150, blank=True,
                               default="Hat den Épinal Guide gebaut · Maturaarbeit 2026")
    photo = models.ImageField("Foto", upload_to="about/", null=True, blank=True)
    intro = models.CharField("Begrüssung", max_length=200, blank=True,
                             default="Hallo! Schön, dass du hier bist.")
    text = models.TextField("Text über mich", blank=True, default=(
        "Letzten Herbst war ich vier Wochen im Austausch in Épinal. Wie immer, wenn ich in eine neue Stadt komme, "
        "habe ich mich gefragt: Was kann man hier eigentlich unternehmen? Die Infos waren überall verstreut, "
        "oft nur auf Französisch, und die besten Tipps kannte man nur, wenn man jemanden gefragt hat.\n\n"
        "Daraus ist die Idee für diese Website entstanden. Hier sammle ich Aktivitäten, Orte und Tipps für Épinal, "
        "die man nach Kategorie, Preis und Datum filtern kann. Wer selbst einen guten Ort kennt, kann ihn hochladen "
        "und andere Orte bewerten.\n\n"
        "Programmiert habe ich alles selbst mit Python und Django, im Rahmen meiner Maturaarbeit."
    ))
    email = models.EmailField("E-Mail", blank=True)
    instagram = models.CharField("Instagram (ohne @)", max_length=60, blank=True)
    other_link = models.URLField("Weiterer Link (z.B. GitHub)", blank=True)

    class Meta:
        verbose_name = "Über mich / Kontakt"
        verbose_name_plural = "Über mich / Kontakt"

    def __str__(self):
        return "Über mich / Kontakt"

    @classmethod
    def load(cls):
        # Gibt immer dieselbe Zeile zurück und legt sie beim ersten Mal an
        info, _created = cls.objects.get_or_create(pk=1)
        return info


# NEU: Nachrichten aus dem Kontaktformular (im Admin lesbar)
class ContactMessage(models.Model):
    TOPIC_CHOICES = [
        ("question", _("Frage")),
        ("tip", _("Tipp für eine Aktivität")),
        ("problem", _("Problem mit der Website melden")),
        ("other", _("Anderes")),
    ]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=100)
    email = models.EmailField()
    topic = models.CharField(max_length=20, choices=TOPIC_CHOICES, default="question")
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_topic_display()} von {self.name}"


# NEU: Besucherzähler insgesamt (nur Zahlen, keine Namen oder IP-Adressen)
class VisitCounter(models.Model):
    visitors = models.PositiveIntegerField(default=0)    # wie viele verschiedene Personen insgesamt
    page_views = models.PositiveIntegerField(default=0)  # wie viele Seiten insgesamt aufgerufen

    class Meta:
        verbose_name = "Besucherzähler"
        verbose_name_plural = "Besucherzähler"

    def __str__(self):
        return f"{self.visitors} Besucher:innen, {self.page_views} Seitenaufrufe"

    @classmethod
    def load(cls):
        counter, _created = cls.objects.get_or_create(pk=1)
        return counter


# NEU: Bushaltestellen vom Imagine-Netz (Épinal) für «So kommst du hin».
# Kommen automatisch aus den offenen Fahrplandaten (GTFS), Befehl: python manage.py import_bus_stops
class BusStop(models.Model):
    name = models.CharField(max_length=150)
    latitude = models.FloatField()
    longitude = models.FloatField()
    # Linien, die hier halten, z.B. [{"name": "4", "color": "#FF0000", "text": "#FFFFFF"}]
    lines = models.JSONField(default=list)

    class Meta:
        verbose_name = "Bushaltestelle"
        verbose_name_plural = "Bushaltestellen"
        ordering = ["name"]

    def __str__(self):
        return self.name


# NEU: Mitteilungen an Nutzer:innen, z.B. «Deine Aktivität wurde freigegeben» oder «zurückgeschickt».
# Erscheinen bei der Glocke oben in der Navigation.
class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    text = models.TextField()
    text_fr = models.TextField(blank=True)  # NEU: gleiche Mitteilung auf Französisch
    link = models.CharField(max_length=255, blank=True)  # wohin ein Klick führt, z.B. zum Bearbeiten
    read = models.BooleanField("gelesen", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mitteilung"
        verbose_name_plural = "Mitteilungen"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username}: {self.text[:40]}"

    @property
    def display_text(self):
        # NEU: Text in der gewählten Sprache
        if self.text_fr and (get_language() or "").startswith("fr"):
            return self.text_fr
        return self.text
