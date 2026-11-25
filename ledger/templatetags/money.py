from decimal import Decimal, InvalidOperation

from django import template
from django.conf import settings

register = template.Library()


def _fmt(value):
    try:
        value = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return ""
    return f"{settings.CURRENCY_SYMBOL}{abs(value):,.2f}"


@register.filter
def money(value):
    """1234.5 -> $1,234.50 (negative values get a leading minus)."""
    text = _fmt(value)
    if text and Decimal(value) < 0:
        return f"-{text}"
    return text


@register.filter
def signed_money(value):
    """Always show the sign: +$1,234.50 / -$12.00."""
    text = _fmt(value)
    if not text:
        return ""
    return f"-{text}" if Decimal(value) < 0 else f"+{text}"


@register.filter
def pct(value):
    """12.34 -> 12.3% ; None -> —"""
    if value is None:
        return "—"
    return f"{Decimal(value):.1f}%"
