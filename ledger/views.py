from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q, ProtectedError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from budgets.services import envelope_statuses

from . import services
from .forms import AccountForm, CategoryForm, TransactionFilterForm, TransactionForm
from .models import Account, Category, Transaction

PAGE_SIZES = [10, 25, 50]


@login_required
def dashboard(request):
    user = request.user
    period = services.Period.parse(request.GET.get("month"))
    previous = period.previous()

    totals = services.period_totals(user, period.start, period.end)
    previous_totals = services.period_totals(user, previous.start, previous.end)
    net_now = services.net_position(user, before=period.end)
    net_prior = services.net_position(user, before=period.start)
    days_elapsed = period.days_elapsed()

    spend = services.category_spend(user, period)
    envelopes = sorted(envelope_statuses(user, period), key=lambda s: s.utilization, reverse=True)

    context = {
        "period": period,
        "totals": totals,
        "net_now": net_now,
        "net_prior": net_prior,
        "net_change": services.percent_change(net_now, net_prior),
        "inflow_change": totals.inflow - previous_totals.inflow,
        "outflow_change_pct": services.percent_change(totals.outflow, previous_totals.outflow),
        "daily_burn": (totals.outflow / days_elapsed).quantize(services.ZERO) if days_elapsed else None,
        "days_elapsed": days_elapsed,
        "flows": services.daily_flows(user, period),
        "spend": spend,
        "spend_total": sum((s["total"] for s in spend), services.ZERO),
        "donut": services.conic_gradient(spend),
        "recent": Transaction.objects.for_user(user).select_related("account", "category")[:6],
        "transaction_total": Transaction.objects.for_user(user).count(),
        "envelopes": envelopes[:3],
    }
    return render(request, "ledger/dashboard.html", context)


def _filtered_transactions(request):
    """Apply the filter bar to the user's transactions. Returns (queryset, filter_form, tab)."""
    user = request.user
    form = TransactionFilterForm(request.GET or None, user=user)
    qs = Transaction.objects.for_user(user).select_related("account", "category")
    tab = "all"
    if form.is_bound and form.is_valid():
        data = form.cleaned_data
        tab = data.get("tab") or "all"
        if data.get("q"):
            qs = qs.filter(Q(payee__icontains=data["q"]) | Q(note__icontains=data["q"]))
        if data.get("account"):
            qs = qs.filter(account=data["account"])
        if data.get("category"):
            qs = qs.filter(category=data["category"])
        if data.get("start"):
            qs = qs.filter(posted_at__date__gte=data["start"])
        if data.get("end"):
            qs = qs.filter(posted_at__date__lte=data["end"])
    return qs, form, tab


def _transaction_page(request, form=None, status=200):
    user = request.user
    base_qs, filter_form, tab = _filtered_transactions(request)

    tab_counts = base_qs.aggregate(
        all=Count("id"),
        expense=Count("id", filter=Q(direction=Transaction.Direction.EXPENSE)),
        income=Count("id", filter=Q(direction=Transaction.Direction.INCOME)),
        recurring=Count("id", filter=Q(is_recurring=True)),
    )
    qs = base_qs
    if tab in ("expense", "income"):
        qs = qs.filter(direction=tab)
    elif tab == "recurring":
        qs = qs.filter(is_recurring=True)

    totals = qs.aggregate(
        debits=services._sum(Q(direction=Transaction.Direction.EXPENSE)),
        credits=services._sum(Q(direction=Transaction.Direction.INCOME)),
        debit_count=Count("id", filter=Q(direction=Transaction.Direction.EXPENSE)),
        credit_count=Count("id", filter=Q(direction=Transaction.Direction.INCOME)),
    )
    totals["net"] = totals["credits"] - totals["debits"]

    try:
        per_page = int(request.GET.get("per_page", PAGE_SIZES[0]))
    except ValueError:
        per_page = PAGE_SIZES[0]
    per_page = per_page if per_page in PAGE_SIZES else PAGE_SIZES[0]
    page = Paginator(qs, per_page).get_page(request.GET.get("page"))

    query = request.GET.copy()
    query.pop("page", None)
    tab_query = query.copy()
    tab_query.pop("tab", None)

    context = {
        "page": page,
        "filter_form": filter_form,
        "tab": tab,
        "tabs": [(key, label, tab_counts[key]) for key, label in TransactionFilterForm.TABS],
        "tab_query": tab_query.urlencode(),
        "query": query.urlencode(),
        "totals": totals,
        "per_page": per_page,
        "page_sizes": PAGE_SIZES,
        "form": form or TransactionForm(user=user),
        "categories": Category.objects.filter(user=user),
        "has_accounts": Account.objects.filter(user=user, is_active=True).exists(),
    }
    return render(request, "ledger/transactions.html", context, status=status)


