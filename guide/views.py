from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import RegisterForm, ActivityForm, PhotoForm, ReportForm, ReviewForm
from .models import Activity, ActivityImage, Location, Rating


def with_ratings(queryset):
    # Hängt jeder Aktivität den Durchschnitt (avg_rating) und die Anzahl (rating_count) an
    return queryset.annotate(
        avg_rating=Avg("ratings__rating"),
        rating_count=Count("ratings", distinct=True),
    )


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
        return JsonResponse({"ok": False, "errors": {"login": ["Benutzername oder Passwort falsch."]}})

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


def activities(request):
    activities = with_ratings(
        Activity.objects.filter(status="published")
        .select_related("category", "location")
        .order_by("-created_at")
    )
    return render(request, "guide/activities.html", {"activities": activities})


def activity_detail(request, pk):
    activity = get_object_or_404(
        with_ratings(Activity.objects.select_related("category", "location", "user")),
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


def favorites(request):
    return render(request, "guide/favorites.html")


@login_required
def add_activity(request, pk=None):
    # Ohne pk = neue Aktivität, mit pk = bearbeiten
    activity = own_activity_or_404(request, pk) if pk else None
    start_step = 1

    if request.method == "POST":
        form = ActivityForm(request.POST, request.FILES, instance=activity)
        if form.is_valid():
            new_activity = form.save(commit=False)
            if activity:
                # Bearbeiten: bestehende Location anpassen
                location = activity.location
                location.address = form.cleaned_data["address"]
                location.city = form.cleaned_data["city"]
                location.save()
            else:
                new_activity.user = request.user
                new_activity.location = Location.objects.create(
                    address=form.cleaned_data["address"],
                    city=form.cleaned_data["city"],
                )
            # Knopf "Als Entwurf speichern" oder "Senden"
            was_published = activity is not None and activity.status == "published"
            new_activity.status = "draft" if "save_draft" in request.POST else "published"
            new_activity.save()

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
            initial = {"address": activity.location.address, "city": activity.location.city}
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
    view = "table" if request.GET.get("view") == "table" else "cards"

    activities = with_ratings(mine.select_related("category", "location")).order_by(*SORT_OPTIONS[sort][1])
    page = Paginator(activities, 9).get_page(request.GET.get("page"))

    return render(request, "guide/my_uploads.html", {
        "page": page,
        "counts": counts,
        "tab": tab,
        "sort": sort,
        "sort_options": {key: label for key, (label, _) in SORT_OPTIONS.items()},
        "view": view,
    })


# ---------- NEU: Bewerten ----------

@login_required
def review_activity(request, pk):
    activity = get_object_or_404(Activity, pk=pk, status="published")
    # Schon bewertet? Dann wird die Bewertung geändert statt doppelt erstellt
    rating = Rating.objects.filter(user=request.user, activity=activity).first()

    if request.method == "POST":
        form = ReviewForm(request.POST)
        if form.is_valid():
            Rating.objects.update_or_create(
                user=request.user, activity=activity,
                defaults={
                    "rating": form.cleaned_data["rating"],
                    "title": form.cleaned_data["title"],
                    "text": form.cleaned_data["text"],
                    "visited_on": form.visited_date(),
                    "companions": form.cleaned_data["companions"],
                },
            )
            messages.success(request, "Danke für deine Bewertung!")
            return redirect("activity_detail", pk=activity.pk)
    else:
        initial = {}
        if rating:
            initial = {
                "rating": rating.rating,
                "title": rating.title,
                "text": rating.text,
                "companions": rating.companions,
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
        else:
            messages.success(request, "Danke für deine Meldung. Wir schauen sie uns an.")
    else:
        if kind == "error":
            messages.error(request, "Bitte beschreib kurz, was falsch ist.")
        else:
            messages.error(request, "Bitte wähle einen Grund aus.")
    return redirect("activity_detail", pk=activity.pk)
