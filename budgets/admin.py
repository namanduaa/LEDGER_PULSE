from django.contrib import admin

from .models import BudgetEnvelope


@admin.register(BudgetEnvelope)
class BudgetEnvelopeAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "kind", "monthly_cap", "is_active", "created_at"]
    list_filter = ["kind", "is_active"]
    search_fields = ["name", "user__email"]
    autocomplete_fields = ["user"]
    filter_horizontal = ["categories"]
