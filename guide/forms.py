import datetime

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _

from .models import WEEKDAYS, Activity, ActivityImage, Category, ContactMessage, Report, SiteInfo


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
            raise forms.ValidationError(_("Der Benutzername darf kein @ enthalten."))
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_("Diese E-Mail ist schon registriert."))
        return email


# ---------- NEU: Profil (Benutzername und E-Mail ändern) ----------
class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["username", "email"]
        labels = {"username": _("Benutzername"), "email": _("E-Mail")}
        help_texts = {"username": _("Bei Bewertungen erscheinen nur die ersten Buchstaben, z.B. fr***.")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"

    def clean_username(self):
        username = self.cleaned_data["username"]
        if "@" in username:  # gleiche Regel wie bei der Registrierung
            raise forms.ValidationError(_("Der Benutzername darf kein @ enthalten."))
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(_("Diese E-Mail ist schon registriert."))
        return email


class ActivityForm(forms.ModelForm):
    # Diese Felder gehören zur Location, nicht zur Activity.
    # Die Adresssuche (JavaScript in add_activity.html) füllt sie automatisch aus.
    address = forms.CharField(label=_("Adresse"), max_length=255, required=False)
    postal_code = forms.CharField(label=_("PLZ"), max_length=10, required=False)
    city = forms.CharField(label=_("Ort"), max_length=100, initial="Épinal")
    latitude = forms.DecimalField(max_digits=10, decimal_places=7, required=False, widget=forms.HiddenInput)
    longitude = forms.DecimalField(max_digits=10, decimal_places=7, required=False, widget=forms.HiddenInput)

    # Welche Felder zu Schritt 2 gehören (für die Fehleranzeige)
    STEP2_FIELDS = {"website", "phone", "email", "hours_note", "hours_always", "transport_note"} | {
        f"hours_{code}_{part}" for code, _short, _name in WEEKDAYS
        for part in ("closed", "open1", "close1", "open2", "close2")
    }

    class Meta:
        model = Activity
        fields = [
            "title", "description", "price_level", "duration_minutes",
            "event_date",
            "website", "phone", "email", "hours_note", "transport_note",
        ]
        labels = {
            "title": _("Name"),
            "description": _("Beschreibung"),
            "price_level": _("Preis"),
            "duration_minutes": _("Dauer in Minuten"),
            "event_date": _("Datum (nur bei Events)"),
            "website": _("Website"),
            "phone": _("Telefonnummer"),
            "email": _("E-Mail-Adresse"),
            "hours_note": _("Bemerkung"),
            "transport_note": _("So kommst du hin"),
        }
        help_texts = {
            "price_level": _("Ungefähr, pro Person."),
            "transport_note": _("Die nächsten Bushaltestellen und die Route zeigen wir automatisch an. "
                                "Schreib hier nur, was man sonst noch wissen muss."),
        }
        widgets = {
            "description": forms.Textarea(attrs={
                "rows": 4,
                "placeholder": _("Was kann man hier machen? Was ist speziell?"),  # hellgrauer Hinweis im leeren Feld
            }),
            "hours_note": forms.Textarea(attrs={
                "rows": 2,
                "placeholder": _("z.B. an Feiertagen geschlossen, im Winter nur bis 17:00"),
            }),
            "event_date": forms.DateInput(attrs={"type": "date"}),
            "price_level": forms.RadioSelect,  # als Knöpfe (siehe add_activity.html)
            "transport_note": forms.Textarea(attrs={
                "rows": 2,
                "placeholder": _("z.B. Eingang hinter dem Parkplatz, letzter Bus fährt um 20:00"),
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs["class"] = css
        self.setup_categories()
        self.setup_opening_hours()
        self.setup_photos()
        # NEU: Preis bei einer neuen Aktivität nicht vorwählen, man soll bewusst eine Stufe antippen
        self.fields["price_level"].error_messages["required"] = _("Bitte wähle einen Preis.")
        if not self.instance.pk:
            self.initial["price_level"] = None

    # ---------- NEU: mehrere Fotos auf einmal ----------
    def setup_photos(self):
        # Das erste Foto wird das Titelbild (Activity.image), die anderen kommen zu den Fotos (ActivityImage).
        # Foto ist zum Senden Pflicht, für einen Entwurf nicht (Prüfung in clean).
        # Darum nicht required=True (sonst ginge kein Entwurf ohne Foto), aber ohne «(optional)» anzeigen.
        self.fields["photos"] = MultipleImageField(
            label=_("Fotos"), required=False,
            help_text=_("Du kannst mehrmals Fotos auswählen (höchstens %(max)s auf einmal). "
                        "Mit «Als Titelbild» bestimmst du das Titelbild. Bitte nur eigene Fotos.") % {"max": MAX_PHOTOS},
        )
        self.fields["photos"].show_as_required = True
        # beim Bearbeiten: die vorhandenen Fotos mit Häkchen zum Entfernen
        self.existing_photos = []
        if self.instance.pk:
            if self.instance.image:
                self.existing_photos.append({"value": "cover", "url": self.instance.image.url, "cover": True})
            for photo in self.instance.images.filter(user=self.instance.user).order_by("created_at"):
                self.existing_photos.append({"value": str(photo.pk), "url": photo.image.url, "cover": False})
        self.fields["delete_photos"] = forms.MultipleChoiceField(
            required=False, choices=[(p["value"], p["value"]) for p in self.existing_photos],
        )
        # NEU: welches Foto das Titelbild ist ("new:2" = drittes neues Foto, "15" = vorhandenes Foto Nr. 15)
        # und welcher Ausschnitt davon zu sehen ist ("50% 30%"). Beides füllt das JavaScript aus.
        self.fields["cover_choice"] = forms.CharField(required=False, widget=forms.HiddenInput)
        self.fields["image_position"] = forms.RegexField(
            regex=r"^\d{1,3}(\.\d+)?% \d{1,3}(\.\d+)?%$", required=False, widget=forms.HiddenInput,
        )
        if self.instance.pk:
            self.initial["image_position"] = self.instance.image_position

    def clean_photos(self):
        return check_photos(self.cleaned_data["photos"])

    def save_photos(self, activity, user):
        # Nach dem Speichern der Aktivität aufrufen (die Fotos brauchen ihre id)
        delete = set(self.cleaned_data.get("delete_photos") or [])
        old_cover = activity.image.name if activity.image else ""
        if "cover" in delete:
            activity.image = None
        ActivityImage.objects.filter(activity=activity, user=activity.user,
                                     pk__in=[v for v in delete if v.isdigit()]).delete()
        new_photos = list(self.cleaned_data.get("photos") or [])

        def move_cover_to_photos():
            # bisheriges Titelbild bleibt als normales Foto erhalten
            if activity.image:
                ActivityImage.objects.create(activity=activity, user=activity.user, image=activity.image.name)

        # NEU: selbst gewähltes Titelbild
        choice = self.cleaned_data.get("cover_choice") or ""
        if choice.startswith("new:") and choice[4:].isdigit() and int(choice[4:]) < len(new_photos):
            move_cover_to_photos()
            activity.image = new_photos.pop(int(choice[4:]))
        elif choice.isdigit():
            chosen = activity.images.filter(pk=choice, user=activity.user).first()
            if chosen:
                move_cover_to_photos()
                activity.image = chosen.image.name
                chosen.delete()

        if not activity.image and new_photos:
            activity.image = new_photos.pop(0)  # sonst: erstes neues Foto = Titelbild
        for photo in new_photos:
            ActivityImage.objects.create(activity=activity, user=user, image=photo)
        if not activity.image:
            # Titelbild entfernt: das nächste eigene Foto wird Titelbild
            first = activity.images.filter(user=activity.user).order_by("created_at").first()
            if first:
                activity.image = first.image.name
                first.delete()

        # NEU: Bildausschnitt. Neues Titelbild ohne gewählten Ausschnitt: Mitte.
        position = self.cleaned_data.get("image_position")
        new_cover = (activity.image.name if activity.image else "") != old_cover
        if position:
            activity.image_position = position
        elif new_cover:
            activity.image_position = "50% 50%"
        activity.save(update_fields=["image", "image_position"])

    # ---------- NEU: Öffnungszeiten pro Wochentag ----------
    def setup_opening_hours(self):
        # Pro Tag: geschlossen (Häkchen), erste Zeit (open1-close1) und eine zweite nach einer Pause (open2-close2)
        self.fields["hours_always"] = forms.BooleanField(
            required=False, label=_("Immer offen (24/7)"),
            widget=forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
        )
        time_widget = {"type": "time", "class": "form-control form-control-sm hours-time"}
        for code, _short, name in WEEKDAYS:
            self.fields[f"hours_{code}_closed"] = forms.BooleanField(
                required=False, label=_("geschlossen"),
                widget=forms.CheckboxInput(attrs={"class": "form-check-input hours-closed"}),
            )
            for n in (1, 2):
                for part, label in (("open", _("von")), ("close", _("bis"))):
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
                        self.add_error(f"hours_{code}_open{n}", _("%(day)s: Beginn und Ende sind gleich.") % {"day": name})
                    # Ende vor Beginn ist erlaubt: geht über Mitternacht (z.B. Bar 18:00–02:00)
                    slots.append([start.strftime("%H:%M"), end.strftime("%H:%M")])
                elif start or end:
                    self.add_error(f"hours_{code}_open{n}", _("%(day)s: bitte Beginn und Ende angeben.") % {"day": name})
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
        # Bei «Genauer?» kann man mehrere antippen, z.B. Restaurant und Café.
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
        main_choices = [("", _("Kategorie wählen"))]
        main_choices += [(main.pk, main.display_name if main.approved else "%s (%s)" % (main.display_name, _("Vorschlag")))
                         for main in mains]
        main_choices += [("new", _("+ Keine passt? Eigene hinzufügen"))]

        for i in range(1, self.MAX_CATEGORIES + 1):
            self.fields[f"main_{i}"] = forms.ChoiceField(
                choices=main_choices,
                required=(i == 1),
                label=_("Kategorie") if i == 1 else _("%(n)s. Kategorie") % {"n": i},
                error_messages={"required": _("Bitte wähle eine Kategorie.")},
                widget=forms.Select(attrs={"class": "form-select cat-main-select"}),
            )
            self.fields[f"sub_{i}"] = forms.ModelMultipleChoiceField(
                queryset=Category.objects.filter(pk__in=sub_ids), required=False,
            )
            # NEU: eigener Vorschlag in dieser Zeile, wenn bei «Genauer?» «Eigene hinzufügen» gewählt ist
            self.fields[f"new_{i}"] = forms.CharField(
                label=_("Was fehlt?"), max_length=60, required=False,
                help_text=_("Wir schauen uns deinen Vorschlag an und nehmen ihn in die Liste auf."),
                widget=forms.TextInput(attrs={"class": "form-control", "placeholder": _("z.B. Rudern, Bäckerei …")}),
            )

        # beim Bearbeiten: gespeicherte Kategorien in die Zeilen eintragen,
        # Unterkategorien derselben Hauptkategorie zusammen in eine Zeile (z.B. Restaurant und Café)
        rows = {}  # Hauptkategorie -> Liste der gewählten Unterkategorien
        for category in current:
            rows.setdefault(category.parent_id or category.pk, [])
            if category.parent_id:
                rows[category.parent_id].append(category.pk)
        for i, (main_id, subs) in enumerate(list(rows.items())[:self.MAX_CATEGORIES], start=1):
            self.initial[f"main_{i}"] = main_id
            self.initial[f"sub_{i}"] = subs

    @property
    def category_rows(self):
        # für das Template: pro Zeile das Dropdown und was gewählt ist
        rows = []
        for i in range(1, self.MAX_CATEGORIES + 1):
            main_value = self[f"main_{i}"].value()
            sub_values = [str(v) for v in (self[f"sub_{i}"].value() or [])]
            rows.append({
                "i": i,
                "main": self[f"main_{i}"],
                "new": self[f"new_{i}"],
                "main_value": str(main_value) if main_value else "",
                "sub_values": sub_values,  # alle angetippten Unterkategorien (als Text)
                "hidden": i > 1 and not main_value,  # 2. und 3. Zeile erst nach Klick auf «Weitere Kategorie»
            })
        return rows

    def clean(self):
        cleaned = super().clean()
        # Ohne Koordinaten gehen Distanzfilter und Karte nicht, deshalb Pflicht
        if cleaned.get("latitude") is None or cleaned.get("longitude") is None:
            self.add_error("address", _("Bitte wähle eine Adresse aus den Vorschlägen oder klicke auf die Karte."))
        cleaned["opening_hours"] = self.build_opening_hours(cleaned)

        # NEU: Foto Pflicht beim Senden (Knopf «Als Entwurf speichern» heisst save_draft)
        if "save_draft" not in self.data:
            delete = set(cleaned.get("delete_photos") or [])
            kept = [p for p in self.existing_photos if p["value"] not in delete]
            if not cleaned.get("photos") and not kept and "photos" not in self.errors:
                self.add_error("photos", _("Bitte füge ein Foto hinzu, damit man sieht, wie es dort aussieht."))

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
                    self.add_error(f"new_{i}", _("Schreib kurz, was fehlt."))
                continue
            main = self.mains_by_id[value]
            # jede Hauptkategorie nur einmal (im Dropdown ist sie dann auch schon ausgegraut)
            if main.pk in chosen_mains:
                self.add_error(f"main_{i}", _("Diese Kategorie hast du schon gewählt."))
                continue
            chosen_mains.add(main.pk)
            # alle angetippten Unterkategorien dieser Hauptkategorie, keine angetippt = die Hauptkategorie allgemein
            subs = [sub for sub in (cleaned.get(f"sub_{i}") or []) if sub.parent_id == main.pk]
            for category in subs or [main]:
                if category not in categories:  # zweimal das Gleiche nur einmal speichern
                    categories.append(category)
                # Vorschlag nur verwenden, wenn in dieser Zeile wirklich «Eigene hinzufügen» (= «Andere») gewählt ist
                if category.name == "Andere":
                    if text:
                        suggestions.append((category.parent, text, category))
                    else:
                        self.add_error(f"new_{i}", _("Schreib kurz, was fehlt."))
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
    # Gemeinsame Prüfung für _("Fotos hinzufügen") und "Bewerten"
    if len(photos) > MAX_PHOTOS:
        raise forms.ValidationError(_("Höchstens %(max)s Fotos auf einmal.") % {"max": MAX_PHOTOS})
    for photo in photos:
        if photo.size > MAX_PHOTO_SIZE:
            raise forms.ValidationError(_("%(name)s ist grösser als 10 MB.") % {"name": photo.name})
    return photos


class PhotoForm(forms.Form):
    photos = MultipleImageField(label=_("Fotos auswählen"))

    def clean_photos(self):
        return check_photos(self.cleaned_data["photos"])



# ---------- NEU: Bewerten (wie bei Tripadvisor) ----------



def last_12_months():
    # [("2026-10", "Oktober 2026"), ("2026-09", "September 2026"), ...]
    today = datetime.date.today()
    year, month = today.year, today.month
    months = []
    for _i in range(12):
        # Monatsname in der gewählten Sprache (Oktober 2026 / octobre 2026)
        months.append((f"{year}-{month:02d}", date_format(datetime.date(year, month, 1), "F Y")))
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return months


class ReviewForm(forms.Form):
    # Reihenfolge hier = Reihenfolge im Formular
    rating = forms.TypedChoiceField(
        label=_("Wie würdest du deine Erfahrung bewerten?"),
        choices=[(i, i) for i in range(1, 6)],
        coerce=int,
        widget=forms.RadioSelect,
        error_messages={"required": _("Bitte wähle 1 bis 5 Sterne.")},
    )
    visited = forms.ChoiceField(label=_("Wann warst du dort?"))
    title = forms.CharField(
        label=_("Titel deiner Bewertung"),
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control",
                                      "placeholder": _("Wie würdest du deine Erfahrung zusammenfassen?")}),
    )
    text = forms.CharField(
        label=_("Schreib deine Bewertung"),
        required=False,  # freiwillig: Sterne und Titel reichen
        widget=forms.Textarea(attrs={"rows": 5, "class": "form-control",
                                     "placeholder": _("Teile deine Erfahrung ...")}),
    )
    photos = MultipleImageField(label=_("Fotos hinzufügen"), required=False)  # freiwillig
    confirm = forms.BooleanField(
        label=_("Ich bestätige, dass diese Bewertung auf meiner eigenen Erfahrung beruht und ehrlich ist."),
        error_messages={"required": _("Bitte bestätige das Kästchen.")},
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
            "reason": _("Grund"),
            "description": _("Was genau?"),
        }

    def __init__(self, *args, kind="report", **kwargs):
        super().__init__(*args, **kwargs)
        self.kind = kind
        if kind == "error":
            # Fehler melden: Grund ist immer "error", dafür muss man beschreiben, was falsch ist
            del self.fields["reason"]
            self.fields["description"].required = True
            self.fields["description"].label = _("Was ist falsch? (z.B. Adresse, Öffnungszeiten, Preis)")
        else:
            self.fields["reason"].choices = [
                (key, label) for key, label in Report.REASON_CHOICES if key in self.REPORT_REASONS
            ]
            self.fields["description"].label = _("Was genau? (freiwillig)")

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
            "text": _("Leere Zeile = neuer Absatz."),
            "email": _("Erscheint auf der Kontaktseite. Leer lassen, wenn du sie nicht zeigen willst."),
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
            "name": _("Dein Name"),
            "email": _("Deine E-Mail"),
            "topic": _("Worum geht es?"),
            "message": _("Nachricht"),
        }
        help_texts = {
            "email": _("Meine Antwort kommt per E-Mail an diese Adresse."),  # NEU
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
            raise forms.ValidationError(_("Spam erkannt."))
        return ""

