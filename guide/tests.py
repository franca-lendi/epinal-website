import io
import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image as PILImage

import datetime

from .models import Activity, ActivityImage, Category, ContactMessage, Favorite, Location, Rating, Report, SiteInfo, VisitCounter

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
        self.category = Category.objects.get(name="Fussball")  # Unterkategorie aus Migration 0014

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
            "postal_code": "88000",
            "city": "Épinal",
            "latitude": "48.1752000",
            "longitude": "6.4569000",
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

    def test_address_saves_postcode_and_coordinates(self):
        self.client.login(username="anna", password="geheim12345")
        self.client.post(reverse("add_activity"), self.form_data())
        location = Activity.objects.get().location
        self.assertEqual(location.postal_code, "88000")
        self.assertAlmostEqual(float(location.latitude), 48.1752)
        self.assertAlmostEqual(float(location.longitude), 6.4569)
        self.assertEqual(str(location), "2 Faubourg de Poissompré, 88000 Épinal")
        # Detailseite zeigt die Karte mit Punkt statt Komma in den Koordinaten
        page = self.client.get(reverse("activity_detail", args=[Activity.objects.get().pk]))
        self.assertContains(page, 'data-lat="48.1752000"')

    def test_address_without_coordinates_rejected(self):
        self.client.login(username="anna", password="geheim12345")
        response = self.client.post(reverse("add_activity"), self.form_data(latitude="", longitude=""))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "wähle eine Adresse aus den Vorschlägen")
        self.assertFalse(Activity.objects.exists())

    def test_add_page_has_map_and_no_visible_comment(self):
        self.client.login(username="anna", password="geheim12345")
        page = self.client.get(reverse("add_activity"))
        self.assertContains(page, 'id="addressMap"')
        self.assertContains(page, "data.geopf.fr/geocodage")
        self.assertNotContains(page, "So funktioniert es")  # Kommentar darf nicht auf der Seite stehen

    def test_edit_form_prefills_coordinates(self):
        self.client.login(username="anna", password="geheim12345")
        self.client.post(reverse("add_activity"), self.form_data())
        activity = Activity.objects.get()
        page = self.client.get(reverse("edit_activity", args=[activity.pk]))
        self.assertContains(page, 'value="48.1752000"')
        self.assertContains(page, 'value="88000"')

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
        self.assertIsNotNone(rating.visited_on)

        # Nochmals bewerten = ändern, nicht doppelt
        self.client.post(reverse("review_activity", args=[activity.pk]), self.review_data(activity, 2))
        self.assertEqual(Rating.objects.filter(user=self.ben).count(), 1)
        self.assertEqual(Rating.objects.get(user=self.ben).rating, 2)

        page = self.client.get(reverse("activity_detail", args=[activity.pk]))
        self.assertContains(page, "Super Abend")
        self.assertContains(page, "★★☆☆☆")

    def test_review_with_photos(self):
        activity = self.make_activity(self.anna)
        self.client.login(username="ben", password="geheim12345")
        data = self.review_data(activity)
        data["photos"] = [fake_photo("a.jpg"), fake_photo("b.jpg")]
        self.client.post(reverse("review_activity", args=[activity.pk]), data)
        self.assertEqual(Rating.objects.count(), 1)
        self.assertEqual(ActivityImage.objects.filter(activity=activity, user=self.ben).count(), 2)

    def test_review_form_order(self):
        # Titel kommt vor dem Text, "Mit wem" gibt es nicht mehr
        activity = self.make_activity(self.anna)
        self.client.login(username="ben", password="geheim12345")
        html = self.client.get(reverse("review_activity", args=[activity.pk])).content.decode()
        self.assertLess(html.index("Titel deiner Bewertung"), html.index("Schreib deine Bewertung"))
        self.assertNotIn("Mit wem", html)
        self.assertIn('enctype="multipart/form-data"', html)

    def test_review_without_text(self):
        # Text ist freiwillig: nur Sterne und Titel reichen
        activity = self.make_activity(self.anna)
        self.client.login(username="ben", password="geheim12345")
        response = self.client.post(reverse("review_activity", args=[activity.pk]),
                                    self.review_data(activity, text=""))
        self.assertRedirects(response, reverse("activity_detail", args=[activity.pk]))
        self.assertEqual(Rating.objects.get().text, "")

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

        # Spam blendet NICHT aus, nur "Unangemessen"
        activity.refresh_from_db()
        self.assertEqual(activity.status, "published")

        # "error" ist beim normalen Melden nicht erlaubt, Fehler melden ohne Text auch nicht
        self.client.post(reverse("report_activity", args=[activity.pk]), {"reason": "error"})
        self.client.post(reverse("report_error", args=[activity.pk]), {"description": ""})
        self.assertEqual(Report.objects.count(), 2)


