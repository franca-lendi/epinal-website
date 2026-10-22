# «Keine passt? Eigene hinzufügen» auch bei Essen & Trinken (Oktober 2026)
# Dahinter steckt wie bei Sport die Unterkategorie «Andere». Wer sie wählt, schreibt einen eigenen Vorschlag.

from django.db import migrations


def add_andere(apps, schema_editor):
    Category = apps.get_model("guide", "Category")
    essen = Category.objects.filter(name="Essen & Trinken", parent=None).first()
    if essen:
        andere, _ = Category.objects.get_or_create(name="Andere", parent=essen)
        andere.position = 99  # immer zuletzt
        andere.save()


def remove_andere(apps, schema_editor):
    Category = apps.get_model("guide", "Category")
    Category.objects.filter(name="Andere", parent__name="Essen & Trinken", activities__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("guide", "0017_status_wartet_auf_freigabe"),
    ]

    operations = [
        migrations.RunPython(add_andere, remove_andere),
    ]
