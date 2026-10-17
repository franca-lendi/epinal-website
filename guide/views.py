from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Exists, OuterRef, Q, Subquery
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import RegisterForm, ActivityForm, ContactForm, PhotoForm, ReportForm, ReviewForm, SiteInfoForm
from .models import Activity, ActivityImage, Category, Favorite, Location, Rating, SiteInfo, VisitCounter


def with_ratings(queryset):
    # Hängt jeder Aktivität den Durchschnitt (avg_rating) und die Anzahl (rating_count) an
    return queryset.annotate(
        avg_rating=Avg("ratings__rating"),
        rating_count=Count("ratings", distinct=True),
    )


def with_favorites(queryset, user):
    # Hängt jeder Aktivität is_favorite = True/False für die angemeldete Person an
    if not user.is_authenticated:
        return queryset
    return queryset.annotate(
        is_favorite=Exists(Favorite.objects.filter(user=user, activity=OuterRef("pk")))
    )


# ---------- NEU: Ansichten Kacheln / Tabelle / Karte ----------
VIEWS = ("cards", "table", "map")


def get_view(request, allowed=VIEWS):
    # Welche Ansicht steht in der Adresse? (?view=map) Sonst Kacheln.
    view = request.GET.get("view")
    return view if view in allowed else "cards"


def map_points(activities):
    # Für die Kartenansicht: Titel, Link und Koordinaten jeder Aktivität.
    # Nur Aktivitäten mit Koordinaten (kommen von der Adresssuche) können auf die Karte.
    points = []
    for activity in activities:
        location = activity.location
        if location.latitude is None or location.longitude is None:
            continue
        points.append({
            "id": activity.pk,  # verbindet die Nadel mit dem Eintrag in der Liste daneben
            "title": activity.title,
            "url": reverse("activity_detail", args=[activity.pk]),
            "category": activity.category.label,
            "price": "Kostenlos" if activity.price == 0 else f"{activity.price} €",
            "lat": float(location.latitude),
            "lng": float(location.longitude),
        })
    return points


def category_tree():
    # Für den Filter: Hauptkategorien, darunter ihre Unterkategorien, je mit der Anzahl veröffentlichter Aktivitäten.
    # Bei der Hauptkategorie zählen alle Unterkategorien mit (auch Vorschläge, die noch nicht freigegeben sind).
    counts = dict(
        Activity.objects.filter(status="published").values_list("category").annotate(n=Count("id"))
    )
    all_categories = list(Category.objects.order_by("position", "name"))
    mains = [c for c in all_categories if c.parent_id is None]
    for main in mains:
        children = [c for c in all_categories if c.parent_id == main.pk]
        main.subs = [c for c in children if c.approved]  # nur freigegebene im Filter zeigen
        for sub in main.subs:
            sub.activity_count = counts.get(sub.pk, 0)
        main.activity_count = counts.get(main.pk, 0) + sum(counts.get(c.pk, 0) for c in children)
    return mains


def own_activity_or_404(request, pk):
    # Nur wer die Aktivität erstellt hat, darf sie bearbeiten oder löschen
    return get_object_or_404(Activity, pk=pk, user=request.user)


def is_ajax(request):
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def login_view(request):
    # Anmelden im Hintergrund (aus dem Kästchen)
    if request.method == "POST" and is_ajax(request):
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            return JsonResponse({"ok": True})
        return JsonResponse({"ok": False, "errors": {"login": ["Benutzername/E-Mail oder Passwort falsch."]}})

    # Alles andere: zurück zur Seite, Kästchen geht automatisch auf
    url = reverse("activities") + "?login=1"
    next_url = request.GET.get("next")
    if next_url:
        url += "&next=" + quote(next_url)
    return redirect(url)


def register(request):
    if request.method == "POST" and is_ajax(request):
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)  # direkt eingeloggt
            return JsonResponse({"ok": True})
        errors = {field: [str(e) for e in errs] for field, errs in form.errors.items()}
        return JsonResponse({"ok": False, "errors": errors})

    return redirect(reverse("activities") + "?register=1")


