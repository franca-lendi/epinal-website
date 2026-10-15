import io
import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image as PILImage

from .models import Activity, ActivityImage, Category, Location, Rating, Report

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
