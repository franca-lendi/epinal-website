from datetime import date
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Exists, OuterRef, Q, Subquery
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy  # für Texte, die schon beim Start feststehen
from django.views.decorators.http import require_POST

from .bus import distance_m, nearest_stops, route_links
from .translate import translate_activity, translate_rating
from .forms import ProfileForm, RegisterForm, ActivityForm, ContactForm, PhotoForm, ReportForm, ReviewForm, SiteInfoForm
from .models import (Activity, ActivityImage, Category, Favorite, Location, Notification, Rating, Report, SiteInfo,
                     VisitCounter)


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
            "title": activity.display_title,
            "url": reverse("activity_detail", args=[activity.pk]),
            "category": ", ".join(c.label for c in activity.categories.all()),
            "price": activity.get_price_level_display(),
            "lat": float(location.latitude),
            "lng": float(location.longitude),
        })
    return points


def category_tree(selected=()):
    # Für den Filter: Hauptkategorien, darunter ihre Unterkategorien, je mit der Anzahl veröffentlichter Aktivitäten.
    # Bei der Hauptkategorie zählen alle Unterkategorien mit (auch Vorschläge, die noch nicht freigegeben sind).
    # Eine Aktivität kann bis zu 3 Kategorien haben. Darum pro Kategorie die Menge (set) der Aktivitäten sammeln:
    # So zählt eine Aktivität mit Fussball und Basketball bei Sport & Bewegung nur einmal.
    links = Activity.categories.through.objects.filter(activity__status="published")
    activities_per_category = {}
    for activity_id, category_id in links.values_list("activity_id", "category_id"):
        activities_per_category.setdefault(category_id, set()).add(activity_id)

    all_categories = list(Category.objects.order_by("position", "name"))
    mains = [c for c in all_categories if c.parent_id is None and c.approved]  # Vorschläge erst nach Freigabe
    for main in mains:
        children = [c for c in all_categories if c.parent_id == main.pk]
        main.subs = [c for c in children if c.approved]  # nur freigegebene im Filter zeigen
        for sub in main.subs:
            sub.activity_count = len(activities_per_category.get(sub.pk, set()))
        together = set(activities_per_category.get(main.pk, set()))
        for child in children:
            together |= activities_per_category.get(child.pk, set())
        main.activity_count = len(together)
        # Unterkategorien im Filter aufgeklappt zeigen, wenn eine davon gewählt ist
        main.open = any(str(sub.pk) in selected for sub in main.subs)
    return mains


def own_activity_or_404(request, pk):
    # Nur wer die Aktivität erstellt hat, darf sie bearbeiten oder löschen.
    # NEU: der Admin auch (z.B. um einen gemeldeten Fehler zu korrigieren)
    if request.user.is_staff:
        return get_object_or_404(Activity, pk=pk)
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
        return JsonResponse({"ok": False, "errors": {"login": [_("Benutzername/E-Mail oder Passwort falsch.")]}})

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


# NEU: Preis-Filter «höchstens»: Stufe -> Text (Stufen siehe PRICE_LEVELS in models.py)
PRICE_FILTER = [(0, gettext_lazy("Nur gratis")), (1, gettext_lazy("bis 10 €")), (2, gettext_lazy("bis 20 €")), (3, gettext_lazy("bis 30 €")),
                (4, gettext_lazy("bis 50 €")), (5, gettext_lazy("bis 100 €"))]


# NEU: Distanz-Filter. Startpunkt: eigener Standort (aus dem Browser) oder ein fester Punkt.
DIST_ORIGINS = {
    "gare": (48.1778971, 6.4420341),    # Bahnhof Épinal (Koordinaten von OpenStreetMap)
    "centre": (48.1746578, 6.4502294),  # Place des Vosges
}
DIST_CHOICES = (1, 3, 5, 10)  # km


def local_now():
    # NEU: jetzt, in der Zeitzone der Website (Épinal hat die gleiche Zeit wie Zürich)
    return timezone.localtime()


