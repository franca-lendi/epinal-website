import datetime

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import WEEKDAYS, Activity, Category, ContactMessage, Report, SiteInfo


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"

    def clean_username(self):
        username = self.cleaned_data["username"]
        # Kein @ im Benutzernamen, sonst könnte man ihn beim Login mit einer E-Mail verwechseln
        if "@" in username:
            raise forms.ValidationError("Der Benutzername darf kein @ enthalten.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Diese E-Mail ist schon registriert.")
        return email


class ActivityForm(forms.ModelForm):
    # Diese Felder gehören zur Location, nicht zur Activity.
    # Die Adresssuche (JavaScript in add_activity.html) füllt sie automatisch aus.
    address = forms.CharField(label="Adresse", max_length=255, required=False)
    postal_code = forms.CharField(label="PLZ", max_length=10, required=False)
    city = forms.CharField(label="Ort", max_length=100, initial="Épinal")
    latitude = forms.DecimalField(max_digits=10, decimal_places=7, required=False, widget=forms.HiddenInput)
    longitude = forms.DecimalField(max_digits=10, decimal_places=7, required=False, widget=forms.HiddenInput)

    # Welche Felder zu Schritt 2 gehören (für die Fehleranzeige)
    STEP2_FIELDS = {"website", "phone", "email", "hours_note", "hours_always"} | {
        f"hours_{code}_{part}" for code, _, _ in WEEKDAYS
        for part in ("closed", "open1", "close1", "open2", "close2")
    }

    class Meta:
        model = Activity
        fields = [
            "title", "description", "price", "duration_minutes",
            "event_date", "image",
            "website", "phone", "email", "hours_note",
        ]
        labels = {
            "title": "Name",
            "description": "Beschreibung",
            "price": "Preis in €",
            "duration_minutes": "Dauer in Minuten",
            "event_date": "Datum (nur bei Events)",
            "image": "Foto",
            "website": "Website",
            "phone": "Telefonnummer",
            "email": "E-Mail-Adresse",
            "hours_note": "Bemerkung",
        }
        help_texts = {
            "price": "0 = kostenlos",
        }
        widgets = {
            "description": forms.Textarea(attrs={
                "rows": 4,
                "placeholder": "Was kann man hier machen? Was ist speziell?",  # hellgrauer Hinweis im leeren Feld
            }),
            "hours_note": forms.Textarea(attrs={
                "rows": 2,
                "placeholder": "z.B. an Feiertagen geschlossen, im Winter nur bis 17:00",
            }),
            "event_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs["class"] = css
        self.setup_categories()
        self.setup_opening_hours()
        self.fields["price"].initial = 0
        # NEU: Foto ist zum Senden Pflicht, für einen Entwurf nicht (Prüfung in clean).
        # Darum nicht required=True (sonst ginge kein Entwurf ohne Foto), aber ohne «(optional)» anzeigen.
        self.fields["image"].show_as_required = True
        self.fields["image"].help_text = "Bitte nur eigene Fotos. Für einen Entwurf kannst du es auch später hinzufügen."

    # ---------- NEU: Öffnungszeiten pro Wochentag ----------
    def setup_opening_hours(self):
        # Pro Tag: geschlossen (Häkchen), erste Zeit (open1-close1) und eine zweite nach einer Pause (open2-close2)
        self.fields["hours_always"] = forms.BooleanField(
            required=False, label="Immer offen (24/7)",
            widget=forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
        )
        time_widget = {"type": "time", "class": "form-control form-control-sm hours-time"}
        for code, _short, name in WEEKDAYS:
            self.fields[f"hours_{code}_closed"] = forms.BooleanField(
                required=False, label="geschlossen",
                widget=forms.CheckboxInput(attrs={"class": "form-check-input hours-closed"}),
            )
            for n in (1, 2):
                for part, label in (("open", "von"), ("close", "bis")):
                    self.fields[f"hours_{code}_{part}{n}"] = forms.TimeField(
                        required=False, label=f"{name} {label}",
                        widget=forms.TimeInput(attrs=time_widget, format="%H:%M"),
                    )

        # beim Bearbeiten: gespeicherte Zeiten eintragen
        data = self.instance.opening_hours or {}
        self.initial["hours_always"] = data.get("always_open", False)
        for code, day in data.get("days", {}).items():
            self.initial[f"hours_{code}_closed"] = day.get("closed", False)
            for n, (start, end) in enumerate(day.get("slots", [])[:2], start=1):
                self.initial[f"hours_{code}_open{n}"] = start
                self.initial[f"hours_{code}_close{n}"] = end

    @property
    def hours_days(self):
        # für das Template: pro Wochentag die Felder
        days = []
        for code, short, name in WEEKDAYS:
            fields = {part: self[f"hours_{code}_{part}"] for part in ("closed", "open1", "close1", "open2", "close2")}
            days.append({
                "code": code,
                "name": name,
                **fields,
                "has_pause": bool(fields["open2"].value() or fields["close2"].value()),
                "errors": [e for f in fields.values() for e in f.errors],
            })
        return days

    def build_opening_hours(self, cleaned):
        # Aus den Feldern das JSON für das Model bauen (siehe Activity.opening_hours)
        if cleaned.get("hours_always"):
            return {"always_open": True, "days": {}}
        days = {}
        for code, _short, name in WEEKDAYS:
            if cleaned.get(f"hours_{code}_closed"):
                days[code] = {"closed": True, "slots": []}
                continue
            slots = []
            for n in (1, 2):
                start = cleaned.get(f"hours_{code}_open{n}")
                end = cleaned.get(f"hours_{code}_close{n}")
                if start and end:
                    if start == end:
                        self.add_error(f"hours_{code}_open{n}", f"{name}: Beginn und Ende sind gleich.")
                    # Ende vor Beginn ist erlaubt: geht über Mitternacht (z.B. Bar 18:00–02:00)
                    slots.append([start.strftime("%H:%M"), end.strftime("%H:%M")])
                elif start or end:
                    self.add_error(f"hours_{code}_open{n}", f"{name}: bitte Beginn und Ende angeben.")
            if slots:
                days[code] = {"closed": False, "slots": slots}
        return {"always_open": False, "days": days} if days else None

    def save(self, commit=True):
        # Öffnungszeiten sind kein normales Formularfeld: hier ins Model schreiben
        self.instance.opening_hours = self.cleaned_data.get("opening_hours")
        return super().save(commit)

    MAX_CATEGORIES = 3

    def setup_categories(self):
        # Bis zu 3 Kategorien. Pro Kategorie: Hauptkategorie im Dropdown (main_1, main_2, main_3),
        # danach «Genauer?» mit den Unterkategorien dieser Hauptkategorie (sub_1, sub_2, sub_3, freiwillig).
        current = list(self.instance.categories.select_related("parent")) if self.instance.pk else []
        all_categories = list(Category.objects.order_by("position", "name"))
        current_mains = {c.parent_id or c.pk for c in current}
        # Vorschläge (noch nicht freigegeben) nur zeigen, wenn diese Aktivität schon so einen hat
        mains = [c for c in all_categories if c.parent_id is None and (c.approved or c.pk in current_mains)]
        for main in mains:
            main.subs = [c for c in all_categories if c.parent_id == main.pk and (c.approved or c in current)]
        self.category_tree = mains
        self.mains_by_id = {str(main.pk): main for main in mains}
        sub_ids = [sub.pk for main in mains for sub in main.subs]

        # Dropdown: alle Hauptkategorien, zuletzt «Keine passt? Eigene hinzufügen» (Wert "new")
        main_choices = [("", "Kategorie wählen")]
        main_choices += [(main.pk, main.name if main.approved else f"{main.name} (Vorschlag)") for main in mains]
        main_choices += [("new", "+ Keine passt? Eigene hinzufügen")]

        for i in range(1, self.MAX_CATEGORIES + 1):
            self.fields[f"main_{i}"] = forms.ChoiceField(
                choices=main_choices,
                required=(i == 1),
                label="Kategorie" if i == 1 else f"{i}. Kategorie",
                error_messages={"required": "Bitte wähle eine Kategorie."},
                widget=forms.Select(attrs={"class": "form-select cat-main-select"}),
            )
            self.fields[f"sub_{i}"] = forms.ModelChoiceField(
                queryset=Category.objects.filter(pk__in=sub_ids), required=False,
            )
            # NEU: eigener Vorschlag in dieser Zeile, wenn bei «Genauer?» «Eigene hinzufügen» gewählt ist
            self.fields[f"new_{i}"] = forms.CharField(
                label="Was fehlt?", max_length=60, required=False,
                help_text="Wir schauen uns deinen Vorschlag an und nehmen ihn in die Liste auf.",
                widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "z.B. Rudern, Bäckerei …"}),
            )

        # beim Bearbeiten: gespeicherte Kategorien in die Zeilen eintragen
        for i, category in enumerate(current[:self.MAX_CATEGORIES], start=1):
            if category.parent_id:
                self.initial[f"main_{i}"] = category.parent_id
                self.initial[f"sub_{i}"] = category.pk
            else:
                self.initial[f"main_{i}"] = category.pk

    @property
    def category_rows(self):
        # für das Template: pro Zeile das Dropdown und was gewählt ist
        rows = []
        for i in range(1, self.MAX_CATEGORIES + 1):
            main_value = self[f"main_{i}"].value()
            sub_value = self[f"sub_{i}"].value()
            rows.append({
                "i": i,
                "main": self[f"main_{i}"],
                "new": self[f"new_{i}"],
                "main_value": str(main_value) if main_value else "",
                "sub_value": str(sub_value) if sub_value else "",
                "hidden": i > 1 and not main_value,  # 2. und 3. Zeile erst nach Klick auf «Weitere Kategorie»
            })
        return rows

    def clean(self):
        cleaned = super().clean()
        # Ohne Koordinaten gehen Distanzfilter und Karte nicht, deshalb Pflicht
        if cleaned.get("latitude") is None or cleaned.get("longitude") is None:
            self.add_error("address", "Bitte wähle eine Adresse aus den Vorschlägen oder klicke auf die Karte.")
        cleaned["opening_hours"] = self.build_opening_hours(cleaned)

        # NEU: Foto Pflicht beim Senden (Knopf «Als Entwurf speichern» heisst save_draft)
        if "save_draft" not in self.data:
            image = cleaned.get("image")  # neue Datei, None = nichts geändert, False = gelöscht
            has_photo = bool(image) or (image is None and bool(self.instance.image))
            if not has_photo:
                self.add_error("image", "Bitte füge ein Foto hinzu, damit man sieht, wie es dort aussieht.")

        # Kategorien aus den Zeilen zusammensetzen: Unterkategorie, wenn gewählt, sonst die Hauptkategorie
        categories = []
        suggestions = []  # (Hauptkategorie oder None, eingetippter Vorschlag, Kategorie, die er ersetzt)
        chosen_mains = set()
        for i in range(1, self.MAX_CATEGORIES + 1):
            value = cleaned.get(f"main_{i}")
            if not value:
                continue
            text = (cleaned.get(f"new_{i}") or "").strip()
            if value == "new":
                # «Keine passt? Eigene hinzufügen» im Dropdown: Vorschlag für eine neue Hauptkategorie
                if text:
                    suggestions.append((None, text, None))
                else:
                    self.add_error(f"new_{i}", "Schreib kurz, was fehlt.")
                continue
            main = self.mains_by_id[value]
            # jede Hauptkategorie nur einmal (im Dropdown ist sie dann auch schon ausgegraut)
            if main.pk in chosen_mains:
                self.add_error(f"main_{i}", "Diese Kategorie hast du schon gewählt.")
                continue
            chosen_mains.add(main.pk)
            sub = cleaned.get(f"sub_{i}")
            category = sub if sub and sub.parent_id == main.pk else main
            if category not in categories:  # zweimal das Gleiche nur einmal speichern
                categories.append(category)
            # Vorschlag nur verwenden, wenn in dieser Zeile wirklich «Eigene hinzufügen» (= «Andere») gewählt ist
            if category.name == "Andere":
                if text:
                    suggestions.append((category.parent, text, category))
                else:
                    self.add_error(f"new_{i}", "Schreib kurz, was fehlt.")
        cleaned["categories"] = categories
        cleaned["suggestions"] = suggestions
        return cleaned