PRICE_MAX = 100  # ganz rechts beim Schieberegler = keine Obergrenze


def parse_date(value):
    # "2026-10-15" -> date, alles andere -> None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def activities(request):
    activities = Activity.objects.filter(status="published").select_related("category__parent", "location")

    # ---------- Suche ----------
    # Sucht im Namen, in der Beschreibung, in der Kategorie und in der Adresse
    query = request.GET.get("q", "").strip()
    if query:
        for word in query.split():  # jedes Wort muss irgendwo vorkommen
            activities = activities.filter(
                Q(title__icontains=word)
                | Q(description__icontains=word)
                | Q(category__name__icontains=word)
                | Q(category__parent__name__icontains=word)  # "sport" findet auch Fussball
                | Q(location__address__icontains=word)
                | Q(location__city__icontains=word)
            )

    # ---------- Filter: Kategorie (mehrere möglich) ----------
    # Hauptkategorie gewählt = auch alle ihre Unterkategorien
    selected_categories = [c for c in request.GET.getlist("category") if c.isdigit()]
    category_count = 0
    if selected_categories:
        chosen = list(Category.objects.filter(pk__in=selected_categories))
        chosen_ids = {c.pk for c in chosen}
        ids = chosen_ids | set(Category.objects.filter(parent_id__in=chosen_ids).values_list("pk", flat=True))
        activities = activities.filter(category_id__in=ids)
        # Zahl auf dem Knopf: Unterkategorien nicht doppelt zählen, wenn ihre Hauptkategorie gewählt ist
        category_count = sum(1 for c in chosen if c.parent_id not in chosen_ids)

    # ---------- Filter: Preis (höchstens ...) ----------
    try:
        max_price = Decimal(request.GET.get("max_price", PRICE_MAX))
    except InvalidOperation:
        max_price = Decimal(PRICE_MAX)
    max_price = max(Decimal(0), min(max_price, Decimal(PRICE_MAX)))
    if max_price < PRICE_MAX:
        activities = activities.filter(price__lte=max_price)

    # ---------- Filter: Datum (von / bis) ----------
    # Aktivitäten ohne Datum (z.B. ein Park) kann man immer machen, sie bleiben drin.
    # Events mit Datum erscheinen nur, wenn ihr Datum im gewählten Zeitraum liegt.
    date_from = parse_date(request.GET.get("date_from"))
    date_to = parse_date(request.GET.get("date_to"))
    if date_from:
        activities = activities.filter(Q(event_date__isnull=True) | Q(event_date__gte=date_from))
    if date_to:
        activities = activities.filter(Q(event_date__isnull=True) | Q(event_date__lte=date_to))

    activities = with_favorites(with_ratings(activities), request.user).order_by("-created_at")

    # Wie viele Filter sind aktiv? (für die Zahl auf den Knöpfen)
    active = {
        "category": category_count,
        "date": int(bool(date_from or date_to)),
        "price": int(max_price < PRICE_MAX),
    }

    # Bei den Aktivitäten gibt es nur Kacheln und Karte (eine Tabelle bringt hier nichts)
    view = get_view(request, allowed=("cards", "map"))

    return render(request, "guide/activities.html", {
        "activities": activities,
        "view": view,
        "map_points": map_points(activities) if view == "map" else [],
        "categories": category_tree(),
        "query": query,
        "selected_categories": selected_categories,
        "max_price": int(max_price),
        "price_max": PRICE_MAX,
        "date_from": date_from,
        "date_to": date_to,
        "active": active,
        "any_filter": query or any(active.values()),
    })


def activity_detail(request, pk):
    activity = get_object_or_404(
        with_favorites(with_ratings(Activity.objects.select_related("category__parent", "location", "user")), request.user),
        pk=pk,
    )
    # Entwürfe sieht nur die eigene Person
    if activity.status != "published" and activity.user != request.user:
        raise Http404

    my_rating = None
    if request.user.is_authenticated:
        my_rating = Rating.objects.filter(user=request.user, activity=activity).first()

    return render(request, "guide/activity_detail.html", {
        "activity": activity,
        "photos": activity.images.order_by("created_at"),
        "reviews": activity.ratings.select_related("user").order_by("-created_at"),
        "my_rating": my_rating,
        "photo_form": PhotoForm(),
        # auto_id: damit die zwei Formulare auf derselben Seite verschiedene ids haben
        "report_form": ReportForm(kind="report", auto_id="report_%s"),
        "error_form": ReportForm(kind="error", auto_id="error_%s"),
    })


