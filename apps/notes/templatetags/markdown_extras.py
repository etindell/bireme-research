"""
Template filters for rendering markdown content.
"""
import markdown
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(name='markdown')
def render_markdown(value):
    """
    Render markdown content to HTML.
    Supports images, links, bold, italic, lists, etc.
    """
    if not value:
        return ''

    md = markdown.Markdown(
        extensions=[
            'markdown.extensions.fenced_code',
            'markdown.extensions.tables',
            'markdown.extensions.nl2br',  # Convert newlines to <br>
        ]
    )
    return mark_safe(md.convert(value))
