from django.contrib import admin
from .models import (Category, Location, Activity, ActivityImage, Rating, Report, Favorite, SiteInfo,
                     ContactMessage, VisitCounter, BusStop, Notification)

for m in (Location, ActivityImage, Rating, Report, Favorite, SiteInfo, VisitCounter, Notification):
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


# NEU: Bushaltestellen (werden mit «python manage.py import_bus_stops» automatisch geladen)
@admin.register(BusStop)
class BusStopAdmin(admin.ModelAdmin):
    list_display = ("name", "line_names")
    search_fields = ("name",)

    @admin.display(description="Linien")
    def line_names(self, stop):
        return ", ".join(line["name"] for line in stop.lines)


# NEU: Kontaktnachrichten mit Knopf «Antworten». Er öffnet dein E-Mail-Programm mit Adresse,
# Betreff und der Nachricht als Zitat. Danach wird die Nachricht als gelesen markiert.
@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("created_at", "name", "email", "topic", "is_read", "reply_link")
    list_filter = ("is_read", "topic")
    list_editable = ("is_read",)
    search_fields = ("name", "email", "message")
    readonly_fields = ("reply_link",)

    @admin.display(description="Antworten")
    def reply_link(self, message):
        from urllib.parse import quote
        from django.utils.html import format_html
        subject = f"Re: {message.get_topic_display()} (Épinal Guide)"
        quoted = "\n".join("> " + line for line in message.message.splitlines())
        body = f"Hallo {message.name}\n\n\n\n---\nDeine Nachricht vom {message.created_at:%d.%m.%Y}:\n{quoted}"
        url = f"mailto:{message.email}?subject={quote(subject)}&body={quote(body)}"
        return format_html('<a class="button" href="{}">Antworten</a>', url)
