from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView

from .forms import RegisterForm


class RegisterView(CreateView):
    form_class = RegisterForm
    template_name = "accounts/register.html"
    success_url = reverse_lazy("chat:index")

    def dispatch(self, request, *args, **kwargs):
        # Login qilgan user register sahifasiga kirmasin
        if request.user.is_authenticated:
            return redirect("chat:index")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)  # ro'yxatdan o'tgach avtomatik login
        return response


class UserLoginView(LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True


class UserLogoutView(LogoutView):
    # Django 5'da logout faqat POST orqali (CSRF himoyasi uchun)
    pass
