"""Hisobot/diagramma ma'lumotini Excel (.xlsx) yoki CSV ga — barcha eksportlar uchun bitta joy.

Har katak formula in'ektsiyasidan himoyalangan (excel_row). CSV — Excel'da to'g'ri ochilishi uchun
UTF-8 BOM va ";" ajratuvchi (o'zbek/rus mintaqa sozlamasida Excel vergulni ustun deb olmaydi).
"""

from __future__ import annotations

from django.http import HttpResponse

from .format import excel_row

FORMATS = ("xlsx", "csv")


def table_response(fmt: str, filename: str, sheets: list) -> HttpResponse:
    """sheets: [(varaq_nomi, sarlavhalar, qatorlar), ...]. CSV — faqat birinchi varaq."""
    if fmt == "csv":
        import csv
        import io

        _title, headers, rows = sheets[0]
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(headers)
        for r in rows:
            w.writerow(excel_row(r))
        resp = HttpResponse("﻿" + buf.getvalue(), content_type="text/csv; charset=utf-8")
    else:
        import openpyxl

        fmt = "xlsx"
        wb = openpyxl.Workbook(write_only=True)
        for title, headers, rows in sheets:
            ws = wb.create_sheet(str(title)[:31])
            ws.append(headers)
            for r in rows:
                ws.append(excel_row(r))
        resp = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        wb.save(resp)
    resp["Content-Disposition"] = f'attachment; filename="{filename}.{fmt}"'
    return resp


def day_rows(shop, start, end, extra=False) -> tuple[list, list]:
    """Do'konning kunma-kun ko'rsatkichlari (savdo, cheklar, chegirma, deklaratsiya, rostlik).

    Kichik yoki bo'sh kun ham qatorda turadi (0) — sana tushib qolmaydi. extra=True — nazoratchi uchun
    rostlik qismlari va yashirilgan savdo ham.
    """
    from datetime import timedelta

    from django.db.models import Count, Sum
    from django.db.models.functions import TruncDate
    from django.utils import timezone

    from apps.analytics.models import DailyScore
    from apps.core.dates import days_between
    from apps.sales.models import Sale

    sales = {
        r["d"]: r
        for r in Sale.objects.filter(shop=shop, **days_between("created_at", start, end))
        .annotate(d=TruncDate("created_at", tzinfo=timezone.get_current_timezone()))
        .values("d")
        .annotate(n=Count("id"), t=Sum("total"), disc=Sum("discount"))
    }
    scores = {s.date: s for s in DailyScore.objects.filter(shop=shop, date__range=(start, end))}
    headers = [
        "Sana",
        "Cheklar soni",
        "Savdo (so'm)",
        "Chegirma (so'm)",
        "Deklaratsiya (so'm)",
        "Rostlik (%)",
        "Holat",
    ]
    if extra:
        headers += [
            "Kassa mosligi (%)",
            "Kamera (%)",
            "Qoldiq (%)",
            "Narx (%)",
            "Yashirilgan savdo (so'm)",
        ]
    rows = []
    d = start
    while d <= end:
        sa, sc = sales.get(d, {}), scores.get(d)
        measured = bool(sc and sc.measured)
        row = [
            d.strftime("%d.%m.%Y"),
            sa.get("n", 0),
            int(sa.get("t") or 0),
            int(sa.get("disc") or 0),
            int(sc.cash_amount) if sc else 0,
            sc.truth_pct if measured else "",
            "o'lchangan" if measured else ("o'lchanmagan" if sc else "hisoblanmagan"),
        ]
        if extra:
            parts = (sc.parts if sc else {}) or {}
            row += [
                parts.get("cash", ""),
                parts.get("camera", ""),
                parts.get("stock", ""),
                parts.get("price", ""),
                int(sc.hidden_sales) if sc else 0,
            ]
        rows.append([("" if v is None else v) for v in row])
        d += timedelta(days=1)
    return headers, rows


def summary_rows(shop, start, end, rows) -> list:
    """Umumiy varaq: davr yig'indilari (kun qatorlaridan)."""
    total = sum(r[2] for r in rows)
    checks = sum(r[1] for r in rows)
    measured = [r[5] for r in rows if r[5] != ""]
    return [
        ["Do'kon", f"№{shop.number} {shop.owner_name or ''}".strip()],
        ["Bozor", shop.market.name if shop.market_id else ""],
        ["Davr", f"{start:%d.%m.%Y} — {end:%d.%m.%Y}"],
        ["Jami savdo (so'm)", total],
        ["Cheklar soni", checks],
        ["O'rtacha chek (so'm)", total // checks if checks else 0],
        ["Jami chegirma (so'm)", sum(r[3] for r in rows)],
        ["Jami deklaratsiya (so'm)", sum(r[4] for r in rows)],
        [
            "O'rtacha rostlik (%, o'lchangan kunlar)",
            round(sum(measured) / len(measured)) if measured else "o'lchanmagan",
        ],
        ["O'lchangan kunlar", f"{len(measured)} / {len(rows)}"],
    ]