def home(request):
    return render(request, "guide/home.html")


@login_required
def favorites(request):
    # Nur die Aktivitäten, die ich mit dem Herz markiert habe (neueste Markierung zuerst)
    my_favorites = Favorite.objects.filter(user=request.user, activity=OuterRef("pk"))
    activities = (
        with_favorites(with_ratings(Activity.objects.filter(status="published")), request.user)
        .filter(is_favorite=True)
        .annotate(favorited_at=Subquery(my_favorites.values("created_at")[:1]))
        .select_related("category__parent", "location")
        .order_by("-favorited_at")
    )
    view = get_view(request)
    return render(request, "guide/favorites.html", {
        "activities": activities,
        "view": view,
        "map_points": map_points(activities) if view == "map" else [],
    })


@login_required
@require_POST
def toggle_favorite(request, pk):
    # Herz anklicken: Favorit hinzufügen, nochmals anklicken: wieder entfernen
    activity = get_object_or_404(Activity, pk=pk, status="published")
    favorite, created = Favorite.objects.get_or_create(user=request.user, activity=activity)
    if not created:
        favorite.delete()

    if is_ajax(request):
        # Antwort für das JavaScript (ohne Seite neu zu laden)
        return JsonResponse({"ok": True, "is_favorite": created})

    # Ohne JavaScript: zurück zur Seite, von der man kam
    next_url = request.POST.get("next", "")
    if next_url.startswith("/") and not next_url.startswith("//"):
        return redirect(next_url)
    return redirect("activity_detail", pk=activity.pk)


@login_required
def add_activity(request, pk=None):
    # Ohne pk = neue Aktivität, mit pk = bearbeiten
    activity = own_activity_or_404(request, pk) if pk else None
    start_step = 1

    if request.method == "POST":
        form = ActivityForm(request.POST, request.FILES, instance=activity)
        if form.is_valid():
            new_activity = form.save(commit=False)
            # Ort speichern (neu oder bestehenden anpassen), inkl. Koordinaten aus der Adresssuche
            location = activity.location if activity else Location()
            for field in ["address", "postal_code", "city", "latitude", "longitude"]:
                setattr(location, field, form.cleaned_data[field])
            location.save()
            new_activity.location = location
            if not activity:
                new_activity.user = request.user
            # NEU: "Andere" + eigener Vorschlag -> neue Unterkategorie, aber erst nach Freigabe im Filter sichtbar.
            # Gibt es sie schon (gross/klein egal), wird die bestehende genommen statt einer doppelten.
            suggestion = form.cleaned_data.get("new_category", "").strip()
            if suggestion:
                new_activity.category, _ = Category.objects.get_or_create(
                    parent=new_activity.category.parent,
                    name__iexact=suggestion,
                    defaults={"name": suggestion, "approved": False, "position": 50},
                )
            # Knopf "Als Entwurf speichern" oder "Senden"
            was_published = activity is not None and activity.status == "published"
            in_review = activity is not None and activity.status == "review"
            if in_review:
                # Gemeldet: bleibt in Prüfung, bis der Admin sie freigibt (sonst könnte man die Prüfung umgehen)
                new_activity.status = "review"
            else:
                new_activity.status = "draft" if "save_draft" in request.POST else "published"
            new_activity.save()

            if in_review:
                messages.success(request, "Gespeichert. Die Aktivität bleibt in Prüfung, bis sie freigegeben wird.")
                return redirect("my_uploads")
            if new_activity.status == "draft":
                messages.success(request, "Als Entwurf gespeichert. Du findest ihn unter «Deine Uploads».")
                return redirect("my_uploads")
            if was_published:
                messages.success(request, "Deine Änderungen wurden gespeichert.")
                return redirect("activity_detail", pk=new_activity.pk)
            # Neu veröffentlicht: direkt weiter zum Bewerten
            messages.success(request, "Deine Aktivität ist jetzt online. Wie war dein Besuch?")
            return redirect("review_activity", pk=new_activity.pk)
        # Fehler nur in Schritt 2? Dann Schritt 2 gleich anzeigen
        if form.errors and set(form.errors) <= ActivityForm.STEP2_FIELDS:
            start_step = 2
    else:
        initial = {}
        if activity:
            location = activity.location
            initial = {
                "address": location.address,
                "postal_code": location.postal_code,
                "city": location.city,
                "latitude": location.latitude,
                "longitude": location.longitude,
            }
        form = ActivityForm(instance=activity, initial=initial)

    return render(request, "guide/add_activity.html", {
        "form": form,
        "start_step": start_step,
        "activity": activity,
    })


