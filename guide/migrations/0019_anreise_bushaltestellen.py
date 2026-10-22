# NEU: «So kommst du hin»: Feld für die Anreise und Bushaltestellen (Oktober 2026)
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("guide", "0018_andere_bei_essen"),
    ]

    operations = [
        migrations.AddField(
            model_name="activity",
            name="transport_note",
            field=models.TextField(blank=True, verbose_name="So kommst du hin"),
        ),
        migrations.CreateModel(
            name="BusStop",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=150)),
                ("latitude", models.FloatField()),
                ("longitude", models.FloatField()),
                ("lines", models.JSONField(default=list)),
            ],
            options={
                "verbose_name": "Bushaltestelle",
                "verbose_name_plural": "Bushaltestellen",
                "ordering": ["name"],
            },
        ),
    ]
