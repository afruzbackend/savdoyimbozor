from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import translation


class RoleLoginView(LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True


@login_required
def profile(request):
    if request.method == "POST":
        lang = request.POST.get("language")
        if lang in dict(request.user._meta.get_field("language").choices):
            request.user.language = lang
            request.user.save(update_fields=["language"])
            translation.activate(lang if lang != "uz-cyrl" else "uz")
            request.session["django_language"] = lang
        return redirect("accounts:profile")
    return render(request, "accounts/profile.html")


def do_logout(request):
    logout(request)
    return redirect("accounts:login")
