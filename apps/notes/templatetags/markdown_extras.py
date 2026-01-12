"""
Template filters for rendering markdown content.
"""
import re
import markdown
from django import template
from django.utils.safestring import mark_safe
import bleach

register = template.Library()

# Allowed HTML tags for sanitization
ALLOWED_TAGS = [
    'p', 'br', 'strong', 'em', 'u', 's', 'del',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'ul', 'ol', 'li',
    'blockquote', 'pre', 'code',
    'a', 'img',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
    'hr',
]

ALLOWED_ATTRIBUTES = {
    'a': ['href', 'title', 'target'],
    'img': ['src', 'alt', 'title'],
    '*': ['class'],
}


def process_underline(text):
    """Convert ++text++ to <u>text</u> for underline support."""
    return re.sub(r'\+\+(.+?)\+\+', r'<u>\1</u>', text)


def process_strikethrough(text):
    """Convert ~~text~~ to <s>text</s> for strikethrough support."""
    return re.sub(r'~~(.+?)~~', r'<s>\1</s>', text)


def process_bullets(text):
    """Convert • bullets to - for markdown list parsing."""
    return re.sub(r'^• ', '- ', text, flags=re.MULTILINE)


@register.filter(name='markdown')
def render_markdown(value):
    """
    Render markdown content to HTML.

    Supports:
    - **bold** or __bold__
    - *italic* or _italic_
    - ++underline++
    - ~~strikethrough~~
    - - bullet lists
    - 1. numbered lists
    - [links](url)
    - ![images](url)
    - # headers
    - > blockquotes
    - `code` and ```code blocks```
    - tables
    """
    if not value:
        return ''

    # Pre-process custom syntax
    value = process_bullets(value)
    value = process_underline(value)
    value = process_strikethrough(value)

    md = markdown.Markdown(
        extensions=[
            'markdown.extensions.fenced_code',
            'markdown.extensions.tables',
            'markdown.extensions.nl2br',  # Convert newlines to <br>
        ]
    )

    html = md.convert(value)

    # Sanitize HTML to prevent XSS while allowing our formatting tags
    clean_html = bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        strip=True
    )

    return mark_safe(clean_html)
