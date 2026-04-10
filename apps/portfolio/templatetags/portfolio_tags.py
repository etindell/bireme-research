from django import template

register = template.Library()


@register.filter
def to_pct(value):
    """Convert a decimal to percentage (0.085 -> 8.5)."""
    if value is None:
        return None
    try:
        return float(value) * 100
    except (ValueError, TypeError):
        return value


@register.filter
def pct_display(value, decimals=1):
    """Convert a decimal to formatted percentage string (0.085 -> '8.5')."""
    if value is None:
        return '--'
    try:
        pct = float(value) * 100
        return f'{pct:.{int(decimals)}f}'
    except (ValueError, TypeError):
        return '--'
