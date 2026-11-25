# LedgerPulse

A personal expense tracker built with **Python, Django, HTML/CSS and PostgreSQL**. Users sign up with their email and a password, then track expenses and income across their accounts, set monthly budget envelopes, and see their cash flow on a dashboard. Everyone who signs up shows up in the Django admin.

The UI follows the mockups in [`docs/design/`](docs/design/).

## Features (current)

| Page | What it does |
|---|---|
| **Sign up / Log in** | Email + password (case-insensitive email, Django password validators) |
| **Dashboard** | Net position, monthly inflow and outflow, savings rate, daily cash-flow chart, spending donut by category, recent activity, budget pacing |
| **Transactions** | All / Expenses / Income / Recurring tabs, search and filters, pagination, bulk categorise and delete, add or edit with an optional receipt upload |
| **Budgets** | Monthly envelopes that cover one or more categories, with spend, remaining, % used, status (on track / caution / overspent) and pace vs. days elapsed |
| **Accounts & Categories** | Add bank accounts, cards and cash with opening balances; add your own categories |
| **Django admin** | Every user with sign-up date, last login, number of accounts and transactions, and last entry; plus all ledger data |

Analytics, Reports and Statement Import are placeholders for now. See [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Tech

- Python 3.12, Django 5.2 LTS
- PostgreSQL 17 (runs in Docker for local development)
- Server-rendered Django templates with plain CSS (`static/css/app.css`). Charts are pure CSS, with no JavaScript framework.
- `python-decouple` for settings from `.env`

## Run it locally

```bash
# 1. Python environment
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Settings: copy the template, then set SECRET_KEY and DB_PASSWORD
cp .env.example .env

# 3. Database (PostgreSQL 17 on localhost:5433)
docker compose up -d db

# 4. Tables and an admin login
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser

# 5. Optional: a demo user with 3 months of sample data (prints its password)
.venv/bin/python manage.py seed_demo

# 6. Start
.venv/bin/python manage.py runserver
```

Then open http://127.0.0.1:8000. The admin is at http://127.0.0.1:8000/admin/.

## Tests

```bash
.venv/bin/python manage.py test
```

The tests cover sign-up and login, keeping each user's data private (another user's transactions, accounts, categories and receipts are unreachable), the totals and month-boundary maths, budget status and pace, and the admin user list.

## Project layout

```
config/      settings and root URLs
accounts/    custom User model (email login), sign-up / login views, admin
ledger/      Account, Category, Transaction; dashboard and transactions pages; services.py holds the maths
budgets/     BudgetEnvelope; budgets page; services.py holds spend / status / pace
templates/   base layout, pages, shared form-field partial
static/css/  app.css (design tokens match docs/design)
docs/        design mockups and roadmap
```

## Notes

- Uploaded receipts aren't served publicly. They download through `/transactions/<id>/receipt/`, which checks that the transaction belongs to you.
- New users automatically get a "Cash" account and a set of common categories.
- Amounts are stored as positive decimals, and `direction` (expense / income / transfer) gives the sign. Transfers don't count as income or spending.

Personal project by Naman Dua.
