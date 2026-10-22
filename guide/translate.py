# NEU: Beschreibungen und Bewertungen automatisch übersetzen (DeepL).
# Jeder Text wird einmal beim Speichern übersetzt und gespeichert, nicht bei jedem Seitenaufruf.
# Ohne Schlüssel (DEEPL_API_KEY in .env) passiert nichts, die Website zeigt dann einfach das Original.
import json
import logging
import urllib.request

from django.conf import settings

log = logging.getLogger(__name__)


def deepl_request(texts, target):
    # Schickt mehrere Texte auf einmal an DeepL. Gibt [(übersetzter Text, erkannte Sprache), ...] zurück.
    key = settings.DEEPL_API_KEY
    # Schlüssel der Gratis-Version enden auf ":fx" und gehen an eine andere Adresse
    host = "api-free.deepl.com" if key.endswith(":fx") else "api.deepl.com"
    data = json.dumps({"text": texts, "target_lang": target}).encode()
    request = urllib.request.Request(f"https://{host}/v2/translate", data=data, headers={
        "Authorization": f"DeepL-Auth-Key {key}",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(request, timeout=8) as response:
        result = json.load(response)
    return [(t["text"], t["detected_source_language"].lower()) for t in result["translations"]]


def translate_fields(obj, fields):
    # fields = [("description", "description_tr"), ...]. Erkennt die Sprache selbst:
    # deutsch geschrieben -> französisch übersetzen, französisch geschrieben -> deutsch übersetzen.
    if not settings.DEEPL_API_KEY:
        return False
    filled = [(source, target) for source, target in fields if getattr(obj, source)]
    if not filled:
        return False
    texts = [getattr(obj, source) for source, _target in filled]
    try:
        result = deepl_request(texts, "FR")
        # Sprache vom längsten Text nehmen (bei einem Namen allein irrt sich DeepL eher)
        longest = max(range(len(texts)), key=lambda i: len(texts[i]))
        source_lang = result[longest][1]
        if source_lang == "fr":
            result = deepl_request(texts, "DE")
        elif source_lang != "de":
            source_lang = "de"  # andere Sprache: wie Deutsch behandeln, also ins Französische
    except Exception as error:  # kein Internet, Kontingent aufgebraucht, falscher Schlüssel ...
        log.warning("DeepL-Übersetzung ging nicht: %s", error)
        return False
    obj.source_lang = source_lang
    for (source, target), (text, _lang) in zip(filled, result):
        setattr(obj, target, text)
    for source, target in fields:
        if not getattr(obj, source):
            setattr(obj, target, "")
    obj.save(update_fields=["source_lang"] + [target for _source, target in fields])
    return True


def translate_activity(activity):
    return translate_fields(activity, [("title", "title_tr"), ("description", "description_tr"),
                                       ("hours_note", "hours_note_tr"), ("transport_note", "transport_note_tr")])


def translate_rating(rating):
    return translate_fields(rating, [("title", "title_tr"), ("text", "text_tr")])
