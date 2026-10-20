"""`money` filter: an amount with the app's currency symbol, grouped
thousands (localized, like floatformat:"2g") and the minus sign in front
of the symbol — "-$200,00" rather than "$-200,00" (QA report 2026-10-20,
finding 6). Empty values render as "—".

Usage: {% load money %}{{ caisse.balance|money }}
"""
from decimal import Decimal, InvalidOperation

from django import template
from django.template.defaultfilters import floatformat

from chantiermobile.constants import CurrencyConfig

register = template.Library()


@register.filter
def money(value, decimals='2g'):
    if value is None or value == '':
        return '—'
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return value
    sign = '-' if amount < 0 else ''
    return f'{sign}{CurrencyConfig.CURRENCY_SYMBOL}{floatformat(abs(amount), decimals)}'
