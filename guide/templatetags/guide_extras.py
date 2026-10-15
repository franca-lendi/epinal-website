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
