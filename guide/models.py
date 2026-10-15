from django.db import models
from django.contrib.auth.models import User


class Category(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Location(models.Model):
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, default="Épinal")
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)

    def __str__(self):
        return f"{self.address}, {self.city}" if self.address else self.city


class Activity(models.Model):
    STATUS_CHOICES = [
        ("published", "Veröffentlicht"),
        ("draft", "Entwurf"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="activities")
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    location = models.ForeignKey(Location, on_delete=models.PROTECT)
    title = models.CharField(max_length=200)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    duration_minutes = models.IntegerField(null=True, blank=True)
    event_date = models.DateField(null=True, blank=True)
    image = models.ImageField(upload_to="activities/", null=True, blank=True)

    # NEU (Schritt 2 vom Formular: Kontakt und Öffnungszeiten)
    website = models.URLField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    opening_hours = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="published")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

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
    COMPANION_CHOICES = [
        ("business", "Geschäftlich"),
        ("couple", "Als Paar"),
        ("family", "Familie"),
        ("friends", "Mit Freunden"),
        ("solo", "Alleine"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name="ratings")
    rating = models.PositiveSmallIntegerField()  # 1 bis 5
    title = models.CharField(max_length=150, blank=True)
    text = models.TextField(blank=True)
    # NEU (wie bei Tripadvisor): wann und mit wem
    visited_on = models.DateField(null=True, blank=True)  # nur Monat und Jahr zählen
    companions = models.CharField(max_length=20, choices=COMPANION_CHOICES, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "activity")  # eine Bewertung pro Person


# NEU: Melden und Fehler melden
class Report(models.Model):
    REASON_CHOICES = [
        ("inappropriate", "Unangemessen"),
        ("spam", "Spam"),
        ("error", "Fehler / falsche Info"),
        ("other", "Anderes"),
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