from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .models import PaymentType, Sale, SaleItem, StockWriteOff


def _seller_shop(request):
    """Sotuvchining do'koni; boshqa rol uchun None."""
    return getattr(request.user, "assigned_shop", None)


@login_required
def sale_create(request):
    """Sotuvchi savdo kiritadi (PWA'dagi asosiy ekran)."""
    shop = _seller_shop(request)
    if shop is None:
        messages.error(request, "Sizga do'kon biriktirilmagan.")
        return redirect("dashboard:home")

    if request.method == "POST":
        try:
            total = Decimal(request.POST.get("total_amount", "0") or "0")
        except InvalidOperation:
            total = Decimal("0")
        sale = Sale.objects.create(
            shop=shop,
            seller=request.user,
            total_amount=total,
            payment_type=request.POST.get("payment_type", PaymentType.CASH),
            is_wholesale=bool(request.POST.get("is_wholesale")),
            note=request.POST.get("note", "")[:200],
        )
        # Ixtiyoriy mahsulot qatorlari
        names = request.POST.getlist("product_name")
        qtys = request.POST.getlist("quantity")
        units = request.POST.getlist("unit")
        prices = request.POST.getlist("unit_price")
        for i, name in enumerate(names):
            if not name.strip():
                continue
            try:
                SaleItem.objects.create(
                    sale=sale, product_name=name.strip(),
                    quantity=Decimal(qtys[i] or "1"),
                    unit=units[i] if i < len(units) else "dona",
                    unit_price=Decimal(prices[i] or "0"),
                )
            except (InvalidOperation, IndexError):
                continue
        messages.success(request, f"Savdo qo'shildi: {total} so'm")
        if request.htmx:
            return render(request, "events/_sale_ok.html", {"sale": sale})
        return redirect("events:sale_create")

    today_sales = Sale.objects.filter(shop=shop, created_at__date__isnull=False)
    return render(request, "events/sale_form.html", {
        "shop": shop,
        "payment_types": PaymentType.choices,
    })


@login_required
def writeoff_create(request):
    """Hisobdan chiqarish — foto majburiy."""
    shop = _seller_shop(request)
    if shop is None:
        messages.error(request, "Sizga do'kon biriktirilmagan.")
        return redirect("dashboard:home")

    if request.method == "POST" and request.FILES.get("photo"):
        try:
            qty = Decimal(request.POST.get("quantity", "0") or "0")
        except InvalidOperation:
            qty = Decimal("0")
        StockWriteOff.objects.create(
            shop=shop, seller=request.user,
            product_name=request.POST.get("product_name", "")[:150],
            quantity=qty,
            unit=request.POST.get("unit", "kg"),
            photo=request.FILES["photo"],
            reason=request.POST.get("reason", "")[:200],
        )
        messages.success(request, "Hisobdan chiqarish qayd etildi.")
        return redirect("events:sale_create")

    return render(request, "events/writeoff_form.html", {"shop": shop})