# ---------- NEU: Fotos hinzufügen (mehrere auf einmal) ----------

MAX_PHOTOS = 10
MAX_PHOTO_SIZE = 10 * 1024 * 1024  # 10 MB


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    # So erlaubt Django mehrere Dateien in einem Feld (Beispiel aus der Django-Doku)
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={"class": "form-control", "accept": "image/*"}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_clean = super().clean
        if not data:  # keine Datei ausgewählt
            if self.required:
                raise forms.ValidationError(self.error_messages["required"], code="required")
            return []
        if isinstance(data, (list, tuple)):
            return [single_clean(d, initial) for d in data]
        return [single_clean(data, initial)]


def check_photos(photos):
    # Gemeinsame Prüfung für "Fotos hinzufügen" und "Bewerten"
    if len(photos) > MAX_PHOTOS:
        raise forms.ValidationError(f"Höchstens {MAX_PHOTOS} Fotos auf einmal.")
    for photo in photos:
        if photo.size > MAX_PHOTO_SIZE:
            raise forms.ValidationError(f"{photo.name} ist grösser als 10 MB.")
    return photos


class PhotoForm(forms.Form):
    photos = MultipleImageField(label="Fotos auswählen")

    def clean_photos(self):
        return check_photos(self.cleaned_data["photos"])



