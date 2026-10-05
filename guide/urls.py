from django.urls import path

from . import views

urlpatterns = [

    path("", views.home, name="home"),

    path("activities/", views.activities, name="activities"),

    path("favorites/", views.favorites, name="favorites"),

    path("add/", views.add_activity, name="add_activity"),

]