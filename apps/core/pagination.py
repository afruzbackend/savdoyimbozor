"""Ro'yxatlar uchun oddiy sahifalash yordamchisi (katta bozorda ham tez)."""

from django.core.paginator import Paginator


def paginate(request, queryset, per_page=50):
    """Queryset'ni sahifalaydi. `?page=` GET parametridan oladi.

    Qaytadi: Page obyekti (shablonda `page.object_list`, `page.has_next` va h.k.).
    """
    paginator = Paginator(queryset, per_page)
    number = request.GET.get("page") or 1
    return paginator.get_page(number)  # noto'g'ri/chegaradan tashqari — xavfsiz clamp
