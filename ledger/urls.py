from django.urls import path

from . import views

app_name = "ledger"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("transactions/", views.transaction_list, name="transactions"),
    path("transactions/new/", views.transaction_create, name="transaction_create"),
    path("transactions/bulk/", views.transaction_bulk, name="transaction_bulk"),
    path("transactions/<int:pk>/edit/", views.transaction_edit, name="transaction_edit"),
    path("transactions/<int:pk>/receipt/", views.receipt, name="receipt"),
    path("settings/", views.settings_view, name="settings"),
    path("settings/accounts/<int:pk>/delete/", views.account_delete, name="account_delete"),
    path("settings/categories/<int:pk>/delete/", views.category_delete, name="category_delete"),
    path("<slug:section>/", views.coming_soon, name="coming_soon"),
]
