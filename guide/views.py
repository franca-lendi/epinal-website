from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from .forms import RegisterForm, ActivityForm
from .models import Activity, Location


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
    activities = (
        Activity.objects.filter(status="published")
        .select_related("category", "location")
        .order_by("-created_at")
    )
    return render(request, "guide/activities.html", {"activities": activities})


def home(request):
    return render(request, "guide/home.html")


def favorites(request):
    return render(request, "guide/favorites.html")


@login_required
def add_activity(request):
    start_step = 1

    if request.method == "POST":
        form = ActivityForm(request.POST, request.FILES)
        if form.is_valid():
            activity = form.save(commit=False)
            activity.user = request.user
            activity.location = Location.objects.create(
                address=form.cleaned_data["address"],
                city=form.cleaned_data["city"],
            )
            activity.status = "published"
            activity.save()
            messages.success(request, "Deine Aktivität wurde hinzugefügt.")
            return redirect("activities")  # kommt in Schritt 3: zur Detailseite mit Bewerten
        # Fehler nur in Schritt 2? Dann Schritt 2 gleich anzeigen
        if form.errors and set(form.errors) <= ActivityForm.STEP2_FIELDS:
            start_step = 2
    else:
        form = ActivityForm()

    return render(request, "guide/add_activity.html", {"form": form, "start_step": start_step})