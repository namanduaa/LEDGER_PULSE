from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "LedgerPulse admin"
admin.site.site_title = "LedgerPulse admin"
admin.site.index_title = "Users and data"

# Order matters: the ledger app is mounted at the root and ends with a catch-all section page.
urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("budgets/", include("budgets.urls")),
    path("", include("ledger.urls")),
]
# Uploaded receipts are NOT served publicly; they go through ledger:receipt, which checks ownership.