# ---------- NEU: Bewerten (wie bei Tripadvisor) ----------

GERMAN_MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni",
                 "Juli", "August", "September", "Oktober", "November", "Dezember"]


def last_12_months():
    # [("2026-10", "Oktober 2026"), ("2026-09", "September 2026"), ...]
    today = datetime.date.today()
    year, month = today.year, today.month
    months = []
    for _ in range(12):
        months.append((f"{year}-{month:02d}", f"{GERMAN_MONTHS[month - 1]} {year}"))
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return months


class ReviewForm(forms.Form):
    # Reihenfolge hier = Reihenfolge im Formular
    rating = forms.TypedChoiceField(
        label="Wie würdest du deine Erfahrung bewerten?",
        choices=[(i, i) for i in range(1, 6)],
        coerce=int,
        widget=forms.RadioSelect,
        error_messages={"required": "Bitte wähle 1 bis 5 Sterne."},
    )
    visited = forms.ChoiceField(label="Wann warst du dort?")
    title = forms.CharField(
        label="Titel deiner Bewertung",
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control",
                                      "placeholder": "Wie würdest du deine Erfahrung zusammenfassen?"}),
    )
    text = forms.CharField(
        label="Schreib deine Bewertung",
        required=False,  # freiwillig: Sterne und Titel reichen
        widget=forms.Textarea(attrs={"rows": 5, "class": "form-control",
                                     "placeholder": "Teile deine Erfahrung ..."}),
    )
    photos = MultipleImageField(label="Fotos hinzufügen", required=False)  # freiwillig
    confirm = forms.BooleanField(
        label="Ich bestätige, dass diese Bewertung auf meiner eigenen Erfahrung beruht und ehrlich ist.",
        error_messages={"required": "Bitte bestätige das Kästchen."},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["visited"].choices = last_12_months()
        self.fields["visited"].widget.attrs["class"] = "form-select w-auto"

    def clean_photos(self):
        return check_photos(self.cleaned_data["photos"])

    def visited_date(self):
        year, month = self.cleaned_data["visited"].split("-")
        return datetime.date(int(year), int(month), 1)


# ---------- NEU: Melden und Fehler melden ----------

class ReportForm(forms.ModelForm):
    # "report" = Melden (unangemessen, Spam, anderes), "error" = Fehler melden
    REPORT_REASONS = ["inappropriate", "spam", "other"]

    class Meta:
        model = Report
        fields = ["reason", "description"]
        widgets = {
            "reason": forms.RadioSelect(attrs={"class": "form-check-input"}),
            "description": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        }
        labels = {
            "reason": "Grund",
            "description": "Was genau?",
        }

    def __init__(self, *args, kind="report", **kwargs):
        super().__init__(*args, **kwargs)
        self.kind = kind
        if kind == "error":
            # Fehler melden: Grund ist immer "error", dafür muss man beschreiben, was falsch ist
            del self.fields["reason"]
            self.fields["description"].required = True
            self.fields["description"].label = "Was ist falsch? (z.B. Adresse, Öffnungszeiten, Preis)"
        else:
            self.fields["reason"].choices = [
                (key, label) for key, label in Report.REASON_CHOICES if key in self.REPORT_REASONS
            ]
            self.fields["description"].label = "Was genau? (freiwillig)"

    def save(self, commit=True):
        if self.kind == "error":
            self.instance.reason = "error"
        return super().save(commit)


# ---------- NEU: Über mich bearbeiten (nur Admin) ----------

class SiteInfoForm(forms.ModelForm):
    class Meta:
        model = SiteInfo
        fields = ["photo", "name", "tagline", "intro", "text", "email", "instagram", "other_link"]
        widgets = {
            "photo": forms.FileInput(attrs={"accept": "image/*"}),
            "text": forms.Textarea(attrs={"rows": 10}),
        }
        help_texts = {
            "text": "Leere Zeile = neuer Absatz.",
            "email": "Erscheint auf der Kontaktseite. Leer lassen, wenn du sie nicht zeigen willst.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


# ---------- NEU: Kontaktformular ----------

class ContactForm(forms.ModelForm):
    # Unsichtbares Feld gegen Spam-Roboter: Menschen sehen es nicht, Roboter füllen es aus
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))

    class Meta:
        model = ContactMessage
        fields = ["name", "email", "topic", "message"]
        labels = {
            "name": "Dein Name",
            "email": "Deine E-Mail",
            "topic": "Worum geht es?",
            "message": "Nachricht",
        }
        widgets = {
            "message": forms.Textarea(attrs={"rows": 6}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            css = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.setdefault("class", css)

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError("Spam erkannt.")
        return ""

