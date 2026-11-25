from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm

from .models import User


class EmailLoginForm(AuthenticationForm):
    """Login with email + password. Django calls the login field `username` internally."""

    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email", "placeholder": "you@example.com"}),
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "placeholder": "••••••••"}),
    )

    error_messages = {
        "invalid_login": "That email and password don't match an account.",
        "inactive": "This account is disabled.",
    }


class SignupForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "placeholder": "At least 8 characters"}),
        help_text=password_validation.password_validators_help_text_html(),
    )
    password2 = forms.CharField(
        label="Confirm password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "placeholder": "Repeat password"}),
    )

    class Meta:
        model = User
        fields = ["full_name", "email"]
        labels = {"full_name": "Full name", "email": "Email"}
        widgets = {
            "full_name": forms.TextInput(attrs={"autocomplete": "name", "autofocus": True, "placeholder": "Your name"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "you@example.com"}),
        }

    def clean_email(self):
        email = User.objects.normalize_email(self.cleaned_data["email"]).lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists. Try logging in.")
        return email

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "The two passwords don't match.")
        return cleaned

    def _post_clean(self):
        super()._post_clean()
        # Validate the password against the (unsaved) user so similarity checks work.
        password = self.cleaned_data.get("password2")
        if password:
            try:
                password_validation.validate_password(password, self.instance)
            except forms.ValidationError as error:
                self.add_error("password1", error)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user
