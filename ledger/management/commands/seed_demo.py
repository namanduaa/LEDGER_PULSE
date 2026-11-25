"""Create a demo user with ~3 months of realistic transactions and budget envelopes.

    python manage.py seed_demo                 # random password, printed once
    python manage.py seed_demo --password X    # choose the password
    python manage.py seed_demo --reset         # delete and recreate the demo user
"""

import random
import secrets
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from budgets.models import BudgetEnvelope
from ledger.models import Account, Category, Transaction

DEMO_EMAIL = "demo@ledgerpulse.local"

# (payee, note, category, account key, min, max, times per month)
EXPENSES = [
    ("Whole Foods Market", "Weekly groceries", "Groceries", "card", 40, 160, 4),
    ("Blue Bottle Coffee", "Morning coffee", "Food & Dining", "checking", 4, 15, 6),
    ("Dinner out", "Weekend dinner", "Food & Dining", "card", 30, 120, 3),
    ("Uber", "Rides around town", "Transport & Travel", "card", 8, 45, 5),
    ("AWS Cloud Infrastructure", "Side project hosting", "Tech & Software", "card", 40, 220, 1),
    ("GitHub", "Pro subscription", "Tech & Software", "card", 4, 4, 1),
    ("Figma", "Professional seat", "Tech & Software", "card", 15, 15, 1),
    ("Equinox Club", "Gym membership", "Health & Fitness", "checking", 245, 245, 1),
    ("Amazon", "Household items", "Shopping", "card", 15, 140, 2),
    ("Netflix", "Streaming", "Entertainment", "card", 15, 15, 1),
]
FIXED = [("Rent", "Monthly rent", "Housing & Utilities", "checking", 1800, 1),
         ("Electric & Fiber", "Utilities", "Housing & Utilities", "checking", 190, 5)]
INCOME = [("Acme Corp Payroll", "Monthly salary", "Salary", "mercury", 6200, 1),
          ("Stripe Payout", "Client retainer", "Freelance & Clients", "mercury", 2400, 15)]
ENVELOPES = [
    ("Housing & Utilities", "fixed", 2100, ["Housing & Utilities"]),
    ("Food & Dining", "variable", 700, ["Food & Dining", "Groceries"]),
    ("Tech & Software", "variable", 220, ["Tech & Software"]),
    ("Transport & Travel", "variable", 200, ["Transport & Travel"]),
    ("Health & Wellness", "fixed", 300, ["Health & Fitness"]),
    ("Discretionary & Entertainment", "discretionary", 250, ["Shopping", "Entertainment"]),
]


class Command(BaseCommand):
    help = "Create a demo user with sample transactions (development only)."

    def add_arguments(self, parser):
        parser.add_argument("--password", help="Password for the demo user (default: random, printed once).")
        parser.add_argument("--reset", action="store_true", help="Delete the existing demo user first.")
        parser.add_argument("--months", type=int, default=3, help="Months of history to generate (default 3).")

    def handle(self, *args, **opts):
        if not settings.DEBUG:
            raise CommandError("seed_demo only runs with DEBUG=True.")
        User = get_user_model()
        if User.objects.filter(email=DEMO_EMAIL).exists():
            if not opts["reset"]:
                raise CommandError(f"{DEMO_EMAIL} already exists. Use --reset to recreate it.")
            User.objects.filter(email=DEMO_EMAIL).delete()

        password = opts["password"] or secrets.token_urlsafe(9)
        with transaction.atomic():
            user = User.objects.create_user(DEMO_EMAIL, password, full_name="Demo User")
            count = self._populate(user, max(1, opts["months"]))

        self.stdout.write(self.style.SUCCESS(f"Created {DEMO_EMAIL} with {count} transactions."))
        if not opts["password"]:
            self.stdout.write(f"Password: {password}")

    def _populate(self, user, months):
        rng = random.Random(42)
        accounts = {
            "checking": Account.objects.create(user=user, name="Chase Checking", kind="checking", last4="4091",
                                               opening_balance=Decimal("8500.00")),
            "card": Account.objects.create(user=user, name="Platinum Card", kind="credit_card", last4="8812"),
            "mercury": Account.objects.create(user=user, name="Mercury Checking", kind="checking", last4="2210",
                                              opening_balance=Decimal("12000.00")),
        }
        categories = {c.name: c for c in Category.objects.filter(user=user)}

        for name, kind, cap, cats in ENVELOPES:
            envelope = BudgetEnvelope.objects.create(user=user, name=name, kind=kind, monthly_cap=Decimal(cap))
            envelope.categories.set([categories[c] for c in cats])

        today = timezone.localdate()
        first = today.replace(day=1)
        month_starts = []
        for _ in range(months):
            month_starts.insert(0, first)
            first = (first - timedelta(days=1)).replace(day=1)

        rows = []

        def add(day, payee, note, cat, acct, amount, direction):
            if day > today:
                return
            moment = timezone.make_aware(datetime.combine(day, time(rng.randint(7, 21), rng.randint(0, 59))))
            rows.append(Transaction(
                user=user, account=accounts[acct], category=categories.get(cat), direction=direction,
                amount=Decimal(amount).quantize(Decimal("0.01")), payee=payee, note=note, posted_at=moment,
                is_recurring=direction != "expense" or cat in ("Housing & Utilities", "Tech & Software", "Health & Fitness"),
            ))

        for start in month_starts:
            last_day = ((start + timedelta(days=32)).replace(day=1) - timedelta(days=1)).day
            for payee, note, cat, acct, amount, day in FIXED:
                add(start.replace(day=day), payee, note, cat, acct, amount, "expense")
            for payee, note, cat, acct, amount, day in INCOME:
                add(start.replace(day=day), payee, note, cat, acct, amount, "income")
            for payee, note, cat, acct, low, high, times in EXPENSES:
                for _ in range(times):
                    day = start.replace(day=rng.randint(1, last_day))
                    add(day, payee, note, cat, acct, rng.uniform(low, high), "expense")

        Transaction.objects.bulk_create(rows)
        return len(rows)
