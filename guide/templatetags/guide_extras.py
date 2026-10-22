from django import template

register = template.Library()


@register.filter
def stars(value):
    # 3.6 -> "★★★★☆"  (gerundet auf ganze Sterne)
    if not value:
        return "☆☆☆☆☆"
    full = int(round(float(value)))
    full = max(0, min(5, full))
    return "★" * full + "☆" * (5 - full)


@register.filter
def mask_name(name):
    # NEU: Benutzername bei Bewertungen abkürzen, z.B. "franca" -> "fr***", "Bo" -> "B***"
    # Immer drei Sternchen, damit man auch die Länge des Namens nicht sieht.
    name = str(name or "")
    keep = 1 if len(name) <= 4 else 2
    return name[:keep] + "***"
