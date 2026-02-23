from django import template

register = template.Library()


@register.filter
def get_field(form, event_date_pk):
    """Get a dynamic date field from the availability form by event_date pk."""
    field_name = f'date_{event_date_pk}'
    return form[field_name] if field_name in form.fields else ''