@login_required
@require_POST
def delete_activity(request, pk):
    activity = own_activity_or_404(request, pk)
    location = activity.location
    title = activity.title
    activity.delete()
    # Den Ort auch löschen, wenn ihn keine andere Aktivität braucht
    if not location.activity_set.exists():
        location.delete()
    messages.success(request, f"«{title}» wurde gelöscht.")
    return redirect("my_uploads")


# ---------- NEU: Deine Uploads ----------

SORT_OPTIONS = {
    "newest": ("Neueste zuerst", ["-created_at"]),
    "oldest": ("Älteste zuerst", ["created_at"]),
    "title": ("Name A–Z", ["title"]),
    "rating": ("Beste Bewertung", ["-avg_rating", "-created_at"]),
}


@login_required
def my_uploads(request):
    mine = Activity.objects.filter(user=request.user)
    counts = mine.aggregate(
        all=Count("id"),
        drafts=Count("id", filter=Q(status="draft")),
    )

    tab = request.GET.get("tab", "all")
    if tab == "drafts":
        mine = mine.filter(status="draft")

    sort = request.GET.get("sort", "newest")
    if sort not in SORT_OPTIONS:
        sort = "newest"
    view = get_view(request)

    activities = with_ratings(mine.select_related("category__parent", "location")).order_by(*SORT_OPTIONS[sort][1])
    # 8 pro Seite: zusammen mit der "Füge hinzu"-Karte gibt das 3 volle Reihen à 3
    page = Paginator(activities, 8).get_page(request.GET.get("page"))

    return render(request, "guide/my_uploads.html", {
        "page": page,
        "counts": counts,
        "tab": tab,
        "sort": sort,
        "sort_options": {key: label for key, (label, _) in SORT_OPTIONS.items()},
        "view": view,
        # Karte und Liste daneben zeigen alle Uploads dieses Tabs (nicht nur die 8 von dieser Seite)
        "map_list": activities if view == "map" else [],
        "map_points": map_points(activities) if view == "map" else [],
    })


# ---------- NEU: Bewerten ----------

@login_required
def review_activity(request, pk):
    activity = get_object_or_404(Activity, pk=pk, status="published")
    # Schon bewertet? Dann wird die Bewertung geändert statt doppelt erstellt
    rating = Rating.objects.filter(user=request.user, activity=activity).first()

    if request.method == "POST":
        form = ReviewForm(request.POST, request.FILES)  # FILES = die Fotos
        if form.is_valid():
            Rating.objects.update_or_create(
                user=request.user, activity=activity,
                defaults={
                    "rating": form.cleaned_data["rating"],
                    "title": form.cleaned_data["title"],
                    "text": form.cleaned_data["text"],
                    "visited_on": form.visited_date(),
                },
            )
            # Fotos aus der Bewertung erscheinen bei den Fotos der Aktivität
            for photo in form.cleaned_data["photos"]:
                ActivityImage.objects.create(activity=activity, user=request.user, image=photo)
            messages.success(request, "Danke für deine Bewertung!")
            return redirect("activity_detail", pk=activity.pk)
    else:
        initial = {}
        if rating:
            initial = {
                "rating": rating.rating,
                "title": rating.title,
                "text": rating.text,
            }
            if rating.visited_on:
                initial["visited"] = rating.visited_on.strftime("%Y-%m")
        form = ReviewForm(initial=initial)

    return render(request, "guide/review_form.html", {
        "form": form,
        "activity": activity,
        "editing": rating is not None,
    })


