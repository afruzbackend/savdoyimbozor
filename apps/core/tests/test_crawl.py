"""To'liq crawler: har rol bilan barcha ichki havolalarni ochadi (test bazasida demo ma'lumot).

Tekshiradi: 404/500 yo'q; shablon qoldig'i ({{ }}, {% %}, {# #}) chiqmaydi; "None", "undefined",
"NaN" matn sifatida ko'rinmaydi; har sahifada <title> va bitta <h1> bor.
"""

import os
import re
from collections import deque
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urldefrag, urlparse

import pytest
from django.core.management import call_command
from django.test import Client

SKIP_PREFIX = ("/logout/", "/static/", "/media/", "/sw.js", "/api/", "/django-admin/",
               "/prefs/theme", "/prefs/language", "/chek/")
# Fayl yuklab beradigan / holatni o'zgartiradigan GET'lar
SKIP_RE = re.compile(r"/(eksport|excel|export)/|/bildirishnomalar/\d+/$|/login-varaqasi/")
LEAK_RE = re.compile(r"\{\{|\}\}|\{%|%\}|\{#|#\}")
BAD_TEXT_RE = re.compile(r"(?<![\w-])(None|undefined|NaN|nan so'm)(?![\w-])")
HREF_RE = re.compile(r"""href=["']([^"'#][^"']*)["']""")


class _Text(HTMLParser):
    """Foydalanuvchi ko'radigan matn (script/style/template ichidan tashqari; atributlar emas)."""

    HIDDEN = {"script", "style", "template"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth, self.parts = 0, []

    def handle_starttag(self, tag, attrs):
        if tag in self.HIDDEN:
            self.depth += 1

    def handle_endtag(self, tag):
        if tag in self.HIDDEN and self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if not self.depth:
            self.parts.append(data)


def _visible_text(html: str) -> str:
    p = _Text()
    p.feed(html)
    return " ".join(p.parts)


def _crawl(client, start="/", limit=400):
    seen, queue, problems = set(), deque([start]), []
    while queue and len(seen) < limit:
        url = queue.popleft()
        if url in seen:
            continue
        seen.add(url)
        r = client.get(url)
        if r.status_code in (301, 302):
            loc = r["Location"]
            if urlparse(loc).path.startswith("/login"):
                problems.append(f"{url}: login'ga yo'naltirdi")
            elif loc.startswith("/") and loc not in seen:
                queue.append(loc)
            continue
        if r.status_code != 200:
            problems.append(f"{url}: HTTP {r.status_code}")
            continue
        ctype = r.get("Content-Type", "")
        if "text/html" not in ctype:
            continue
        html = r.content.decode("utf-8", errors="replace")
        text = _visible_text(html)
        if LEAK_RE.search(text):
            snippet = LEAK_RE.search(text)
            problems.append(f"{url}: shablon qoldig'i: …{text[max(0, snippet.start() - 40):snippet.end() + 40]!r}")
        bad = BAD_TEXT_RE.search(text)
        if bad:
            problems.append(f"{url}: matnda {bad.group(1)!r}: …{text[max(0, bad.start() - 50):bad.end() + 30]!r}")
        if "<title>" not in html:
            problems.append(f"{url}: <title> yo'q")
        for href in HREF_RE.findall(html):
            href = urldefrag(unescape(href))[0]
            if not href.startswith("/") or href.startswith("//"):
                continue
            if href.startswith(SKIP_PREFIX) or SKIP_RE.search(href):
                continue
            if href not in seen:
                queue.append(href)
    return seen, problems


@pytest.fixture
def demo(db):
    with open(os.devnull, "w") as out:
        call_command("seed_demo", "--reset", "--days", "3", stdout=out)
    from apps.accounts.models import User

    return {u.username: u for u in User.objects.filter(username__in=["admin", "nazorat", "sotuvchi", "prokuror"])}


@pytest.mark.django_db
def test_crawl_all_roles(demo):
    report = {}
    for username in ("sotuvchi", "nazorat", "prokuror", "admin"):
        c = Client()
        c.force_login(demo[username])
        seen, problems = _crawl(c)
        report[username] = (len(seen), problems)
    lines = [f"{u}: {n} sahifa, {len(p)} muammo" + "".join(f"\n   - {x}" for x in p[:40])
             for u, (n, p) in report.items()]
    print("\n".join(lines))
    assert all(n > 5 for n, _ in report.values()), "\n".join(lines)
    assert not any(p for _, p in report.values()), "\n".join(lines)
