from django.shortcuts import render


def home(request):
    return render(request, "guide/home.html")


def activities(request):
    return render(request, "guide/activities.html")


def favorites(request):
    return render(request, "guide/favorites.html")


def add_activity(request):
    return render(request, "guide/add_activity.html")