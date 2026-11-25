# LedgerPulse roadmap

The design mockups for each screen are in `docs/design/`.

## Done: Phase 1, foundation
- Email + password sign-up and login, custom user model
- Django admin with user activity (accounts, transactions, last entry)
- Accounts, categories and transactions, with receipts that only the owner can download
- Dashboard (`dashboard.png`)
- Transactions: list, filters, tabs, bulk actions, add and edit (`transactions.png`)
- Budget envelopes with status and pace (`budgets.png`, first half)
- Tests for authentication, data isolation, the maths and budgets

## Next
1. **Budgets, part 2** (`budgets.png`): sinking funds and savings goals (target, saved, monthly auto-save, projected completion); moving surplus from one envelope to another.
2. **Transactions, part 2** (`transactions.png`): tags, CSV bulk import (with duplicate detection), recurring templates that post automatically each month, CSV export.
3. **Analytics** (`analytics.png`): 12-month spending trend, month-on-month and 6-month comparison table by category, unusual-spend flags (z-score / IQR), a simple next-month projection.
4. **Reports** (`reports.png`): a monthly statement PDF (ReportLab or WeasyPrint), a list of generated reports, CSV download.
5. **Statement Import** (`pdf-ingestion.png`): upload a bank statement PDF, extract rows with pdfplumber, check the debit and credit totals match the statement, review the extracted rows, then post them to the ledger.

## Later
- Email verification and password reset by email
- Celery + Redis for imports, recurring postings and report generation
- Docker for the web app, GitHub Actions CI, deployment
- Per-user currency setting
