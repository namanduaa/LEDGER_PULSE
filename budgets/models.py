from django.conf import settings
from django.db import models
from django.db.models import Q


class BudgetEnvelope(models.Model):
    """A monthly spending cap that covers one or more expense categories."""

    class Kind(models.TextChoices):
        FIXED = "fixed", "Fixed"
        VARIABLE = "variable", "Variable"
        DISCRETIONARY = "discretionary", "Discretionary"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="envelopes")
    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.VARIABLE)
    monthly_cap = models.DecimalField(max_digits=12, decimal_places=2)
    categories = models.ManyToManyField("ledger.Category", related_name="envelopes")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["user", "name"], name="unique_envelope_name_per_user"),
            models.CheckConstraint(condition=Q(monthly_cap__gt=0), name="envelope_cap_positive"),
        ]

    def __str__(self):
        return self.name
