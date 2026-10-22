# NEU: Bildausschnitt fürs Titelbild (Oktober 2026)
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("guide", "0022_uebersetzung_fr"),
    ]

    operations = [
        migrations.AddField(
            model_name="activity",
            name="image_position",
            field=models.CharField(default="50% 50%", max_length=20, verbose_name="Bildausschnitt"),
        ),
    ]
