from django.contrib import admin
from .models import Category, Location, Activity, ActivityImage, Rating, Report, Favorite, SiteInfo, ContactMessage, VisitCounter

for m in (Location, ActivityImage, Rating, Report, Favorite, SiteInfo, ContactMessage, VisitCounter):
    admin.site.register(m)


# NEU: Aktivitäten freigeben. Neue Aktivitäten haben den Status "Wartet auf Freigabe".
# In der Liste nach Status filtern, Häkchen setzen, Aktion "Freigeben" wählen.
@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "user", "created_at")
    list_filter = ("status",)
    search_fields = ("title", "description")
    actions = ["approve"]

    @admin.action(description="Freigeben (veröffentlichen)")
    def approve(self, request, queryset):
        count = queryset.update(status="published")
        self.message_user(request, f"{count} Aktivität(en) freigegeben.")


# NEU: Kategorien mit Reihenfolge, die man direkt in der Liste ändern kann
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "position", "approved")
    list_editable = ("position", "approved")   # Vorschläge freigeben = Häkchen setzen und speichern
    list_filter = ("approved", "parent")