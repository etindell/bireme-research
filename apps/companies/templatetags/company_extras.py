"""
Custom template filters for companies app.
"""
from decimal import Decimal
from django import template

register = template.Library()


@register.filter
def format_market_cap(value):
    """Format market cap in human-readable form (B/M)."""
    if value is None:
        return '-'

    try:
        value = Decimal(str(value))
        if value >= 1_000_000_000_000:
            return f'${value / 1_000_000_000_000:.1f}T'
        elif value >= 1_000_000_000:
            return f'${value / 1_000_000_000:.1f}B'
        elif value >= 1_000_000:
            return f'${value / 1_000_000:.0f}M'
        else:
            return f'${value:,.0f}'
    except (ValueError, TypeError):
        return '-'
