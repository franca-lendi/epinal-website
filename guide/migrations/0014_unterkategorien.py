# Unterkategorien und neue Hauptkategorie "Ausgang & Nightlife" (Oktober 2026)
# - Sport & Bewegung: feste Liste + "Andere" (dort kann man eine fehlende Sportart vorschlagen)
# - Essen & Trinken: Restaurant, Café, Bar, Imbiss & Takeaway
# - Ausgang & Nightlife: eigene Hauptkategorie (Clubs, Konzerte, Partys), gleich nach Essen & Trinken
# Als Migration, damit es beim Hosting auf dem Server genau gleich passiert.

from django.db import migrations

MAIN_ORDER = [
    "Sport & Bewegung",
    "Natur & Parks",
    "Essen & Trinken",
    "Ausgang & Nightlife",  # neu
    "Kultur & Museen",
    "Jugendzentren & Vereine",
    "Spiel & Action",
    "Märkte & Einkaufen",
]

SUBCATEGORIES = {
    "Sport & Bewegung": [
        "Fussball", "Basketball", "Klettern", "Schwimmen", "Velo & Bike",
        "Laufen", "Fitness", "Skaten", "Tennis & Padel", "Andere",
    ],
    "Essen & Trinken": ["Restaurant", "Café", "Bar", "Imbiss & Takeaway"],
}


def add_subcategories(apps, schema_editor):
    Category = apps.get_model("guide", "Category")

    Category.objects.get_or_create(name="Ausgang & Nightlife", parent=None)
    for position, name in enumerate(MAIN_ORDER, start=1):
        Category.objects.filter(name=name, parent=None).update(position=position)

    for main_name, subs in SUBCATEGORIES.items():
        main = Category.objects.filter(name=main_name, parent=None).first()
        if main is None:
            continue
        for position, name in enumerate(subs, start=1):
            sub, _ = Category.objects.get_or_create(name=name, parent=main)
            sub.position = 99 if name == "Andere" else position  # "Andere" immer zuletzt
            sub.save()


def remove_subcategories(apps, schema_editor):
    Category = apps.get_model("guide", "Category")
    # nur Unterkategorien ohne Aktivitäten löschen
    Category.objects.filter(parent__isnull=False, activity__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("guide", "0013_category_parent_approved"),
    ]

    operations = [
        migrations.RunPython(add_subcategories, remove_subcategories),
    ]
