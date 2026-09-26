"""Rus tili qamrovi: shablon matnlari va model tanlovlari static/js/ru.js da bo'lishi shart.

i18n.js mantiqi takrorlanadi: aniq moslik → bo'shliq normallashtirilgan → oxirgi tinish belgisi
(:→»·) → bo'laklar (RU_FRAGMENTS). Yangi matn qo'shib, tarjimasini unutsangiz — test yiqiladi.
"""

import json
import re
from html.parser import HTMLParser
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.utils.encoding import force_str

BASE = Path(settings.BASE_DIR)
_STR = r'"((?:[^"\\\n]|\\.)*)"'  # bitta qator ichidagi JS satri


def _load_ru():
    src = (BASE / "static/js/ru.js").read_text(encoding="utf-8")
    dict_part, frag_part = src.split("window.RU_FRAGMENTS", 1)
    # Bir qatorda bir nechta kalit bo'lishi mumkin: "a": "b", "c": "d",
    keys = {json.loads(f'"{m}"') for m in re.findall(rf"{_STR}\s*:", dict_part)}
    frags = [json.loads(f'"{m}"') for m in re.findall(rf"\[\s*{_STR}\s*,", frag_part)]
    return keys, frags


RU, FRAGS = _load_ru()


def translated(text):
    key = text.strip()
    norm = re.sub(r"\s+", " ", key)
    if key in RU or norm in RU:
        return True
    m = re.match(r"^(.+?)\s*([:→»·]+)$", norm)
    if m and m.group(1) in RU:
        return True
    return any(f in re.sub(r"\s+", " ", text) for f in FRAGS)


# Ataylab tarjima qilinmaydi: brend, texnik atamalar, o'zbekcha misol (tahlilchi o'zbekcha tushunadi)
ALLOWED = {"Bozor Nazorat", "Excel", "TOP", "Token", "RTSP (substream)", "SMS",
           "«pomidor o'n besh kilo sakkiz mingdan, kartoshka 2 qop»"}


class _Text(HTMLParser):
    HIDE = {"script", "style", "code", "textarea", "title"}
    VOID = {"br", "img", "input", "meta", "link", "hr", "source", "use", "path", "circle", "rect"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.chunks = [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        hidden = bool(self.stack and self.stack[-1][1]) or "data-noloc" in a or tag in self.HIDE
        if tag not in self.VOID:
            self.stack.append((tag, hidden))

    def handle_endtag(self, tag):
        if tag in [t for t, _ in self.stack]:
            while self.stack and self.stack.pop()[0] != tag:
                pass

    def handle_data(self, d):
        if not (self.stack and self.stack[-1][1]):
            self.chunks.append(d)


def _template_pieces():
    comment = re.compile(r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", re.S)
    tags = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}", re.S)
    for p in sorted((BASE / "templates").glob("**/*.html")):
        if p.name == "styleguide.html":  # faqat dizayn namoyishi
            continue
        parser = _Text()
        parser.feed(tags.sub("\x00", comment.sub(" ", p.read_text(encoding="utf-8"))))
        for chunk in parser.chunks:
            for piece in chunk.split("\x00"):
                s = re.sub(r"\s+", " ", piece).strip()
                if (len(s) >= 3 and re.search(r"[A-Za-z]{3,}", s) and not re.search(r"[\u0400-\u04FF]", s)
                        and '="' not in s and "=>" not in s and s not in ALLOWED
                        and s not in {"accent", "bad", "primary", "warn"}
                        and not s.startswith(("http", "rtsp:", "/"))):
                    yield p.relative_to(BASE), piece, s


def test_every_template_text_has_russian():
    missing = sorted({(str(p), s) for p, piece, s in _template_pieces()
                      if not translated(piece) and not translated(s)
                      and not s.endswith("— Bozor Nazorat")})  # sarlavha qismlab tarjima qilinadi
    assert not missing, "ru.js da tarjimasi yo'q:\n" + "\n".join(f"{p}: {s}" for p, s in missing[:40])


def test_every_model_choice_has_russian():
    missing = set()
    for model in apps.get_models():
        if not model.__module__.startswith("apps."):
            continue
        for field in model._meta.get_fields():
            for _value, label in getattr(field, "choices", None) or []:
                label = force_str(label)
                if label not in RU and not re.search(r"[\u0400-\u04FF]", label):
                    missing.add(f"{model.__name__}.{field.name}: {label}")
    assert not missing, "ru.js da tanlov tarjimasi yo'q:\n" + "\n".join(sorted(missing))
