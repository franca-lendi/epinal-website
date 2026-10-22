"""
NEU: Zahl der Dinge, die du als Admin prüfen musst (für den Link «Prüfen» in der Navigation).
Ein Context-Processor gibt jedem Template zusätzliche Variablen mit, ohne dass jede View sie einzeln übergeben muss.
Eingetragen in config/settings.py unter TEMPLATES -> context_processors.
"""
from .models import Activity, Category, Notification, Report


def moderation(request):
    user = getattr(request, "user", None)
    if not (user and user.is_staff):
        return {}  # für alle anderen nichts abfragen
    activities = Activity.objects.filter(status__in=["pending", "review"]).count()
    suggestions = Category.objects.filter(approved=False).count()
    reports = Report.objects.filter(status="open", activity__status="published").count()  # Fehler und Meldungen
    return {"moderation_count": activities + suggestions + reports}


def notifications(request):
    # NEU: Zahl der ungelesenen Mitteilungen für die Glocke in der Navigation
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated):
        return {}
    return {"unread_notifications": Notification.objects.filter(user=user, read=False).count()}
