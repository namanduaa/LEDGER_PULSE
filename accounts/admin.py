from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.db.models import Count, Max

from .models import User


class AdminUserCreationForm(forms.ModelForm):
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ["email", "full_name"]

    def clean_password2(self):
        p1, p2 = self.cleaned_data.get("password1"), self.cleaned_data.get("password2")
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Passwords don't match.")
        return p2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = user.email.lower()
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class AdminUserChangeForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField(
        help_text="Passwords are stored hashed, so they can't be shown. "
        'Use the <a href="../password/">password change form</a> to set a new one.'
    )

    class Meta:
        model = User
        fields = "__all__"


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Everyone who signs up on the website, with a quick view of their activity."""

    form = AdminUserChangeForm
    add_form = AdminUserCreationForm

    list_display = [
        "email",
        "full_name",
        "date_joined",
        "last_login",
        "account_count",
        "transaction_count",
        "last_activity",
        "is_active",
        "is_staff",
    ]
    list_filter = ["is_active", "is_staff", "date_joined"]
    search_fields = ["email", "full_name"]
    ordering = ["-date_joined"]
    readonly_fields = ["date_joined", "last_login"]
    date_hierarchy = "date_joined"

    fieldsets = [
        (None, {"fields": ["email", "password"]}),
        ("Profile", {"fields": ["full_name"]}),
        ("Activity", {"fields": ["date_joined", "last_login"]}),
        ("Permissions", {"fields": ["is_active", "is_staff", "is_superuser", "groups", "user_permissions"]}),
    ]
    add_fieldsets = [
        (None, {"classes": ["wide"], "fields": ["email", "full_name", "password1", "password2"]}),
    ]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                _account_count=Count("ledger_accounts", distinct=True),
                _transaction_count=Count("transactions", distinct=True),
                _last_activity=Max("transactions__created_at"),
            )
        )

    @admin.display(description="Accounts", ordering="_account_count")
    def account_count(self, obj):
        return obj._account_count

    @admin.display(description="Transactions", ordering="_transaction_count")
    def transaction_count(self, obj):
        return obj._transaction_count

    @admin.display(description="Last entry", ordering="_last_activity")
    def last_activity(self, obj):
        return obj._last_activity
