import datetime

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Activity, Rating, Report


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Diese E-Mail ist schon registriert.")
        return email


class ActivityForm(forms.ModelForm):
    # Diese zwei Felder gehören zur Location, nicht zur Activity
    address = forms.CharField(label="Adresse", max_length=255)
    city = forms.CharField(label="Ort", max_length=100, initial="Épinal")

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
        self.fields["category"].empty_label = "Kategorie wählen"
        self.fields["price"].initial = 0


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
    rating = forms.TypedChoiceField(
        label="Wie würdest du deine Erfahrung bewerten?",
        choices=[(i, i) for i in range(1, 6)],
        coerce=int,
        widget=forms.RadioSelect,
        error_messages={"required": "Bitte wähle 1 bis 5 Punkte."},
    )
    visited = forms.ChoiceField(label="Wann warst du dort?")
    companions = forms.ChoiceField(
        label="Mit wem warst du dort?",
        choices=Rating.COMPANION_CHOICES,
        widget=forms.RadioSelect,
        required=False,
    )
    text = forms.CharField(
        label="Schreib deine Bewertung",
        min_length=25,
        widget=forms.Textarea(attrs={"rows": 5, "class": "form-control",
                                     "placeholder": "Teile deine Erfahrung ..."}),
        error_messages={"min_length": "Bitte schreib mindestens 25 Zeichen."},
    )
    title = forms.CharField(
        label="Titel deiner Bewertung",
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control",
                                      "placeholder": "Wie würdest du deine Erfahrung zusammenfassen?"}),
    )
    confirm = forms.BooleanField(
        label="Ich bestätige, dass diese Bewertung auf meiner eigenen Erfahrung beruht und ehrlich ist.",
        error_messages={"required": "Bitte bestätige das Kästchen."},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["visited"].choices = last_12_months()
        self.fields["visited"].widget.attrs["class"] = "form-select w-auto"

    def visited_date(self):
        year, month = self.cleaned_data["visited"].split("-")
        return datetime.date(int(year), int(month), 1)


# ---------- NEU: Fotos hinzufügen (mehrere auf einmal) ----------

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    # So erlaubt Django mehrere Dateien in einem Feld (Beispiel aus der Django-Doku)
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={"class": "form-control", "accept": "image/*"}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_clean(d, initial) for d in data]
        return [single_clean(data, initial)]


MAX_PHOTOS = 10
MAX_PHOTO_SIZE = 10 * 1024 * 1024  # 10 MB


class PhotoForm(forms.Form):
    photos = MultipleImageField(label="Fotos auswählen")

    def clean_photos(self):
        photos = self.cleaned_data["photos"]
        if len(photos) > MAX_PHOTOS:
            raise forms.ValidationError(f"Höchstens {MAX_PHOTOS} Fotos auf einmal.")
        for photo in photos:
            if photo.size > MAX_PHOTO_SIZE:
                raise forms.ValidationError(f"{photo.name} ist grösser als 10 MB.")
        return photos


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

