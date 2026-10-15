# Legt die Kategorien aus der Recherche an (Meine Uploads.docx).
# Bestehende Kategorien mit gleichem Namen werden nicht doppelt erstellt.

from django.db import migrations

CATEGORIES = [
    "Sport & Bewegung",
    "Abenteuer & Indoor",
    "Parks & Natur",
    "Museen & Kultur",
    "Cafés",
    "Essen & Restaurants",
    "Märkte & Einkaufen",
    "Jugendzentren & Vereine",
]


def add_categories(apps, schema_editor):
    Category = apps.get_model("guide", "Category")
    for name in CATEGORIES:
        Category.objects.get_or_create(name=name)


def remove_categories(apps, schema_editor):
    Category = apps.get_model("guide", "Category")
    # nur löschen, wenn keine Aktivität mehr daran hängt
    Category.objects.filter(name__in=CATEGORIES, activity__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("guide", "0003_rating_visited_on_companions"),
    ]

    operations = [
        migrations.RunPython(add_categories, remove_categories),
    ]
