from django.shortcuts import render

def home(request):
    return render(request, "guide/home.html")

