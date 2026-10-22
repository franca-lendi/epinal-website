# NEU: Zurückschicken (Status + Grund) und Mitteilungen an Nutzer:innen (Oktober 2026)
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("guide", "0020_preis_stufen"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="activity",
            name="status",
            field=models.CharField(
                choices=[("published", "Veröffentlicht"), ("draft", "Entwurf"), ("review", "In Prüfung"),
                         ("pending", "Wartet auf Freigabe"), ("returned", "Zurückgeschickt")],
                default="published", max_length=20),
        ),
        migrations.AddField(
            model_name="activity",
            name="return_note",
            field=models.TextField(blank=True, verbose_name="Grund fürs Zurückschicken"),
        ),
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("text", models.TextField()),
                ("link", models.CharField(blank=True, max_length=255)),
                ("read", models.BooleanField(default=False, verbose_name="gelesen")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications",
                                           to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Mitteilung",
                "verbose_name_plural": "Mitteilungen",
                "ordering": ["-created_at"],
            },
        ),
    ]
