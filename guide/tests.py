import io
import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image as PILImage

import datetime

from .models import Activity, ActivityImage, Category, Favorite, Location, Rating, Report

TEMP_MEDIA = tempfile.mkdtemp()


def fake_photo(name="foto.jpg"):
    # Erstellt ein kleines echtes JPG im Speicher
    buffer = io.BytesIO()
    PILImage.new("RGB", (20, 20), "green").save(buffer, "JPEG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class GuideTests(TestCase):
    """Starten mit: python manage.py test guide"""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.anna = User.objects.create_user("anna", "anna@test.ch", "geheim12345")
        self.ben = User.objects.create_user("ben", "ben@test.ch", "geheim12345")
        self.category = Category.objects.get(name="Sport & Bewegung")  # kommt aus Migration 0004

    def make_activity(self, user, status="published", title="Eislaufen"):
        location = Location.objects.create(address="2 Faubourg de Poissompré", city="Épinal")
        return Activity.objects.create(user=user, category=self.category, location=location,
                                       title=title, description="Eishalle", status=status)

    def form_data(self, **extra):
        data = {
            "title": "Patinoire",
            "category": self.category.pk,
            "description": "Eislaufen in Épinal",
            "address": "2 Faubourg de Poissompré",
            "city": "Épinal",
            "price": "0",
            "duration_minutes": "90",
            "website": "",
            "phone": "",
            "email": "",
            "opening_hours": "Mo–Fr: 10:00–18:00",
        }
        data.update(extra)
        return data

    # ---------- Hinzufügen ----------

    def test_add_needs_login(self):
        response = self.client.get(reverse("add_activity"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_add_goes_to_review(self):
        self.client.login(username="anna", password="geheim12345")
        response = self.client.post(reverse("add_activity"), self.form_data(image=fake_photo()))
        activity = Activity.objects.get(title="Patinoire")
        self.assertRedirects(response, reverse("review_activity", args=[activity.pk]))
        self.assertEqual(activity.status, "published")

        # sofort bei den Aktivitäten sichtbar und klickbar
        page = self.client.get(reverse("activities"))
        self.assertContains(page, "Patinoire")
        self.assertContains(page, reverse("activity_detail", args=[activity.pk]))

    def test_save_as_draft(self):
        self.client.login(username="anna", password="geheim12345")
        response = self.client.post(reverse("add_activity"), self.form_data(save_draft=""))
        self.assertRedirects(response, reverse("my_uploads"))
        self.assertEqual(Activity.objects.get().status, "draft")
        self.assertNotContains(self.client.get(reverse("activities")), "Patinoire")

    def test_edit_own(self):
        activity = self.make_activity(self.anna)
        self.client.login(username="anna", password="geheim12345")
        response = self.client.post(reverse("edit_activity", args=[activity.pk]),
                                    self.form_data(title="Neuer Name", address="Neue Adresse 1"))
        self.assertRedirects(response, reverse("activity_detail", args=[activity.pk]))
        activity.refresh_from_db()
        self.assertEqual(activity.title, "Neuer Name")
        self.assertEqual(activity.location.address, "Neue Adresse 1")
        self.assertEqual(Location.objects.count(), 1)  # kein zweiter Ort erstellt

    def test_cannot_edit_or_delete_others(self):
        activity = self.make_activity(self.anna)
        self.client.login(username="ben", password="geheim12345")
        self.assertEqual(self.client.get(reverse("edit_activity", args=[activity.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("delete_activity", args=[activity.pk])).status_code, 404)
        self.assertTrue(Activity.objects.filter(pk=activity.pk).exists())

    def test_delete_own(self):
        activity = self.make_activity(self.anna)
        self.client.login(username="anna", password="geheim12345")
        response = self.client.post(reverse("delete_activity", args=[activity.pk]))
        self.assertRedirects(response, reverse("my_uploads"))
        self.assertFalse(Activity.objects.exists())
        self.assertFalse(Location.objects.exists())

    # ---------- Deine Uploads ----------

    def test_my_uploads_tabs_and_sort(self):
        self.make_activity(self.anna, title="Bowling")
        self.make_activity(self.anna, status="draft", title="Kino")
        self.make_activity(self.ben, title="Fremd")
        self.client.login(username="anna", password="geheim12345")

        page = self.client.get(reverse("my_uploads"))
        self.assertContains(page, "Meine Aktivitäten (2)")
        self.assertContains(page, "Entwürfe (1)")
        self.assertContains(page, "Bowling")
        self.assertNotContains(page, "Fremd")

        drafts = self.client.get(reverse("my_uploads") + "?tab=drafts&view=table&sort=rating")
        self.assertContains(drafts, "Kino")
        self.assertNotContains(drafts, "Bowling")

    # ---------- Detail ----------

    def test_draft_hidden_from_others(self):
        draft = self.make_activity(self.anna, status="draft")
        self.assertEqual(self.client.get(reverse("activity_detail", args=[draft.pk])).status_code, 404)
        self.client.login(username="anna", password="geheim12345")
        self.assertEqual(self.client.get(reverse("activity_detail", args=[draft.pk])).status_code, 200)

    def test_detail_page_shows_buttons(self):
        activity = self.make_activity(self.anna)
        page = self.client.get(reverse("activity_detail", args=[activity.pk]))
        for text in ["Bewerten", "Fotos hinzufügen", "Melden", "Fehler melden", "Épinal"]:
            self.assertContains(page, text)

    # ---------- Bewerten ----------

    def review_data(self, activity, rating=4, text="Sehr schöne Eishalle, gute Musik und nicht zu voll."):
        form = self.client.get(reverse("review_activity", args=[activity.pk])).context["form"]
        return {
            "rating": rating,
            "visited": form.fields["visited"].choices[0][0],
            "companions": "friends",
            "text": text,
            "title": "Super Abend",
            "confirm": "on",
        }

    def test_review_create_and_update(self):
        activity = self.make_activity(self.anna)
        self.client.login(username="ben", password="geheim12345")

        response = self.client.post(reverse("review_activity", args=[activity.pk]), self.review_data(activity, 4))
        self.assertRedirects(response, reverse("activity_detail", args=[activity.pk]))
        rating = Rating.objects.get(user=self.ben)
        self.assertEqual(rating.rating, 4)
        self.assertEqual(rating.companions, "friends")
        self.assertIsNotNone(rating.visited_on)

        # Nochmals bewerten = ändern, nicht doppelt
        self.client.post(reverse("review_activity", args=[activity.pk]), self.review_data(activity, 2))
        self.assertEqual(Rating.objects.filter(user=self.ben).count(), 1)
        self.assertEqual(Rating.objects.get(user=self.ben).rating, 2)

        page = self.client.get(reverse("activity_detail", args=[activity.pk]))
        self.assertContains(page, "Super Abend")
        self.assertContains(page, "★★☆☆☆")

    def test_review_too_short(self):
        activity = self.make_activity(self.anna)
        self.client.login(username="ben", password="geheim12345")
        response = self.client.post(reverse("review_activity", args=[activity.pk]),
                                    self.review_data(activity, text="zu kurz"))
        self.assertContains(response, "mindestens 25 Zeichen")
        self.assertFalse(Rating.objects.exists())

    # ---------- Fotos ----------

    def test_add_photos(self):
        activity = self.make_activity(self.anna)
        self.client.login(username="ben", password="geheim12345")
        self.client.post(reverse("add_photos", args=[activity.pk]),
                         {"photos": [fake_photo("a.jpg"), fake_photo("b.jpg")]})
        self.assertEqual(ActivityImage.objects.filter(activity=activity, user=self.ben).count(), 2)

    def test_reject_non_image(self):
        activity = self.make_activity(self.anna)
        self.client.login(username="ben", password="geheim12345")
        fake = SimpleUploadedFile("virus.jpg", b"kein bild", content_type="image/jpeg")
        self.client.post(reverse("add_photos", args=[activity.pk]), {"photos": [fake]})
        self.assertFalse(ActivityImage.objects.exists())

    # ---------- Melden ----------

    def test_report_and_error(self):
        activity = self.make_activity(self.anna)
        self.client.login(username="ben", password="geheim12345")
        self.client.post(reverse("report_activity", args=[activity.pk]), {"reason": "spam"})
        self.client.post(reverse("report_error", args=[activity.pk]), {"description": "Montag geschlossen"})
        self.assertEqual(Report.objects.count(), 2)
        self.assertEqual(Report.objects.get(description="Montag geschlossen").reason, "error")

        # "error" ist beim normalen Melden nicht erlaubt, Fehler melden ohne Text auch nicht
        self.client.post(reverse("report_activity", args=[activity.pk]), {"reason": "error"})
        self.client.post(reverse("report_error", args=[activity.pk]), {"description": ""})
        self.assertEqual(Report.objects.count(), 2)


class SearchFilterFavoriteTests(TestCase):
    """Suche, Filter und Favoriten"""

    def setUp(self):
        self.anna = User.objects.create_user("anna", "anna@test.ch", "geheim12345")
        self.sport = Category.objects.get(name="Sport & Bewegung")
        self.park = Category.objects.get(name="Parks & Natur")
        self.museum = Category.objects.get(name="Museen & Kultur")

        def make(title, category, price=0, date=None, address="", description="Text", status="published"):
            location = Location.objects.create(address=address, city="Épinal")
            return Activity.objects.create(user=self.anna, category=category, location=location, title=title,
                                           description=description, price=price, event_date=date, status=status)

        self.eis = make("Patinoire", self.sport, price=6, address="2 Faubourg de Poissompré")
        self.parc = make("Parc du Château", self.park, description="Grosser Park mit Tieren")
        self.musee = make("Musée de l'Image", self.museum, price=12)
        self.fest = make("Fête foraine", self.sport, price=0, date=datetime.date(2026, 11, 20))
        self.draft = make("Entwurf Park", self.park, status="draft")

    def titles(self, **params):
        response = self.client.get(reverse("activities"), params)
        self.assertEqual(response.status_code, 200)
        return {a.title for a in response.context["activities"]}

    def test_no_filter_shows_all_published(self):
        self.assertEqual(self.titles(), {"Patinoire", "Parc du Château", "Musée de l'Image", "Fête foraine"})

    def test_search_title_description_address_category(self):
        self.assertEqual(self.titles(q="patinoire"), {"Patinoire"})        # Name, Gross/klein egal
        self.assertEqual(self.titles(q="tieren"), {"Parc du Château"})     # Beschreibung
        self.assertEqual(self.titles(q="Poissompré"), {"Patinoire"})       # Adresse
        self.assertEqual(self.titles(q="museen"), {"Musée de l'Image"})    # Kategorie
        self.assertEqual(self.titles(q="park tieren"), {"Parc du Château"})  # alle Wörter müssen passen
        self.assertEqual(self.titles(q="gibtesnicht"), set())

    def test_draft_never_in_results(self):
        self.assertNotIn("Entwurf Park", self.titles(q="park"))

    def test_category_filter_multiple(self):
        response = self.client.get(reverse("activities"), {"category": [self.sport.pk, self.park.pk]})
        titles = {a.title for a in response.context["activities"]}
        self.assertEqual(titles, {"Patinoire", "Fête foraine", "Parc du Château"})

    def test_price_filter(self):
        self.assertEqual(self.titles(max_price=0), {"Parc du Château", "Fête foraine"})
        self.assertEqual(self.titles(max_price=10), {"Parc du Château", "Fête foraine", "Patinoire"})
        self.assertEqual(len(self.titles(max_price=100)), 4)  # ganz rechts = egal
        self.assertEqual(len(self.titles(max_price="quatsch")), 4)  # falsche Eingabe = egal

    def test_date_filter_keeps_undated(self):
        # Fest am 20.11.: im Zeitraum Dezember nicht dabei, die anderen (ohne Datum) schon
        self.assertNotIn("Fête foraine", self.titles(date_from="2026-12-01", date_to="2026-12-31"))
        self.assertIn("Fête foraine", self.titles(date_from="2026-11-01", date_to="2026-11-30"))
        self.assertIn("Patinoire", self.titles(date_from="2026-12-01"))

    def test_combined(self):
        self.assertEqual(self.titles(q="parc", max_price=0, category=self.park.pk), {"Parc du Château"})

    # ---------- Favoriten ----------

    def test_favorite_needs_login(self):
        response = self.client.post(reverse("toggle_favorite", args=[self.eis.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Favorite.objects.exists())
        self.assertEqual(self.client.get(reverse("favorites")).status_code, 302)

    def test_toggle_favorite_ajax(self):
        self.client.login(username="anna", password="geheim12345")
        url = reverse("toggle_favorite", args=[self.eis.pk])
        ajax = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}

        self.assertEqual(self.client.post(url, **ajax).json(), {"ok": True, "is_favorite": True})
        self.assertTrue(Favorite.objects.filter(user=self.anna, activity=self.eis).exists())

        self.assertEqual(self.client.post(url, **ajax).json(), {"ok": True, "is_favorite": False})
        self.assertFalse(Favorite.objects.exists())

    def test_toggle_without_js_redirects_back(self):
        self.client.login(username="anna", password="geheim12345")
        response = self.client.post(reverse("toggle_favorite", args=[self.eis.pk]), {"next": "/activities/?q=eis"})
        self.assertRedirects(response, "/activities/?q=eis", fetch_redirect_response=False)
        # fremde Adresse wird ignoriert
        response = self.client.post(reverse("toggle_favorite", args=[self.eis.pk]), {"next": "https://boese.example"})
        self.assertRedirects(response, reverse("activity_detail", args=[self.eis.pk]), fetch_redirect_response=False)

    def test_favorites_page_and_heart_state(self):
        self.client.login(username="anna", password="geheim12345")
        Favorite.objects.create(user=self.anna, activity=self.parc)
        Favorite.objects.create(user=self.anna, activity=self.musee)

        page = self.client.get(reverse("favorites"))
        self.assertEqual([a.title for a in page.context["activities"]], ["Musée de l'Image", "Parc du Château"])
        self.assertNotContains(page, "Patinoire")

        # auf der Aktivitäten-Seite ist das Herz bei den Favoriten gefüllt
        listing = self.client.get(reverse("activities"))
        favs = {a.title for a in listing.context["activities"] if a.is_favorite}
        self.assertEqual(favs, {"Parc du Château", "Musée de l'Image"})

        detail = self.client.get(reverse("activity_detail", args=[self.parc.pk]))
        self.assertContains(detail, "Gespeichert")

    def test_cannot_favorite_draft(self):
        self.client.login(username="anna", password="geheim12345")
        response = self.client.post(reverse("toggle_favorite", args=[self.draft.pk]))
        self.assertEqual(response.status_code, 404)

