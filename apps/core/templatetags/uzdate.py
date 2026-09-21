"""O'zbekcha (lotin) sana formati — Django uz lokali rus oy nomini berardi.
Lotin chiqadi; kirill rejimida i18n.js avtomatik o'giradi."""

from django import template

register = template.Library()

# Indeks 1..12
UZ_MONTHS = [
    "", "yanvar", "fevral", "mart", "aprel", "may", "iyun",
    "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr",
]


@register.filter
def uzdate(value):
    """21-sentabr 2026"""
    if not value:
        return ""
    try:
        return f"{value.day}-{UZ_MONTHS[value.month]} {value.year}"
    except (AttributeError, IndexError):
        return str(value)


@register.filter
def uzdatetime(value):
    """21-sentabr 2026, 14:30"""
    if not value:
        return ""
    try:
        return f"{value.day}-{UZ_MONTHS[value.month]} {value.year}, {value:%H:%M}"
    except (AttributeError, IndexError, ValueError):
        return str(value)
