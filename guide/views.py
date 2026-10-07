from django.shortcuts import render
from .models import Activity

def activities(request):
    activities = Activity.objects.select_related("category", "location")
    return render(request, "guide/activities.html", {"activities": activities})

def home(request):
    return render(request, "guide/home.html")

def favorites(request):
    return render(request, "guide/favorites.html")


def add_activity(request):
    return render(request, "guide/add_activity.html")
