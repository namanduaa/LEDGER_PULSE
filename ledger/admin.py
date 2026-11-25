from django.contrib import admin

from .models import Account, Category, Transaction


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "kind", "last4", "opening_balance", "is_active", "created_at"]
    list_filter = ["kind", "is_active"]
    search_fields = ["name", "user__email"]
    autocomplete_fields = ["user"]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "kind", "color"]
    list_filter = ["kind"]
    search_fields = ["name", "user__email"]
    autocomplete_fields = ["user"]


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ["posted_at", "payee", "user", "direction", "amount", "category", "account", "status"]
    list_filter = ["direction", "status", "is_recurring", "posted_at"]
    search_fields = ["payee", "note", "user__email"]
    date_hierarchy = "posted_at"
    list_select_related = ["user", "category", "account"]
    autocomplete_fields = ["user", "account", "category"]
    readonly_fields = ["created_at", "updated_at"]
