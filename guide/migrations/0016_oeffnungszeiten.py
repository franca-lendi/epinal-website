# Öffnungszeiten pro Wochentag (Oktober 2026)
# - das bisherige Textfeld "opening_hours" heisst neu "hours_note" (Bemerkung, z.B. Feiertage).
#   So geht nichts verloren, was schon eingetragen ist.
# - neues Feld "opening_hours" (JSON) mit den Zeiten pro Tag, siehe Activity.opening_hours

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("guide", "0015_mehrere_kategorien"),
    ]

    operations = [
        migrations.RenameField(
            model_name="activity",
            old_name="opening_hours",
            new_name="hours_note",
        ),
        migrations.AlterField(
            model_name="activity",
            name="hours_note",
            field=models.TextField(blank=True, verbose_name="Bemerkung zu den Öffnungszeiten"),
        ),
        migrations.AddField(
            model_name="activity",
            name="opening_hours",
            field=models.JSONField(blank=True, null=True, verbose_name="Öffnungszeiten"),
        ),
    ]
