from django.urls import path

from . import views

from django.contrib.auth.views import LogoutView

urlpatterns = [

    path("", views.activities, name="home"),

    path("activities/", views.activities, name="activities"),

    # NEU: Detailseite und was man dort machen kann
    path("activities/<int:pk>/", views.activity_detail, name="activity_detail"),

    path("activities/<int:pk>/review/", views.review_activity, name="review_activity"),

    path("activities/<int:pk>/photos/", views.add_photos, name="add_photos"),

    path("activities/<int:pk>/report/", views.report_activity, {"kind": "report"}, name="report_activity"),

    path("activities/<int:pk>/error/", views.report_activity, {"kind": "error"}, name="report_error"),

    # NEU: Bearbeiten und Löschen
    path("activities/<int:pk>/edit/", views.add_activity, name="edit_activity"),

    path("activities/<int:pk>/delete/", views.delete_activity, name="delete_activity"),

    # NEU: Prüfen und Freigeben (nur Admin)
    path("moderation/", views.moderation, name="moderation"),
    path("activities/<int:pk>/approve/", views.approve_activity, name="approve_activity"),
    path("categories/<int:pk>/approve/", views.approve_category, name="approve_category"),
    path("reports/<int:pk>/done/", views.resolve_report, name="resolve_report"),

    path("favorites/", views.favorites, name="favorites"),

    # NEU: Herz anklicken (Favorit hinzufügen oder entfernen)
    path("activities/<int:pk>/favorite/", views.toggle_favorite, name="toggle_favorite"),

    # NEU: Deine Uploads
    path("uploads/", views.my_uploads, name="my_uploads"),

    path("add/", views.add_activity, name="add_activity"),

    # NEU: Über mich und Kontakt
    path("about/", views.about, name="about"),

    path("about/edit/", views.about_edit, name="about_edit"),

    path("contact/", views.contact, name="contact"),

    path("register/", views.register, name="register"),

    path("accounts/login/", views.login_view, name="login"),

    path("accounts/logout/", LogoutView.as_view(), name="logout"),

]