@login_required
def transaction_list(request):
    return _transaction_page(request)


@login_required
@require_POST
def transaction_create(request):
    form = TransactionForm(request.POST, request.FILES, user=request.user)
    if form.is_valid():
        txn = form.save()
        messages.success(request, f"Posted {txn.get_direction_display().lower()}: {txn.payee}.")
        return redirect("ledger:transactions")
    messages.error(request, "The transaction wasn't saved. Check the highlighted fields.")
    return _transaction_page(request, form=form, status=400)


@login_required
def transaction_edit(request, pk):
    txn = get_object_or_404(Transaction, pk=pk, user=request.user)
    form = TransactionForm(request.POST or None, request.FILES or None, instance=txn, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Transaction updated.")
        return redirect("ledger:transactions")
    return render(request, "ledger/transaction_edit.html", {"form": form, "txn": txn})


@login_required
@require_POST
def transaction_bulk(request):
    ids = request.POST.getlist("ids")
    selected = Transaction.objects.for_user(request.user).filter(pk__in=[i for i in ids if i.isdigit()])
    action = request.POST.get("action")
    if not selected.exists():
        messages.info(request, "Select at least one transaction first.")
    elif action == "delete":
        count, _ = selected.delete()
        messages.success(request, f"Deleted {count} transaction(s).")
    elif action == "categorize":
        category = Category.objects.filter(user=request.user, pk=request.POST.get("category") or 0).first()
        if category is None:
            messages.error(request, "Pick a category to apply.")
        else:
            count = selected.exclude(direction=Transaction.Direction.TRANSFER).update(category=category)
            messages.success(request, f"Moved {count} transaction(s) to {category}.")
    next_url = request.POST.get("next") or ""
    if not next_url.startswith(reverse("ledger:transactions")):
        next_url = reverse("ledger:transactions")
    return redirect(next_url)


@login_required
def receipt(request, pk):
    """Receipts are private: only the owner can download them (media is not publicly served)."""
    txn = get_object_or_404(Transaction, pk=pk, user=request.user)
    if not txn.receipt:
        raise Http404("No receipt attached.")
    return FileResponse(txn.receipt.open("rb"), filename=txn.receipt.name.rsplit("/", 1)[-1])


@login_required
def settings_view(request):
    user = request.user
    account_form = AccountForm(user=user, prefix="account")
    category_form = CategoryForm(user=user, prefix="category")
    if request.method == "POST":
        if "add_account" in request.POST:
            account_form = AccountForm(request.POST, user=user, prefix="account")
            if account_form.is_valid():
                account = account_form.save(commit=False)
                account.user = user
                account.save()
                messages.success(request, f"Added account {account.name}.")
                return redirect("ledger:settings")
        elif "add_category" in request.POST:
            category_form = CategoryForm(request.POST, user=user, prefix="category")
            if category_form.is_valid():
                category = category_form.save(commit=False)
                category.user = user
                category.save()
                messages.success(request, f"Added category {category.name}.")
                return redirect("ledger:settings")
    context = {
        "account_form": account_form,
        "category_form": category_form,
        "accounts": Account.objects.filter(user=user).annotate(txn_count=Count("transactions")),
        "categories": Category.objects.filter(user=user).annotate(txn_count=Count("transactions")),
    }
    return render(request, "ledger/settings.html", context)


@login_required
@require_POST
def account_delete(request, pk):
    account = get_object_or_404(Account, pk=pk, user=request.user)
    try:
        account.delete()
        messages.success(request, f"Deleted account {account.name}.")
    except ProtectedError:
        account.is_active = False
        account.save(update_fields=["is_active"])
        messages.info(request, f"{account.name} has transactions, so it was archived instead of deleted.")
    return redirect("ledger:settings")


@login_required
@require_POST
def category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk, user=request.user)
    category.delete()
    messages.success(request, f"Deleted category {category.name}. Its transactions are now uncategorised.")
    return redirect("ledger:settings")


@login_required
def coming_soon(request, section):
    pages = {
        "analytics": ("Analytics", "Trend analysis, month-on-month variance and anomaly detection."),
        "reports": ("Reports", "Monthly PDF statements and CSV exports."),
        "import": ("Statement Import", "Upload a bank statement PDF and review the extracted transactions."),
    }
    if section not in pages:
        raise Http404
    title, summary = pages[section]
    return render(request, "ledger/coming_soon.html", {"title": title, "summary": summary, "section": section})
