from django.urls import path

from . import views

app_name = "budgets"

urlpatterns = [
    path("", views.budget_list, name="list"),
    path("<int:pk>/edit/", views.envelope_edit, name="edit"),
    path("<int:pk>/delete/", views.envelope_delete, name="delete"),
]
