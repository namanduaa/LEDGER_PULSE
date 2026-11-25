from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect
from django.views.generic import CreateView

from .forms import EmailLoginForm, SignupForm


class EmailLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = EmailLoginForm
    redirect_authenticated_user = True


class SignupView(CreateView):
    template_name = "accounts/signup.html"
    form_class = SignupForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("ledger:dashboard")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save()
        login(self.request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(self.request, f"Welcome to LedgerPulse, {user.get_short_name()}!")
        return redirect("ledger:dashboard")


class AppLogoutView(LogoutView):
    pass
