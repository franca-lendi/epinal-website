from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Activity


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