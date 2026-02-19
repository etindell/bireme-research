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
    'hr', 'div', 'span',
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


BLANK_LINE_MARKER = 'BLANKLINEMARKER8675309'


def preserve_blank_lines(text):
    """
    Preserve blank lines so rendered output matches what the user typed.

    With nl2br, a single newline becomes <br>. A double newline (\n\n) becomes
    a paragraph break, but visually that looks almost the same as <br> with
    prose-sm styling. We insert markers so that each blank line the user typed
    produces visible spacing in the output.
    """
    # Normalize line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    # Find sequences of 2+ newlines (1+ blank lines)
    # and insert markers for visible spacing
    def replace_blank_lines(match):
        newlines = match.group(0)
        # Count blank lines (n newlines = n-1 blank lines)
        blank_count = newlines.count('\n') - 1
        if blank_count < 1:
            return newlines
        # Each blank line gets a marker for visible spacing
        markers = (BLANK_LINE_MARKER + '\n\n') * blank_count
        return '\n\n' + markers

    return re.sub(r'\n{2,}', replace_blank_lines, text)


def restore_blank_lines(html):
    """Convert blank line markers to visible spacing."""
    # The markers will be wrapped in <p> tags by markdown, replace with styled empty paragraph
    html = html.replace(f'<p>{BLANK_LINE_MARKER}</p>', '<div class="h-4"></div>')
    html = html.replace(BLANK_LINE_MARKER, '')  # Remove any leftover markers
    return html


def process_links(html):
    """
    Add target="_blank" and rel="noopener noreferrer" to external links,
    and add explicit styling classes to make links visible.
    """
    # Add target="_blank" and rel to links that don't already have target
    # Also add a class for explicit styling
    html = re.sub(
        r'<a href="(https?://[^"]+)"(?![^>]*target=)',
        r'<a href="\1" target="_blank" rel="noopener noreferrer" class="text-primary-600 underline hover:text-primary-500"',
        html
    )
    # For links that might not have styling, add it
    html = re.sub(
        r'<a href="([^"]+)"(?![^>]*class=)',
        r'<a href="\1" class="text-primary-600 underline hover:text-primary-500"',
        html
    )
    return html


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
    - Multiple blank lines are preserved
    """
    if not value:
        return ''

    # Pre-process custom syntax
    value = preserve_blank_lines(value)
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

    # Restore blank line markers as visible spacing
    clean_html = restore_blank_lines(clean_html)

    # Process links to add styling and target="_blank" for external links
    clean_html = process_links(clean_html)

    return mark_safe(clean_html)
