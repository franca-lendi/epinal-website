from urllib.parse import quote

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from .forms import RegisterForm
from .models import Activity


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
    activities = Activity.objects.select_related("category", "location")
    return render(request, "guide/activities.html", {"activities": activities})


def home(request):
    return render(request, "guide/home.html")


def favorites(request):
    return render(request, "guide/favorites.html")


@login_required
def add_activity(request):
    return render(request, "guide/add_activity.html")