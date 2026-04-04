from django import template

register = template.Library()

STATUS_COLORS = {
    'NOT_STARTED': ('bg-gray-100 text-gray-700', 'text-gray-400'),
    'IN_PROGRESS': ('bg-blue-100 text-blue-700', 'text-blue-400'),
    'COMPLETED': ('bg-green-100 text-green-700', 'text-green-500'),
    'DEFERRED': ('bg-yellow-100 text-yellow-700', 'text-yellow-400'),
    'NOT_APPLICABLE': ('bg-gray-100 text-gray-500', 'text-gray-300'),
}


@register.filter
def status_badge_class(status):
    return STATUS_COLORS.get(status, STATUS_COLORS['NOT_STARTED'])[0]


@register.filter
def status_dot_class(status):
    return STATUS_COLORS.get(status, STATUS_COLORS['NOT_STARTED'])[1]


@register.filter
def status_label(status):
    labels = {
        'NOT_STARTED': 'Not Started',
        'IN_PROGRESS': 'In Progress',
        'COMPLETED': 'Completed',
        'DEFERRED': 'Deferred',
        'NOT_APPLICABLE': 'N/A',
    }
    return labels.get(status, status)


QUARTER_DATES = {
    1: ('Jan 1', 'Mar 31'),
    2: ('Apr 1', 'Jun 30'),
    3: ('Jul 1', 'Sep 30'),
    4: ('Oct 1', 'Dec 31'),
}


@register.filter
def period_label(assignment):
    """Return a human-readable period label like 'Q4 2025 (Oct 1 - Dec 31, 2025)' or 'Year 2025 (Jan 1 - Dec 31, 2025)'."""
    year = getattr(assignment, 'year', None)
    quarter = getattr(assignment, 'quarter', None)
    if quarter and year:
        start, end = QUARTER_DATES.get(quarter, ('', ''))
        return f"Q{quarter} {year} ({start} \u2013 {end}, {year})"
    if year:
        return f"Year {year} (Jan 1 \u2013 Dec 31, {year})"
    return ""
