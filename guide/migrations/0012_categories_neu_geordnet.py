# Neue Kategorien und Reihenfolge (Oktober 2026):
# - umbenennen: "Parks & Natur" -> "Natur & Parks", "Museen & Kultur" -> "Kultur & Museen",
#   "Abenteuer & Indoor" -> "Spiel & Action" (Bowling, Escape Room, Lasertag ...)
# - zusammenlegen: "Essen & Restaurants" und "Cafés" -> "Essen & Trinken"
#   (Aktivitäten aus den alten Kategorien wandern in die neue, dann wird die alte gelöscht)
# - position: Reihenfolge im Filter und im Formular
# Als Migration statt von Hand im Admin, damit es beim Hosting auf dem Server genau gleich passiert.

from django.db import migrations

# (neuer Name, frühere Namen), in der gewünschten Reihenfolge
NEW_CATEGORIES = [
    ("Sport & Bewegung", []),
    ("Natur & Parks", ["Parks & Natur"]),
    ("Essen & Trinken", ["Essen & Restaurants", "Cafés"]),
    ("Kultur & Museen", ["Museen & Kultur"]),
    ("Jugendzentren & Vereine", []),
    ("Spiel & Action", ["Abenteuer & Indoor"]),
    ("Märkte & Einkaufen", []),
]


def reorder_categories(apps, schema_editor):
    Category = apps.get_model("guide", "Category")
    Activity = apps.get_model("guide", "Activity")

    for position, (name, old_names) in enumerate(NEW_CATEGORIES, start=1):
        category = Category.objects.filter(name=name).first()
        old = list(Category.objects.filter(name__in=old_names))

        if category is None:
            if old:
                category = old.pop(0)  # erste alte Kategorie wird umbenannt
                category.name = name
            else:
                category = Category(name=name)

        category.position = position
        category.save()

        # restliche alte Kategorien: Aktivitäten umhängen, dann löschen
        for leftover in old:
            Activity.objects.filter(category=leftover).update(category=category)
            leftover.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("guide", "0011_category_position"),
    ]

    operations = [
        # Rückwärts nichts tun: zusammengelegte Kategorien kann man nicht automatisch wieder trennen
        migrations.RunPython(reorder_categories, migrations.RunPython.noop),
    ]
