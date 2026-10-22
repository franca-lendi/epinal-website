# NEU: Übersetzung DE/FR (Oktober 2026)
# - Kategorien bekommen einen französischen Namen
# - Mitteilungen werden in beiden Sprachen gespeichert
from django.db import migrations, models

NAMES_FR = {
    'Sport & Bewegung': 'Sport & activité physique',
    'Natur & Parks': 'Nature & parcs',
    'Essen & Trinken': 'Manger & boire',
    'Ausgang & Nightlife': 'Sorties & vie nocturne',
    'Kultur & Museen': 'Culture & musées',
    'Jugendzentren & Vereine': 'Maisons des jeunes & associations',
    'Spiel & Action': 'Jeux & action',
    'Märkte & Einkaufen': 'Marchés & shopping',
    'Fussball': 'Football',
    'Basketball': 'Basketball',
    'Klettern': 'Escalade',
    'Schwimmen': 'Natation',
    'Velo & Bike': 'Vélo & VTT',
    'Laufen': 'Course à pied',
    'Fitness': 'Fitness',
    'Skaten': 'Skate',
    'Tennis & Padel': 'Tennis & padel',
    'Andere': 'Autre',
    'Restaurant': 'Restaurant',
    'Café': 'Café',
    'Bar': 'Bar',
    'Imbiss & Takeaway': 'Snack & à emporter',
}


def add_french_names(apps, schema_editor):
    Category = apps.get_model("guide", "Category")
    for name, name_fr in NAMES_FR.items():
        Category.objects.filter(name=name, name_fr="").update(name_fr=name_fr)


class Migration(migrations.Migration):

    dependencies = [
        ("guide", "0021_zurueckschicken_mitteilungen"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="name_fr",
            field=models.CharField(blank=True, max_length=100, verbose_name="Name auf Französisch"),
        ),
        migrations.AddField(
            model_name="notification",
            name="text_fr",
            field=models.TextField(blank=True),
        ),
        migrations.RunPython(add_french_names, migrations.RunPython.noop),
    ]
