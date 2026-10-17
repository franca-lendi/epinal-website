from django.contrib import admin
from .models import Category, Location, Activity, ActivityImage, Rating, Report, Favorite, SiteInfo, ContactMessage, VisitCounter

for m in (Location, Activity, ActivityImage, Rating, Report, Favorite, SiteInfo, ContactMessage, VisitCounter):
    admin.site.register(m)


# NEU: Kategorien mit Reihenfolge, die man direkt in der Liste ändern kann
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "position", "approved")
    list_editable = ("position", "approved")   # Vorschläge freigeben = Häkchen setzen und speichern
    list_filter = ("approved", "parent")