class CategorySuggestionTests(TestCase):
    """NEU: bei "Andere" eine eigene Sportart vorschlagen"""

    def setUp(self):
        self.anna = User.objects.create_user("anna", "anna@test.ch", "geheim12345")
        self.client.force_login(self.anna)
        self.andere = Category.objects.get(name="Andere")

    def post(self, category, suggestion):
        return self.client.post(reverse("add_activity"), {
            "title": "Rudern auf der Mosel", "category": category.pk, "new_category": suggestion,
            "description": "x", "address": "Quai", "postal_code": "88000", "city": "Épinal",
            "latitude": "48.17", "longitude": "6.45", "price": "0",
        })

    def test_suggestion_creates_hidden_subcategory(self):
        self.post(self.andere, "Rudern")
        activity = Activity.objects.get(title="Rudern auf der Mosel")
        self.assertEqual(activity.category.name, "Rudern")
        self.assertEqual(activity.category.parent.name, "Sport & Bewegung")
        self.assertFalse(activity.category.approved)
        # noch nicht im Filter, aber die Aktivität zählt bei Sport mit
        sport = next(c for c in self.client.get(reverse("activities")).context["categories"] if c.name == "Sport & Bewegung")
        self.assertNotIn("Rudern", [c.name for c in sport.subs])
        self.assertEqual(sport.activity_count, 1)

    def test_same_suggestion_not_twice(self):
        self.post(self.andere, "Rudern")
        self.post(self.andere, "rudern")
        self.assertEqual(Category.objects.filter(name__iexact="rudern").count(), 1)

    def test_suggestion_ignored_without_andere(self):
        self.post(Category.objects.get(name="Fussball"), "Rudern")
        self.assertFalse(Category.objects.filter(name="Rudern").exists())


class SearchFilterFavoriteTests(TestCase):
    """Suche, Filter und Favoriten"""

    def setUp(self):
        self.anna = User.objects.create_user("anna", "anna@test.ch", "geheim12345")
        self.sport = Category.objects.get(name="Sport & Bewegung")
        self.park = Category.objects.get(name="Natur & Parks")       # umbenannt in Migration 0012
        self.museum = Category.objects.get(name="Kultur & Museen")   # umbenannt in Migration 0012

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

    def test_category_order_and_count(self):
        # Reihenfolge wie festgelegt, Zahl = nur veröffentlichte Aktivitäten (der Entwurf zählt nicht)
        response = self.client.get(reverse("activities"))
        categories = list(response.context["categories"])
        self.assertEqual([c.name for c in categories], [
            "Sport & Bewegung", "Natur & Parks", "Essen & Trinken", "Ausgang & Nightlife", "Kultur & Museen",
            "Jugendzentren & Vereine", "Spiel & Action", "Märkte & Einkaufen",
        ])
        counts = {c.name: c.activity_count for c in categories}
        self.assertEqual(counts["Sport & Bewegung"], 2)
        self.assertEqual(counts["Natur & Parks"], 1)
        self.assertEqual(counts["Essen & Trinken"], 0)

    def test_main_category_includes_subcategories(self):
        # Fussball gehört zu Sport: zählt bei Sport mit und erscheint beim Filter "Sport"
        fussball = Category.objects.get(name="Fussball")
        location = Location.objects.create(city="Épinal")
        Activity.objects.create(user=self.anna, category=fussball, location=location, title="Stade", description="x")
        response = self.client.get(reverse("activities"))
        sport = next(c for c in response.context["categories"] if c.name == "Sport & Bewegung")
        self.assertEqual(sport.activity_count, 3)
        self.assertEqual({c.name: c.activity_count for c in sport.subs}["Fussball"], 1)
        self.assertIn("Stade", self.titles(category=self.sport.pk))
        self.assertEqual(self.titles(category=fussball.pk), {"Stade"})
        self.assertIn("Stade", self.titles(q="sport"))  # Suche findet auch über die Hauptkategorie

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


