import datetime

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Activity, Category, ContactMessage, Report, SiteInfo


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

    # NEU: eigener Vorschlag, wenn bei der Kategorie "Andere" gewählt ist (z.B. eine Sportart, die fehlt)
    new_category = forms.CharField(
        label="Was genau?", max_length=60, required=False,
        help_text="Wir schauen deinen Vorschlag an und nehmen ihn dann in die Liste auf.",
        widget=forms.TextInput(attrs={"placeholder": "z.B. Rudern, Klettersteig …"}),
    )

    # Welche Felder zu Schritt 2 gehören (für die Fehleranzeige)
    STEP2_FIELDS = {"website", "phone", "email", "opening_hours"}

    class Meta:
        model = Activity
        fields = [
            "title", "category", "description", "price", "duration_minutes",
            "event_date", "image",
            "website", "phone", "email", "opening_hours",
        ]
        labels = {
            "title": "Name",
            "category": "Kategorie",
            "description": "Beschreibung",
            "price": "Preis in €",
            "duration_minutes": "Dauer in Minuten",
            "event_date": "Datum (nur bei Events)",
            "image": "Foto",
            "website": "Website",
            "phone": "Telefonnummer",
            "email": "E-Mail-Adresse",
            "opening_hours": "Öffnungszeiten",
        }
        help_texts = {
            "price": "0 = kostenlos",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "opening_hours": forms.Textarea(attrs={
                "rows": 4,
                "placeholder": "Mo–Fr: 9:00–18:00\nSa: 10:00–16:00",
            }),
            "event_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs["class"] = css
        self.setup_categories()
        self.fields["price"].initial = 0

    def setup_categories(self):
        # Kategorie-Auswahl mit Gruppen: pro Hauptkategorie eine Gruppe mit ihren Unterkategorien.
        # Hauptkategorien ohne Unterkategorien (z.B. Natur & Parks) wählt man direkt.
        field = self.fields["category"]
        current = self.instance.category if self.instance.category_id else None
        all_categories = list(Category.objects.order_by("position", "name"))

        choices = [("", "Kategorie wählen")]
        allowed = []
        for main in [c for c in all_categories if c.parent_id is None]:
            # Vorschläge (noch nicht freigegeben) nur zeigen, wenn diese Aktivität schon so eine hat
            subs = [c for c in all_categories if c.parent_id == main.pk and (c.approved or c == current)]
            if subs:
                choices.append((main.name, [(c.pk, c.name if c.approved else f"{c.name} (Vorschlag)") for c in subs]))
                allowed += [c.pk for c in subs]
            else:
                choices.append((main.pk, main.name))
                allowed.append(main.pk)

        # ältere Aktivität, die noch direkt in einer Hauptkategorie mit Unterkategorien ist: behalten können
        if current and current.pk not in allowed:
            choices.insert(1, (current.pk, current.name))
            allowed.append(current.pk)

        field.queryset = Category.objects.filter(pk__in=allowed)  # nur diese sind gültig
        field.choices = choices                                    # so werden sie angezeigt

    def clean(self):
        cleaned = super().clean()
        # Ohne Koordinaten gehen Distanzfilter und Karte nicht, deshalb Pflicht
        if cleaned.get("latitude") is None or cleaned.get("longitude") is None:
            self.add_error("address", "Bitte wähle eine Adresse aus den Vorschlägen oder klicke auf die Karte.")
        # Vorschlag nur verwenden, wenn wirklich "Andere" gewählt ist
        category = cleaned.get("category")
        if not (category and category.name == "Andere"):
            cleaned["new_category"] = ""
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

