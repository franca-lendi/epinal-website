# NEU: alle Aktivitäten und Bewertungen übersetzen, die noch keine Übersetzung haben
# (z.B. nachdem du den DeepL-Schlüssel eingetragen hast).
#   python manage.py translate_all
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from guide.models import Activity, Rating
from guide.translate import translate_activity, translate_rating


class Command(BaseCommand):
    help = "Übersetzt alle Aktivitäten und Bewertungen ohne Übersetzung mit DeepL."

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="auch schon übersetzte nochmals übersetzen")

    def handle(self, *args, **options):
        if not settings.DEEPL_API_KEY:
            raise CommandError("Kein DeepL-Schlüssel. Trag in der Datei .env ein: DEEPL_API_KEY=dein-schlüssel")
        activities = Activity.objects.all() if options["all"] else Activity.objects.filter(source_lang="")
        ratings = Rating.objects.all() if options["all"] else Rating.objects.filter(source_lang="")
        done = sum(translate_activity(a) for a in activities)
        done_ratings = sum(translate_rating(r) for r in ratings)
        self.stdout.write(self.style.SUCCESS(f"{done} Aktivitäten und {done_ratings} Bewertungen übersetzt."))