def distance_text(meters):
    # 350 -> "350 m", 1240 -> "1,2 km"
    if meters < 1000:
        return f"{int(round(meters, -1))} m"
    return f"{meters / 1000:.1f} km".replace(".", ",")


def parse_date(value):
    # "2026-10-15" -> date, alles andere -> None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def activities(request):
    activities = Activity.objects.filter(status="published").select_related("location").prefetch_related("categories__parent")

    # ---------- Suche ----------
    # Sucht im Namen, in der Beschreibung, in der Kategorie und in der Adresse
    query = request.GET.get("q", "").strip()
    if query:
        for word in query.split():  # jedes Wort muss irgendwo vorkommen
            activities = activities.filter(
                Q(title__icontains=word)
                | Q(description__icontains=word)
                | Q(title_tr__icontains=word)          # NEU: auch in der Übersetzung suchen
                | Q(description_tr__icontains=word)
                # Kategorien über eine Unterabfrage, damit keine Aktivität doppelt erscheint ("sport" findet auch Fussball)
                | Q(pk__in=Activity.objects.filter(
                    Q(categories__name__icontains=word) | Q(categories__parent__name__icontains=word)
                ).values("pk"))
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
        activities = activities.filter(pk__in=Activity.objects.filter(categories__in=ids).values("pk"))
        # Zahl auf dem Knopf: Unterkategorien nicht doppelt zählen, wenn ihre Hauptkategorie gewählt ist
        category_count = sum(1 for c in chosen if c.parent_id not in chosen_ids)

    # ---------- Filter: Preis (höchstens bis zu einer Stufe) ----------
    # NEU: ?price=2 heisst «bis 20 €» = Stufen 0, 1 und 2. Nichts gewählt = egal.
    price = request.GET.get("price", "")
    price = int(price) if price.isdigit() and int(price) in dict(PRICE_FILTER) else None
    if price is not None:
        activities = activities.filter(price_level__lte=price)

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

    # ---------- NEU: Filter: Distanz ----------
    # ?dist=3&from=gare  oder  ?dist=3&from=me&lat=48.17&lng=6.45 (Standort fragt das JavaScript im Browser ab)
    dist = request.GET.get("dist", "")
    dist = int(dist) if dist.isdigit() and int(dist) in DIST_CHOICES else None
    origin = request.GET.get("from", "me")
    point = DIST_ORIGINS.get(origin)
    if origin == "me":
        try:
            lat, lng = float(request.GET.get("lat", "")), float(request.GET.get("lng", ""))
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                point = (lat, lng)
        except ValueError:
            point = None
    # Filter «Jetzt geöffnet»: vorerst weggelassen (zu wenige Öffnungszeiten eingetragen).
    # Die Prüfung dafür gibt es schon: Activity.is_open_at(local_now())

    if dist and point:
        # Abstand für jede Aktivität mit Koordinaten ausrechnen, nur die nahen behalten, die nächsten zuerst
        nearby = []
        for activity in activities:
            location = activity.location
            if location.latitude is None or location.longitude is None:
                continue
            meters = distance_m(point[0], point[1], float(location.latitude), float(location.longitude))
            if meters <= dist * 1000:
                activity.distance = meters
                activity.distance_text = distance_text(meters)
                nearby.append(activity)
        activities = sorted(nearby, key=lambda a: a.distance)

    # Wie viele Filter sind aktiv? (für die Zahl auf den Knöpfen)
    active = {
        "category": category_count,
        "date": int(bool(date_from or date_to)),
        "price": int(price is not None),
        "distance": int(bool(dist and point)),
    }

    # Bei den Aktivitäten gibt es nur Kacheln und Karte (eine Tabelle bringt hier nichts)
    view = get_view(request, allowed=("cards", "map"))

    return render(request, "guide/activities.html", {
        "activities": activities,
        "view": view,
        "map_points": map_points(activities) if view == "map" else [],
        "categories": category_tree(selected_categories),
        "query": query,
        "selected_categories": selected_categories,
        "price": price,
        "price_label": dict(PRICE_FILTER).get(price, ""),
        "price_filter": PRICE_FILTER,
        "dist": dist,
        "dist_choices": DIST_CHOICES,
        "origin": origin if origin in ("me", "gare", "centre") else "me",
        "user_lat": request.GET.get("lat", ""),
        "user_lng": request.GET.get("lng", ""),
        "date_from": date_from,
        "date_to": date_to,
        "active": active,
        "any_filter": query or any(active.values()),
    })


def activity_detail(request, pk):
    activity = get_object_or_404(
        with_favorites(with_ratings(Activity.objects.select_related("location", "user").prefetch_related("categories__parent")), request.user),
        pk=pk,
    )
    # Entwürfe und Aktivitäten, die noch nicht freigegeben sind, sieht nur die eigene Person (und der Admin)
    if activity.status != "published" and activity.user != request.user and not request.user.is_staff:
        raise Http404

    my_rating = None
    if request.user.is_authenticated:
        my_rating = Rating.objects.filter(user=request.user, activity=activity).first()

    # NEU: alle Fotos zum Durchblättern, das Titelbild zuerst.
    # Eigene Fotos (oder alle für den Admin) haben einen Löschen-Knopf.
    photos = list(activity.images.select_related("user").order_by("created_at"))
    gallery = []
    if activity.image:
        gallery.append({"url": activity.image.url, "position": activity.image_position, "delete_url": ""})
    for photo in photos:
        can_delete = request.user.is_authenticated and (photo.user == request.user or request.user.is_staff)
        gallery.append({"url": photo.image.url, "position": "50% 50%",
                        "delete_url": reverse("delete_photo", args=[photo.pk]) if can_delete else ""})

    return render(request, "guide/activity_detail.html", {
        "activity": activity,
        "photos": photos,
        "gallery": gallery,
        "reviews": activity.ratings.select_related("user").order_by("-created_at"),
        "my_rating": my_rating,
        # NEU: «So kommst du hin»
        "bus_stops": nearest_stops(activity.location.latitude, activity.location.longitude),
        "route_links": route_links(activity.location.latitude, activity.location.longitude),
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
        .select_related("location").prefetch_related("categories__parent")
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
            # Knopf "Als Entwurf speichern" oder "Senden"
            was_published = activity is not None and activity.status == "published"
            in_review = activity is not None and activity.status == "review"
            if in_review:
                # Gemeldet: bleibt in Prüfung, bis der Admin sie freigibt (sonst könnte man die Prüfung umgehen)
                new_activity.status = "review"
            elif "save_draft" in request.POST:
                # NEU: zurückgeschickt bleibt zurückgeschickt, bis man sie wieder sendet
                new_activity.status = "returned" if activity and activity.status == "returned" else "draft"
            elif was_published:
                new_activity.status = "published"  # Änderungen an einer freigegebenen Aktivität bleiben online
            else:
                # NEU: neu gesendet (oder Entwurf gesendet): erst nach Freigabe durch den Admin sichtbar
                new_activity.status = "pending"
                new_activity.return_note = ""  # nochmals gesendet: Grund vom Zurückschicken ist erledigt
            new_activity.save()
            # NEU: Fotos (erstes = Titelbild, entfernte löschen)
            form.save_photos(new_activity, request.user)
            # NEU: Name, Beschreibung und Bemerkungen in die andere Sprache übersetzen (DeepL)
            translate_activity(new_activity)
            # Kategorien (n:m) gehen erst, wenn die Aktivität gespeichert ist
            new_activity.categories.set(form.cleaned_data["categories"])

            # NEU: «Eigene hinzufügen» + Text -> neue Unterkategorie statt «Andere», aber erst nach Freigabe im Filter.
            # Gibt es sie schon (gross/klein egal), wird die bestehende genommen statt einer doppelten.
            # parent=None: Vorschlag für eine neue Hauptkategorie (aus dem Dropdown)
            for parent, suggestion, replaces in form.cleaned_data["suggestions"]:
                suggested, _created = Category.objects.get_or_create(
                    parent=parent,
                    name__iexact=suggestion,
                    defaults={"name": suggestion, "approved": False, "position": 50},
                )
                if replaces:
                    new_activity.categories.remove(replaces)
                new_activity.categories.add(suggested)

            if in_review:
                messages.success(request, _("Gespeichert. Die Aktivität bleibt in Prüfung, bis sie freigegeben wird."))
                return redirect("my_uploads")
            if new_activity.status in ("draft", "returned"):
                messages.success(request, _("Als Entwurf gespeichert. Du findest ihn unter «Deine Uploads»."))
                return redirect("my_uploads")
            if was_published:
                messages.success(request, _("Deine Änderungen wurden gespeichert."))
                return redirect("activity_detail", pk=new_activity.pk)
            # NEU: gesendet, wartet auf Freigabe
            messages.success(request, _("Danke! Wir prüfen deine Aktivität. Sie erscheint innerhalb von 24 Stunden bei den Aktivitäten."))
            return redirect("my_uploads")
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
    messages.success(request, _("«%(title)s» wurde gelöscht.") % {"title": title})
    return redirect("my_uploads")


# ---------- NEU: Deine Uploads ----------

SORT_OPTIONS = {
    "newest": (gettext_lazy("Neueste zuerst"), ["-created_at"]),
    "oldest": (gettext_lazy("Älteste zuerst"), ["created_at"]),
    "title": (gettext_lazy("Name A–Z"), ["title"]),
    "rating": (gettext_lazy("Beste Bewertung"), ["-avg_rating", "-created_at"]),
}


@login_required
def my_uploads(request):
    mine = Activity.objects.filter(user=request.user)
    counts = mine.aggregate(
        all=Count("id"),
        drafts=Count("id", filter=Q(status__in=["draft", "returned"])),
    )

    tab = request.GET.get("tab", "all")
    if tab == "drafts":
        # NEU: Zurückgeschickte stehen auch bei den Entwürfen, man muss sie ja noch bearbeiten
        mine = mine.filter(status__in=["draft", "returned"])

    sort = request.GET.get("sort", "newest")
    if sort not in SORT_OPTIONS:
        sort = "newest"
    view = get_view(request)

    activities = with_ratings(mine.select_related("location").prefetch_related("categories__parent")).order_by(*SORT_OPTIONS[sort][1])
    # 8 pro Seite: zusammen mit der "Füge hinzu"-Karte gibt das 3 volle Reihen à 3
    page = Paginator(activities, 8).get_page(request.GET.get("page"))

    # NEU: ungelesene Mitteilungen poppen hier auf und gelten danach als gelesen
    new_notifications = list(request.user.notifications.filter(read=False)[:10])
    if new_notifications:
        Notification.objects.filter(pk__in=[n.pk for n in new_notifications]).update(read=True)

    return render(request, "guide/my_uploads.html", {
        "new_notifications": new_notifications,
        "page": page,
        "counts": counts,
        "tab": tab,
        "sort": sort,
        "sort_options": {key: label for key, (label, _order) in SORT_OPTIONS.items()},
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
            saved_rating, _created = Rating.objects.update_or_create(
                user=request.user, activity=activity,
                defaults={
                    "rating": form.cleaned_data["rating"],
                    "title": form.cleaned_data["title"],
                    "text": form.cleaned_data["text"],
                    "visited_on": form.visited_date(),
                },
            )
            translate_rating(saved_rating)  # NEU: Bewertung übersetzen (DeepL)
            # Fotos aus der Bewertung erscheinen bei den Fotos der Aktivität
            for photo in form.cleaned_data["photos"]:
                ActivityImage.objects.create(activity=activity, user=request.user, image=photo)
            messages.success(request, _("Danke für deine Bewertung!"))
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
        messages.success(request, _("Danke, deine Fotos wurden hinzugefügt."))
    else:
        for error in form.errors.get("photos", []):
            messages.error(request, error)
    return redirect(reverse("activity_detail", args=[activity.pk]) + "#fotos")


@login_required
@require_POST
def delete_photo(request, pk):
    # NEU: eigenes Foto wieder löschen (nur wer es hochgeladen hat, oder der Admin)
    photo = get_object_or_404(ActivityImage, pk=pk)
    if photo.user != request.user and not request.user.is_staff:
        raise Http404
    activity = photo.activity
    photo.delete()
    messages.success(request, _("Dein Foto wurde gelöscht."))
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
            messages.success(request, _("Danke! Wir prüfen den Fehler und korrigieren ihn."))
        else:
            # NEU: jede Meldung (unangemessen, Spam, anderes) blendet sofort aus, bis der Admin sie geprüft hat
            activity.status = "review"
            activity.save(update_fields=["status"])
            messages.success(request, _("Danke für deine Meldung. Die Aktivität ist ausgeblendet, bis wir sie geprüft haben."))
            return redirect("activities")
    else:
        if kind == "error":
            messages.error(request, _("Bitte beschreib kurz, was falsch ist."))
        else:
            messages.error(request, _("Bitte wähle einen Grund aus."))
    return redirect("activity_detail", pk=activity.pk)


# ---------- NEU: Prüfen und Freigeben (nur Admin) ----------

def safe_next(request, fallback):
    # zurück zur Seite, von der man kam (nur Adressen auf dieser Website)
    next_url = request.POST.get("next", "")
    if next_url.startswith("/") and not next_url.startswith("//"):
        return redirect(next_url)
    return redirect(fallback)


@staff_member_required
def moderation(request):
    # Alles auf einer Seite: neue Aktivitäten, gemeldete Aktivitäten, Vorschläge für Kategorien
    base = Activity.objects.select_related("user", "location").prefetch_related("categories__parent", "reports")
    return render(request, "guide/moderation.html", {
        "pending": base.filter(status="pending").order_by("created_at"),   # älteste zuerst
        "reported": base.filter(status="review").order_by("updated_at"),
        "suggestions": Category.objects.filter(approved=False).select_related("parent")
                                       .annotate(activity_count=Count("activities")),
        # NEU: offene Fehler-Meldungen zu Aktivitäten, die online sind.
        # (Meldungen blenden die Aktivität aus, die stehen oben bei «Gemeldet».)
        "reports": Report.objects.filter(status="open", activity__status="published")
                                 .select_related("activity", "user").order_by("created_at"),
    })


@staff_member_required
@require_POST
def resolve_report(request, pk):
    # Fehler korrigiert oder Meldung angeschaut: als erledigt markieren
    report = get_object_or_404(Report, pk=pk)
    report.status = "erledigt"
    report.save(update_fields=["status"])
    messages.success(request, _("Als erledigt markiert."))
    return redirect("moderation")


@staff_member_required
@require_POST
def approve_activity(request, pk):
    activity = get_object_or_404(Activity, pk=pk, status__in=["pending", "review"])
    was_reported = activity.status == "review"
    activity.status = "published"
    activity.save(update_fields=["status"])
    # gemeldet und trotzdem in Ordnung: offene Meldungen als erledigt markieren
    Report.objects.filter(activity=activity, status="open").update(status="erledigt")
    # NEU: Mitteilung an die Person, die sie hinzugefügt hat
    def text():
        if was_reported:
            return _("Deine Aktivität «%(title)s» wurde geprüft und ist wieder online.") % {"title": activity.title}
        return _("Deine Aktivität «%(title)s» wurde freigegeben und ist jetzt online. Danke!") % {"title": activity.title}
    notify(activity.user, text, reverse("activity_detail", args=[activity.pk]))
    messages.success(request, _("«%(title)s» ist jetzt veröffentlicht.") % {"title": activity.title})
    return safe_next(request, "moderation")


def notify(user, text, link=""):
    # NEU: Mitteilung erstellen (poppt bei «Deine Uploads» auf).
    # text ist eine Funktion, die den Text baut. Sie wird einmal auf Deutsch und einmal auf Französisch
    # aufgerufen, damit die Person die Mitteilung in ihrer Sprache sieht.
    with translation.override("de"):
        text_de = text()
    with translation.override("fr"):
        text_fr = text()
    Notification.objects.create(user=user, text=text_de, text_fr=text_fr, link=link)


@staff_member_required
@require_POST
def return_activity(request, pk):
    # NEU: neue oder gemeldete Aktivität zum Überarbeiten zurückschicken, mit Grund.
    # Sie bleibt ausgeblendet. Wenn die Person sie überarbeitet und sendet, wartet sie wieder auf Freigabe.
    activity = get_object_or_404(Activity, pk=pk, status__in=["pending", "review"])
    note = request.POST.get("message", "").strip()
    if not note:
        messages.error(request, _("Bitte schreib kurz, was geändert werden soll."))
        return safe_next(request, "moderation")
    activity.status = "returned"
    activity.return_note = note
    activity.save(update_fields=["status", "return_note"])
    Report.objects.filter(activity=activity, status="open").update(status="zurückgeschickt")
    notify(activity.user,
           lambda: _("Deine Aktivität «%(title)s» wurde zurückgeschickt: %(note)s "
                     "Bitte überarbeite sie und sende sie nochmals.") % {"title": activity.title, "note": note},
           reverse("edit_activity", args=[activity.pk]))
    messages.success(request, _("«%(title)s» wurde zurückgeschickt.") % {"title": activity.title})
    return safe_next(request, "moderation")


@staff_member_required
@require_POST
def return_report(request, pk):
    # NEU: gemeldeten Fehler an die Person schicken, die die Aktivität hinzugefügt hat.
    # Die Aktivität bleibt online (ein Fehler ist meistens klein, z.B. falsche Öffnungszeiten).
    report = get_object_or_404(Report, pk=pk, status="open")
    activity = report.activity
    extra = request.POST.get("message", "").strip()
    def text():
        if report.description:
            result = _("Bei deiner Aktivität «%(title)s» wurde ein Fehler gemeldet: «%(error)s»") % {
                "title": activity.title, "error": report.description}
        else:
            result = _("Bei deiner Aktivität «%(title)s» wurde ein Fehler gemeldet.") % {"title": activity.title}
        if extra:
            result += f" {extra}"
        return result + " " + _("Kannst du das korrigieren?")
    notify(activity.user, text, reverse("edit_activity", args=[activity.pk]))
    report.status = "zurückgeschickt"
    report.save(update_fields=["status"])
    messages.success(request, _("Fehler zu «%(title)s» wurde an %(user)s geschickt.") % {
        "title": activity.title, "user": activity.user.username})
    return redirect("moderation")


@staff_member_required
@require_POST
def reject_category(request, pk):
    # NEU: Kategorie-Vorschlag verwerfen. Die Aktivitäten damit bekommen die Hauptkategorie
    # (bzw. «Andere» darin), und die Person bekommt eine Mitteilung.
    category = get_object_or_404(Category, pk=pk, approved=False)
    if category.children.exists():
        messages.error(request, _("«%(name)s» hat Unterkategorien und kann nicht verworfen werden.") % {"name": category.name})
        return redirect("moderation")
    replacement = None
    if category.parent:
        replacement = (Category.objects.filter(parent=category.parent, name="Andere", approved=True).first()
                       or category.parent)
    for activity in category.activities.select_related("user"):
        activity.categories.remove(category)
        if replacement:
            activity.categories.add(replacement)
        has_other = activity.categories.exists()

        def text(activity=activity, has_other=has_other):
            result = _("Dein Vorschlag «%(name)s» wurde nicht als Kategorie übernommen.") % {"name": category.name}
            if replacement:
                result += " " + _("«%(title)s» steht jetzt unter «%(main)s».") % {
                    "title": activity.title, "main": category.parent.display_name}
            elif not has_other:
                result += " " + _("Bitte wähle für «%(title)s» eine passende Kategorie.") % {"title": activity.title}
            return result
        notify(activity.user, text, reverse("edit_activity", args=[activity.pk]))
    name = category.name
    category.delete()
    messages.success(request, _("Vorschlag «%(name)s» wurde verworfen.") % {"name": name})
    return redirect("moderation")


@login_required
def profile(request):
    # NEU: Mein Profil. Angaben ansehen, Benutzername/E-Mail ändern, Passwort ändern.
    # Zwei Formulare auf einer Seite: der Knopf (name="save_profile" oder "save_password") sagt, welches gesendet wurde.
    profile_form = ProfileForm(instance=request.user)
    password_form = PasswordChangeForm(request.user)
    if request.method == "POST" and "save_profile" in request.POST:
        profile_form = ProfileForm(request.POST, instance=request.user)
        if profile_form.is_valid():
            profile_form.save()
            messages.success(request, _("Deine Angaben wurden gespeichert."))
            return redirect("profile")
    elif request.method == "POST" and "save_password" in request.POST:
        password_form = PasswordChangeForm(request.user, request.POST)
        if password_form.is_valid():
            user = password_form.save()
            update_session_auth_hash(request, user)  # sonst wäre man nach dem Ändern abgemeldet
            messages.success(request, _("Dein Passwort wurde geändert."))
            return redirect("profile")
    for field in password_form.fields.values():
        field.widget.attrs["class"] = "form-control"

    user = request.user
    stats = {
        "uploads": user.activities.count(),
        "published": user.activities.filter(status="published").count(),
        "reviews": Rating.objects.filter(user=user).count(),
        "favorites": Favorite.objects.filter(user=user).count(),
    }
    return render(request, "guide/profile.html", {
        "profile_form": profile_form,
        "password_form": password_form,
        "stats": stats,
        "show_password": password_form.is_bound,  # bei Fehlern das Passwort-Feld offen lassen
    })


@login_required
def notifications(request):
    # NEU: alle Mitteilungen, neueste zuerst. Beim Anschauen gelten sie als gelesen.
    items = list(request.user.notifications.all()[:50])
    unread_ids = [n.pk for n in items if not n.read]
    if unread_ids:
        Notification.objects.filter(pk__in=unread_ids).update(read=True)
    return render(request, "guide/notifications.html", {"items": items, "unread_ids": unread_ids})


@staff_member_required
@require_POST
def approve_category(request, pk):
    category = get_object_or_404(Category, pk=pk, approved=False)
    category.approved = True
    category.save(update_fields=["approved"])
    if category.parent:
        messages.success(request, _("«%(name)s» ist jetzt eine Unterkategorie von «%(main)s».") % {
            "name": category.name, "main": category.parent.name})
    else:
        messages.success(request, _("«%(name)s» ist jetzt eine Hauptkategorie.") % {"name": category.name})
    return redirect("moderation")


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
            messages.success(request, _("«Über mich» wurde gespeichert."))
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
            messages.success(request, _("Danke für deine Nachricht! Ich melde mich so bald wie möglich."))
            return redirect("contact")
    else:
        # Angemeldet: Name und E-Mail schon ausfüllen. ?topic=problem wählt das Thema vor (Link im Footer)
        initial = {"topic": request.GET.get("topic", "question")}
        if request.user.is_authenticated:
            initial.update({"name": request.user.username, "email": request.user.email})
        form = ContactForm(initial=initial)
    return render(request, "guide/contact.html", {"form": form, "info": info})