class ModerationAndUploadsTests(TestCase):
    """Unangemessen melden blendet aus, "Füge hinzu"-Karte bei Deine Uploads"""

    def setUp(self):
        self.anna = User.objects.create_user("anna", "anna@test.ch", "geheim12345")
        self.ben = User.objects.create_user("ben", "ben@test.ch", "geheim12345")
        category = Category.objects.get(name="Sport & Bewegung")
        location = Location.objects.create(address="Rue 1", city="Épinal")
        self.activity = Activity.objects.create(user=self.anna, category=category, location=location,
                                                title="Patinoire", description="Eishalle", status="published")

    def test_inappropriate_hides_activity(self):
        self.client.login(username="ben", password="geheim12345")
        response = self.client.post(reverse("report_activity", args=[self.activity.pk]), {"reason": "inappropriate"})
        self.assertRedirects(response, reverse("activities"))
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.status, "review")

        # weg aus der Liste und der Suche, Detailseite für andere nicht mehr erreichbar
        self.assertNotContains(self.client.get(reverse("activities")), "Patinoire")
        self.assertEqual(self.client.get(reverse("activity_detail", args=[self.activity.pk])).status_code, 404)

        # die Besitzerin sieht sie noch, mit Hinweis
        self.client.login(username="anna", password="geheim12345")
        self.assertContains(self.client.get(reverse("activity_detail", args=[self.activity.pk])), "In Prüfung")
        self.assertContains(self.client.get(reverse("my_uploads")), "In Prüfung")

    def test_owner_cannot_bypass_review_by_editing(self):
        self.activity.status = "review"
        self.activity.save()
        self.client.login(username="anna", password="geheim12345")
        self.client.post(reverse("edit_activity", args=[self.activity.pk]), {
            "title": "Patinoire neu", "category": self.activity.category_id, "description": "x",
            "address": "Rue 1", "city": "Épinal", "price": "0", "latitude": "48.17", "longitude": "6.45",
        })
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.title, "Patinoire neu")
        self.assertEqual(self.activity.status, "review")

    def test_add_card_first_also_in_drafts(self):
        self.client.login(username="anna", password="geheim12345")
        for tab in ["all", "drafts"]:
            html = self.client.get(reverse("my_uploads") + f"?tab={tab}").content.decode()
            self.assertIn("add-card", html)
        html = self.client.get(reverse("my_uploads")).content.decode()
        self.assertLess(html.index("add-card"), html.index("Patinoire"))  # vor der ersten Aktivität


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class AboutContactTests(TestCase):
    """Über mich (nur Admin bearbeitet), Kontaktformular, Footer"""

    def setUp(self):
        self.admin = User.objects.create_user("franc", "f@test.ch", "geheim12345", is_staff=True)
        self.anna = User.objects.create_user("anna", "anna@test.ch", "geheim12345")

    def test_about_public_with_default_text(self):
        page = self.client.get(reverse("about"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Austausch in Épinal")
        self.assertNotContains(page, reverse("about_edit"))  # kein Bearbeiten-Knopf für Besucher

    def test_only_staff_can_edit(self):
        self.client.login(username="anna", password="geheim12345")
        self.assertEqual(self.client.get(reverse("about_edit")).status_code, 302)  # weg zum Admin-Login
        self.client.post(reverse("about_edit"), {"name": "Hacker"})
        self.assertNotEqual(SiteInfo.load().name, "Hacker")

    def test_staff_edits_with_photo(self):
        self.client.login(username="franc", password="geheim12345")
        self.assertContains(self.client.get(reverse("about")), "Bearbeiten")
        response = self.client.post(reverse("about_edit"), {
            "photo": fake_photo("ich.jpg"), "name": "Franca", "tagline": "Maturaarbeit 2026",
            "intro": "Hallo!", "text": "Absatz eins.\n\nAbsatz zwei.", "email": "ich@test.ch",
            "instagram": "epinalguide", "other_link": "",
        })
        self.assertRedirects(response, reverse("about"))
        info = SiteInfo.load()
        self.assertEqual(info.name, "Franca")
        self.assertTrue(info.photo)
        page = self.client.get(reverse("about"))
        self.assertContains(page, "<p>Absatz zwei.</p>", html=True)
        contact = self.client.get(reverse("contact"))
        self.assertContains(contact, "ich@test.ch")
        self.assertContains(contact, "@epinalguide")

    def test_contact_form_saves_message(self):
        response = self.client.post(reverse("contact"), {
            "name": "Lea", "email": "lea@test.ch", "topic": "tip", "message": "Kennt ihr das Café X?", "website": "",
        })
        self.assertRedirects(response, reverse("contact"))
        self.assertEqual(ContactMessage.objects.get().topic, "tip")

    def test_contact_honeypot_blocks_bots(self):
        self.client.post(reverse("contact"), {
            "name": "Bot", "email": "bot@test.ch", "topic": "other", "message": "Spam", "website": "http://spam",
        })
        self.assertFalse(ContactMessage.objects.exists())

    def test_contact_topic_preselected_and_footer(self):
        page = self.client.get(reverse("contact") + "?topic=problem")
        self.assertEqual(page.context["form"]["topic"].value(), "problem")
        self.assertContains(page, "site-footer")
        self.assertContains(page, "Problem melden")


class LoginAndVisitTests(TestCase):
    """Login mit E-Mail, Besucherzähler insgesamt"""

    def setUp(self):
        self.anna = User.objects.create_user("anna", "anna@test.ch", "geheim12345")

    def login(self, username, password="geheim12345"):
        return self.client.post(reverse("login"), {"username": username, "password": password},
                                HTTP_X_REQUESTED_WITH="XMLHttpRequest").json()

    def test_login_with_username_or_email(self):
        self.assertTrue(self.login("anna")["ok"])
        self.client.logout()
        self.assertTrue(self.login("Anna@Test.ch")["ok"])  # Gross/klein egal
        self.client.logout()
        self.assertFalse(self.login("anna@test.ch", "falsch")["ok"])
        self.assertFalse(self.login("niemand@test.ch")["ok"])

    def test_username_without_at(self):
        response = self.client.post(reverse("register"), {
            "username": "a@b.ch", "email": "neu@test.ch", "password1": "SehrGeheim123!", "password2": "SehrGeheim123!",
        }, HTTP_X_REQUESTED_WITH="XMLHttpRequest").json()
        self.assertFalse(response["ok"])
        self.assertIn("username", response["errors"])

    def test_contact_without_email_sending(self):
        self.client.post(reverse("contact"), {
            "name": "Lea", "email": "lea@test.ch", "topic": "other", "message": "Hallo", "website": "",
        })
        self.assertEqual(ContactMessage.objects.count(), 1)  # steht im Admin

    def test_visitor_counted_once_in_total(self):
        self.client.get(reverse("activities"))
        self.client.get(reverse("about"))
        self.client.get(reverse("contact"))
        counter = VisitCounter.load()
        self.assertEqual(counter.visitors, 1)    # dieselbe Person
        self.assertEqual(counter.page_views, 3)  # drei Seiten

        other = self.client_class()              # zweite Person (anderer Browser)
        other.get(reverse("activities"))
        counter.refresh_from_db()
        self.assertEqual(counter.visitors, 2)

    def test_bots_admin_and_staff_not_counted(self):
        self.client.get(reverse("activities"), HTTP_USER_AGENT="Googlebot/2.1")
        self.client.get("/admin/login/")
        staff = User.objects.create_user("franc", "f@test.ch", "geheim12345", is_staff=True)
        self.client.force_login(staff)
        self.client.get(reverse("activities"))
        self.assertEqual(VisitCounter.load().page_views, 0)

    def test_about_shows_visitors(self):
        counter = VisitCounter.load()
        counter.visitors = 42
        counter.save()
        page = self.client.get(reverse("about"))
        # Dieser Besuch wird erst nach dem Anzeigen gezählt, erscheint also beim nächsten Mal
        self.assertEqual(page.context["stats"]["visitors"], 42)
        self.assertContains(page, "Besucher:innen")

