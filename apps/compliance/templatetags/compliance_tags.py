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
