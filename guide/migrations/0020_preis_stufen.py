# NEU: Preis als Stufe (Gratis, bis 10 €, 10–20 € ... über 100 €) statt genauer Betrag (Oktober 2026)
# Bestehende Aktivitäten bekommen die passende Stufe zu ihrem alten Preis.
from decimal import Decimal

from django.db import migrations, models

# obere Grenze jeder Stufe (Stufe 6 = über 100 €)
LIMITS = [(0, Decimal(0)), (1, Decimal(10)), (2, Decimal(20)), (3, Decimal(30)), (4, Decimal(50)), (5, Decimal(100))]


def price_to_level(apps, schema_editor):
    Activity = apps.get_model("guide", "Activity")
    for activity in Activity.objects.all():
        level = 6
        for number, limit in LIMITS:
            if activity.price <= limit:
                level = number
                break
        Activity.objects.filter(pk=activity.pk).update(price_level=level)


def level_to_price(apps, schema_editor):
    # rückwärts: die obere Grenze der Stufe als Preis
    Activity = apps.get_model("guide", "Activity")
    limits = dict(LIMITS)
    for activity in Activity.objects.all():
        Activity.objects.filter(pk=activity.pk).update(price=limits.get(activity.price_level, Decimal(150)))


class Migration(migrations.Migration):

    dependencies = [
        ("guide", "0019_anreise_bushaltestellen"),
    ]

    operations = [
        migrations.AddField(
            model_name="activity",
            name="price_level",
            field=models.PositiveSmallIntegerField(
                choices=[(0, "Gratis"), (1, "bis 10 €"), (2, "10–20 €"), (3, "20–30 €"), (4, "30–50 €"),
                         (5, "50–100 €"), (6, "über 100 €")],
                default=0, verbose_name="Preis"),
        ),
        migrations.RunPython(price_to_level, level_to_price),
        migrations.RemoveField(
            model_name="activity",
            name="price",
        ),
    ]
