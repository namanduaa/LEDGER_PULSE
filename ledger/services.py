"""Ledger calculations. Views stay thin and call these functions."""

import calendar
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db import transaction as db_transaction
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from .models import Account, Category, Transaction

ZERO = Decimal("0.00")
MONEY = DecimalField(max_digits=14, decimal_places=2)

STARTER_CATEGORIES = [
    # (name, kind, colour)
    ("Housing & Utilities", "expense", "#4338ca"),
    ("Food & Dining", "expense", "#047857"),
    ("Groceries", "expense", "#0d9488"),
    ("Transport & Travel", "expense", "#0284c7"),
    ("Tech & Software", "expense", "#7c3aed"),
    ("Health & Fitness", "expense", "#db2777"),
    ("Shopping", "expense", "#d97706"),
    ("Entertainment", "expense", "#64748b"),
    ("Salary", "income", "#16a34a"),
    ("Freelance & Clients", "income", "#22c55e"),
    ("Other Income", "income", "#84cc16"),
]


@db_transaction.atomic
def create_starter_data(user):
    Account.objects.get_or_create(user=user, name="Cash", defaults={"kind": Account.Kind.CASH})
    for name, kind, color in STARTER_CATEGORIES:
        Category.objects.get_or_create(user=user, name=name, defaults={"kind": kind, "color": color})


# --- Periods -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Period:
    """A calendar month in the user's timezone, as a half-open [start, end) range."""

    year: int
    month: int

    @classmethod
    def containing(cls, day: date) -> "Period":
        return cls(day.year, day.month)

    @classmethod
    def current(cls) -> "Period":
        return cls.containing(timezone.localdate())

    @classmethod
    def parse(cls, value: str | None) -> "Period":
        """Parse 'YYYY-MM'; fall back to the current month."""
        try:
            year, month = (int(part) for part in (value or "").split("-"))
            if 1 <= month <= 12 and 2000 <= year <= 2100:
                return cls(year, month)
        except ValueError:
            pass
        return cls.current()

    @property
    def first_day(self) -> date:
        return date(self.year, self.month, 1)

    @property
    def days_in_month(self) -> int:
        return calendar.monthrange(self.year, self.month)[1]

    @property
    def start(self) -> datetime:
        return timezone.make_aware(datetime.combine(self.first_day, time.min))

    @property
    def end(self) -> datetime:
        return self.next().start

    def previous(self) -> "Period":
        return Period(self.year - 1, 12) if self.month == 1 else Period(self.year, self.month - 1)

    def next(self) -> "Period":
        return Period(self.year + 1, 1) if self.month == 12 else Period(self.year, self.month + 1)

    @property
    def key(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

    @property
    def label(self) -> str:
        return self.first_day.strftime("%B %Y")

    def days_elapsed(self, today: date | None = None) -> int:
        """Days of this month that have passed (whole month for past months, 0 for future ones)."""
        today = today or timezone.localdate()
        if today < self.first_day:
            return 0
        if today >= self.next().first_day:
            return self.days_in_month
        return today.day


# --- Totals --------------------------------------------------------------------------------------


def _sum(field_filter=None):
    return Coalesce(Sum("amount", filter=field_filter), Value(ZERO), output_field=MONEY)


@dataclass
class PeriodTotals:
    inflow: Decimal
    outflow: Decimal
    income_count: int
    expense_count: int
    count: int

    @property
    def net(self) -> Decimal:
        return self.inflow - self.outflow

    @property
    def savings_rate(self) -> Decimal | None:
        """Share of income kept, as a percentage (None when there is no income)."""
        if not self.inflow:
            return None
        return (self.net / self.inflow * 100).quantize(Decimal("0.1"))


def period_totals(user, start, end) -> PeriodTotals:
    row = Transaction.objects.for_user(user).between(start, end).aggregate(
        inflow=_sum(Q(direction=Transaction.Direction.INCOME)),
        outflow=_sum(Q(direction=Transaction.Direction.EXPENSE)),
        income_count=Count("id", filter=Q(direction=Transaction.Direction.INCOME)),
        expense_count=Count("id", filter=Q(direction=Transaction.Direction.EXPENSE)),
        count=Count("id"),
    )
    return PeriodTotals(**row)


def net_position(user, before=None) -> Decimal:
    """Opening balances plus all income minus all expenses (optionally only before a moment)."""
    opening = Account.objects.filter(user=user).aggregate(
        total=Coalesce(Sum("opening_balance"), Value(ZERO), output_field=MONEY)
    )["total"]
    txns = Transaction.objects.for_user(user)
    if before is not None:
        txns = txns.filter(posted_at__lt=before)
    row = txns.aggregate(
        inflow=_sum(Q(direction=Transaction.Direction.INCOME)),
        outflow=_sum(Q(direction=Transaction.Direction.EXPENSE)),
    )
    return opening + row["inflow"] - row["outflow"]


def percent_change(current: Decimal, previous: Decimal) -> Decimal | None:
    if not previous:
        return None
    return ((current - previous) / abs(previous) * 100).quantize(Decimal("0.1"))


# --- Breakdowns ----------------------------------------------------------------------------------


def daily_flows(user, period: Period) -> list[dict]:
    """One row per day of the month: inflow, outflow and bar heights (0-100) for the chart."""
    rows = (
        Transaction.objects.for_user(user)
        .between(period.start, period.end)
        .annotate(day=TruncDate("posted_at"))
        .values("day")
        .annotate(
            inflow=_sum(Q(direction=Transaction.Direction.INCOME)),
            outflow=_sum(Q(direction=Transaction.Direction.EXPENSE)),
        )
    )
    by_day = {row["day"]: row for row in rows}
    days = []
    for offset in range(period.days_in_month):
        day = period.first_day + timedelta(days=offset)
        row = by_day.get(day, {})
        days.append({"day": day, "inflow": row.get("inflow", ZERO), "outflow": row.get("outflow", ZERO)})

    peak = max([max(d["inflow"], d["outflow"]) for d in days] + [Decimal("1")])
    for d in days:
        d["inflow_pct"] = round(d["inflow"] / peak * 100, 1)
        d["outflow_pct"] = round(d["outflow"] / peak * 100, 1)
    return days


def category_spend(user, period: Period) -> list[dict]:
    """Expense totals per category for the month, largest first, with share of total."""
    rows = list(
        Transaction.objects.for_user(user)
        .expenses()
        .between(period.start, period.end)
        .values("category__name", "category__color")
        .annotate(total=_sum())
        .order_by("-total")
    )
    grand_total = sum((r["total"] for r in rows), ZERO)
    result = []
    for r in rows:
        share = (r["total"] / grand_total * 100) if grand_total else ZERO
        result.append(
            {
                "name": r["category__name"] or "Uncategorised",
                "color": r["category__color"] or "#94a3b8",
                "total": r["total"],
                "share": share.quantize(Decimal("0.1")),
            }
        )
    return result


def conic_gradient(segments: list[dict]) -> str:
    """CSS conic-gradient stops for a donut chart, built from category_spend() rows."""
    if not segments:
        return "#e2e8f0 0 100%"
    stops, position = [], Decimal("0")
    for seg in segments:
        end = position + seg["share"]
        stops.append(f"{seg['color']} {position}% {end}%")
        position = end
    return ", ".join(stops)
