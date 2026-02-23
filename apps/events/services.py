"""
Services for event planning - screenshot OCR and email generation.
"""
import base64
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_guests_from_screenshot(image_path):
    """
    Extract guest names and emails from a screenshot using Claude Vision API.

    Args:
        image_path: Path to the image file.

    Returns:
        List of dicts with 'name' and 'email' keys, or empty list on failure.
    """
    try:
        import anthropic
    except ImportError:
        logger.error("anthropic package not installed")
        return []

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        logger.error("ANTHROPIC_API_KEY environment variable not set")
        return []

    # Read and base64 encode the image
    image_path = Path(image_path)
    if not image_path.exists():
        logger.error(f"Image file not found: {image_path}")
        return []

    with open(image_path, 'rb') as f:
        image_data = base64.standard_b64encode(f.read()).decode('utf-8')

    # Determine media type
    suffix = image_path.suffix.lower()
    media_types = {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.webp': 'image/webp',
    }
    media_type = media_types.get(suffix, 'image/png')

    client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.messages.create(
            model='claude-sonnet-4-5-20250929',
            max_tokens=4096,
            messages=[
                {
                    'role': 'user',
                    'content': [
                        {
                            'type': 'image',
                            'source': {
                                'type': 'base64',
                                'media_type': media_type,
                                'data': image_data,
                            },
                        },
                        {
                            'type': 'text',
                            'text': (
                                'Extract all person names and email addresses from this image. '
                                'Return ONLY a JSON array of objects, each with "name" and "email" keys. '
                                'If you cannot find an email for a person, use an empty string for email. '
                                'If no people or contacts are found, return an empty array []. '
                                'Do not include any other text, just the JSON array.\n\n'
                                'Example output:\n'
                                '[{"name": "John Smith", "email": "john@example.com"}, '
                                '{"name": "Jane Doe", "email": "jane@example.com"}]'
                            ),
                        },
                    ],
                }
            ],
        )

        # Parse the response
        text = response.content[0].text.strip()
        # Handle potential markdown code blocks
        if text.startswith('```'):
            text = text.split('\n', 1)[1] if '\n' in text else text[3:]
            if text.endswith('```'):
                text = text[:-3]
            text = text.strip()

        guests = json.loads(text)
        if not isinstance(guests, list):
            logger.error(f"Expected list from Claude, got: {type(guests)}")
            return []

        # Validate each entry
        validated = []
        for g in guests:
            if isinstance(g, dict) and 'name' in g:
                validated.append({
                    'name': str(g.get('name', '')).strip(),
                    'email': str(g.get('email', '')).strip(),
                })

        return validated

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude response as JSON: {e}")
        return []
    except Exception as e:
        logger.error(f"Error calling Claude Vision API: {e}")
        return []


def generate_invitation_email(guest_name, event_name, event_date, event_location, event_description, rsvp_url):
    """
    Generate a personalized dinner invitation email using Claude.

    Args:
        guest_name: Name of the guest.
        event_name: Name of the event.
        event_date: Date/time of the event.
        event_location: Location of the event.
        event_description: Description of the event.
        rsvp_url: Full URL for the RSVP page.

    Returns:
        Generated email text, or a fallback template on failure.
    """
    try:
        import anthropic
    except ImportError:
        logger.error("anthropic package not installed")
        return _fallback_email(guest_name, event_name, event_date, event_location, rsvp_url)

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        logger.error("ANTHROPIC_API_KEY environment variable not set")
        return _fallback_email(guest_name, event_name, event_date, event_location, rsvp_url)

    client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=1024,
            messages=[
                {
                    'role': 'user',
                    'content': (
                        f'Write a warm, professional dinner invitation email for the following event.\n\n'
                        f'Guest name: {guest_name}\n'
                        f'Event: {event_name}\n'
                        f'Date: {event_date}\n'
                        f'Location: {event_location}\n'
                        f'Description: {event_description}\n'
                        f'RSVP link: {rsvp_url}\n\n'
                        f'Write ONLY the email body (no subject line). '
                        f'Start with a greeting using the guest\'s name. '
                        f'Include the event details and the RSVP link. '
                        f'Keep it concise (under 150 words), warm, and professional.'
                    ),
                }
            ],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.error(f"Error generating invitation email: {e}")
        return _fallback_email(guest_name, event_name, event_date, event_location, rsvp_url)


def _fallback_email(guest_name, event_name, event_date, event_location, rsvp_url):
    """Fallback email template when Claude API is unavailable."""
    return (
        f'Dear {guest_name},\n\n'
        f'You are cordially invited to {event_name}!\n\n'
        f'Date: {event_date}\n'
        f'Location: {event_location}\n\n'
        f'Please let us know if you can attend by clicking the link below:\n'
        f'{rsvp_url}\n\n'
        f'We look forward to seeing you there!\n\n'
        f'Best regards'
    )
