# NEU: automatische Übersetzung von Beschreibungen und Bewertungen (DeepL), Oktober 2026
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("guide", "0023_bildausschnitt"),
    ]

    operations = [
        migrations.AddField(model_name="activity", name="source_lang",
                            field=models.CharField(blank=True, max_length=2, verbose_name="Originalsprache")),
        migrations.AddField(model_name="activity", name="title_tr",
                            field=models.CharField(blank=True, max_length=200, verbose_name="Name übersetzt")),
        migrations.AddField(model_name="activity", name="description_tr",
                            field=models.TextField(blank=True, verbose_name="Beschreibung übersetzt")),
        migrations.AddField(model_name="activity", name="hours_note_tr",
                            field=models.TextField(blank=True, verbose_name="Bemerkung übersetzt")),
        migrations.AddField(model_name="activity", name="transport_note_tr",
                            field=models.TextField(blank=True, verbose_name="Anreise übersetzt")),
        migrations.AddField(model_name="rating", name="source_lang",
                            field=models.CharField(blank=True, max_length=2, verbose_name="Originalsprache")),
        migrations.AddField(model_name="rating", name="title_tr",
                            field=models.CharField(blank=True, max_length=150, verbose_name="Titel übersetzt")),
        migrations.AddField(model_name="rating", name="text_tr",
                            field=models.TextField(blank=True, verbose_name="Text übersetzt")),
    ]
