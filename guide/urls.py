from django.urls import path

from . import views

from django.contrib.auth.views import LogoutView

urlpatterns = [

    path("", views.activities, name="home"),

    path("activities/", views.activities, name="activities"),

    path("favorites/", views.favorites, name="favorites"),

    path("add/", views.add_activity, name="add_activity"),

    path("register/", views.register, name="register"),

    path("accounts/login/", views.login_view, name="login"),

    path("accounts/logout/", LogoutView.as_view(), name="logout"),

]
