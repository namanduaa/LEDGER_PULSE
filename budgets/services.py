from dataclasses import dataclass
from decimal import Decimal

from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce

from ledger.models import Transaction
from ledger.services import ZERO, Period

from .models import BudgetEnvelope

CAUTION_AT = Decimal("80")  # % of cap used
OVERSPENT_AT = Decimal("100")


@dataclass
class EnvelopeStatus:
    envelope: BudgetEnvelope
    spent: Decimal
    expected_by_now: Decimal  # where spending "should" be if spread evenly over the month

    @property
    def cap(self) -> Decimal:
        return self.envelope.monthly_cap

    @property
    def remaining(self) -> Decimal:
        return self.cap - self.spent

    @property
    def utilization(self) -> Decimal:
        return (self.spent / self.cap * 100).quantize(Decimal("0.1"))

    @property
    def bar_width(self) -> Decimal:
        return min(self.utilization, Decimal("100"))

    @property
    def status(self) -> str:
        if self.utilization > OVERSPENT_AT:
            return "overspent"
        if self.utilization >= CAUTION_AT:
            return "caution"
        return "safe"

    @property
    def status_label(self) -> str:
        return {"overspent": "Overspent", "caution": "Caution", "safe": "On track"}[self.status]

    @property
    def is_ahead_of_pace(self) -> bool:
        return self.spent > self.expected_by_now


def envelope_statuses(user, period: Period) -> list[EnvelopeStatus]:
    """Spend against every active envelope for one month."""
    envelopes = BudgetEnvelope.objects.filter(user=user, is_active=True).prefetch_related("categories")
    elapsed_share = Decimal(period.days_elapsed()) / Decimal(period.days_in_month)
    money = DecimalField(max_digits=14, decimal_places=2)

    results = []
    for envelope in envelopes:
        category_ids = [c.id for c in envelope.categories.all()]
        spent = Transaction.objects.for_user(user).between(period.start, period.end).aggregate(
            total=Coalesce(
                Sum("amount", filter=Q(direction=Transaction.Direction.EXPENSE, category_id__in=category_ids)),
                Value(ZERO),
                output_field=money,
            )
        )["total"]
        expected = (envelope.monthly_cap * elapsed_share).quantize(Decimal("0.01"))
        results.append(EnvelopeStatus(envelope=envelope, spent=spent, expected_by_now=expected))
    return results


def budget_summary(statuses: list[EnvelopeStatus]) -> dict:
    allocated = sum((s.cap for s in statuses), ZERO)
    spent = sum((s.spent for s in statuses), ZERO)
    return {
        "allocated": allocated,
        "spent": spent,
        "remaining": allocated - spent,
        "utilization": (spent / allocated * 100).quantize(Decimal("0.1")) if allocated else None,
        "envelope_count": len(statuses),
    }
