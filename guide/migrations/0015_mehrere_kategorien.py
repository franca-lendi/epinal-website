# Bis zu 3 Kategorien pro Aktivität (Oktober 2026)
# Vorher: Activity.category (eine Kategorie, Fremdschlüssel)
# Neu:    Activity.categories (mehrere, n:m mit Zwischentabelle guide_activity_categories)
# Reihenfolge wichtig: zuerst das neue Feld anlegen, dann die bisherige Kategorie hinüberkopieren,
# erst danach das alte Feld löschen. Sonst wären die Kategorien der bestehenden Aktivitäten weg.

from django.db import migrations, models


def copy_category(apps, schema_editor):
    Activity = apps.get_model("guide", "Activity")
    for activity in Activity.objects.all():
        activity.categories.add(activity.category_id)


class Migration(migrations.Migration):

    dependencies = [
        ("guide", "0014_unterkategorien"),
    ]

    operations = [
        migrations.AddField(
            model_name="activity",
            name="categories",
            field=models.ManyToManyField(related_name="activities", to="guide.category", verbose_name="Kategorien"),
        ),
        # Rückwärts nicht möglich (aus mehreren Kategorien kann man nicht automatisch eine machen)
        migrations.RunPython(copy_category, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="activity",
            name="category",
        ),
    ]
