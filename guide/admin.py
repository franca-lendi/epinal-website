from django.contrib import admin
from .models import Category, Location, Activity, ActivityImage, Rating, Report, Favorite

for m in (Category, Location, Activity, ActivityImage, Rating, Report, Favorite):
    admin.site.register(m)