# ---------- NEU: Fotos hinzufügen ----------

@login_required
@require_POST
def add_photos(request, pk):
    activity = get_object_or_404(Activity, pk=pk, status="published")
    form = PhotoForm(request.POST, request.FILES)
    if form.is_valid():
        for photo in form.cleaned_data["photos"]:
            ActivityImage.objects.create(activity=activity, user=request.user, image=photo)
        messages.success(request, "Danke, deine Fotos wurden hinzugefügt.")
    else:
        for error in form.errors.get("photos", []):
            messages.error(request, error)
    return redirect(reverse("activity_detail", args=[activity.pk]) + "#fotos")


# ---------- NEU: Melden und Fehler melden ----------

@login_required
@require_POST
def report_activity(request, pk, kind):
    activity = get_object_or_404(Activity, pk=pk, status="published")
    form = ReportForm(request.POST, kind=kind)
    if form.is_valid():
        report = form.save(commit=False)
        report.user = request.user
        report.activity = activity
        report.save()
        if kind == "error":
            messages.success(request, "Danke! Wir prüfen den Fehler und korrigieren ihn.")
        elif report.reason == "inappropriate":
            # Unangemessen: sofort ausblenden, bis ein Admin es geprüft hat
            activity.status = "review"
            activity.save(update_fields=["status"])
            messages.success(request, "Danke für deine Meldung. Die Aktivität ist ausgeblendet, bis wir sie geprüft haben.")
            return redirect("activities")
        else:
            messages.success(request, "Danke für deine Meldung. Wir schauen sie uns an.")
    else:
        if kind == "error":
            messages.error(request, "Bitte beschreib kurz, was falsch ist.")
        else:
            messages.error(request, "Bitte wähle einen Grund aus.")
    return redirect("activity_detail", pk=activity.pk)


# ---------- NEU: Über mich ----------

def about(request):
    info = SiteInfo.load()
    # Ein paar Zahlen, die sich von selbst aktualisieren
    stats = {
        "activities": Activity.objects.filter(status="published").count(),
        "ratings": Rating.objects.filter(activity__status="published").count(),
        "categories": Category.objects.filter(parent=None).count(),  # nur Hauptkategorien
        "visitors": VisitCounter.load().visitors,
    }
    return render(request, "guide/about.html", {"info": info, "stats": stats})


@staff_member_required  # nur Admin (is_staff) darf bearbeiten, alle anderen landen beim Admin-Login
def about_edit(request):
    info = SiteInfo.load()
    if request.method == "POST":
        form = SiteInfoForm(request.POST, request.FILES, instance=info)
        if form.is_valid():
            form.save()
            messages.success(request, "«Über mich» wurde gespeichert.")
            return redirect("about")
    else:
        form = SiteInfoForm(instance=info)
    return render(request, "guide/about_edit.html", {"form": form, "info": info})


# ---------- NEU: Kontakt ----------

def contact(request):
    info = SiteInfo.load()
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            message = form.save(commit=False)
            if request.user.is_authenticated:
                message.user = request.user
            message.save()  # steht danach im Admin unter "Contact messages"
            messages.success(request, "Danke für deine Nachricht! Ich melde mich so bald wie möglich.")
            return redirect("contact")
    else:
        # Angemeldet: Name und E-Mail schon ausfüllen. ?topic=problem wählt das Thema vor (Link im Footer)
        initial = {"topic": request.GET.get("topic", "question")}
        if request.user.is_authenticated:
            initial.update({"name": request.user.username, "email": request.user.email})
        form = ContactForm(initial=initial)
    return render(request, "guide/contact.html", {"form": form, "info": info})

