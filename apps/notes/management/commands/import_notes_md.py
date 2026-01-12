"""
Management command to import notes from a Markdown file.

Supports format:
    Company Name

    - Date Title of note
      - Nested content
      - More content
        - Even deeper nesting

Usage:
    python manage.py import_notes_md path/to/file.md --org my-org
    python manage.py import_notes_md path/to/file.md --org my-org --dry-run
"""
import re
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.organizations.models import Organization
from apps.companies.models import Company
from apps.notes.models import Note, NoteType


def parse_date(date_str):
    """
    Parse various date formats from the MD file.
    Examples:
        - "Fri, Nov 21, 2025"
        - "Thu, Nov 20, 2025"
        - "Wed, Nov 19, 2025"
        - "Tue, Nov 18, 2025"
        - "11/10/25"
    """
    # Clean up the string - remove special chars
    date_str = date_str.replace('\ufeff', '').strip()

    # Try various formats
    formats = [
        "%a, %b %d, %Y",      # Fri, Nov 21, 2025
        "%A, %b %d, %Y",      # Friday, Nov 21, 2025
        "%a, %B %d, %Y",      # Fri, November 21, 2025
        "%b %d, %Y",          # Nov 21, 2025
        "%B %d, %Y",          # November 21, 2025
        "%m/%d/%y",           # 11/21/25
        "%m/%d/%Y",           # 11/21/2025
        "%Y-%m-%d",           # 2025-11-21
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            # Make timezone aware
            return timezone.make_aware(datetime.combine(dt.date(), datetime.min.time()))
        except ValueError:
            continue

    return None


def get_indent_level(line):
    """Get the indentation level of a line (number of leading spaces/tabs)."""
    stripped = line.lstrip()
    if not stripped:
        return -1
    indent = len(line) - len(stripped)
    # Normalize: 2 spaces or 1 tab = 1 level
    return indent // 2


def parse_md_file(content):
    """
    Parse the markdown file and extract notes.

    Returns:
        tuple: (company_name, list of note dicts)
    """
    lines = content.split('\n')

    # First non-empty line is the company name
    company_name = None
    start_idx = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith('-') and not stripped.startswith('#'):
            company_name = stripped
            start_idx = i + 1
            break

    notes = []
    current_note = None
    current_content_lines = []

    # Pattern to match date entries
    # Matches: "- Fri, Nov 21, 2025 Title text" or "- 11/10/25 Title text"
    date_pattern = re.compile(
        r'^-\s*\ufeff?\s*'  # Bullet and optional BOM
        r'((?:[A-Za-z]{3,9},?\s+)?'  # Optional day name
        r'(?:[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}|'  # "Nov 21, 2025" or "November 21, 2025"
        r'\d{1,2}/\d{1,2}/\d{2,4}))'  # or "11/21/25"
        r'\ufeff?\s*'  # Optional BOM
        r'(.*)$'  # Rest is the title
    )

    for i in range(start_idx, len(lines)):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            if current_note and current_content_lines:
                current_content_lines.append('')
            continue

        # Check if this is a new top-level dated entry
        if stripped.startswith('-'):
            match = date_pattern.match(stripped)
            if match:
                # Save previous note
                if current_note:
                    current_note['content'] = '\n'.join(current_content_lines).strip()
                    notes.append(current_note)

                date_str = match.group(1)
                title = match.group(2).strip()

                parsed_date = parse_date(date_str)

                current_note = {
                    'date_str': date_str,
                    'written_at': parsed_date,
                    'title': title if title else date_str,
                    'content': '',
                }
                current_content_lines = []
                continue

        # This is content for the current note
        if current_note:
            # Remove leading "- " for cleaner content, preserve structure
            current_content_lines.append(line.rstrip())

    # Don't forget the last note
    if current_note:
        current_note['content'] = '\n'.join(current_content_lines).strip()
        notes.append(current_note)

    return company_name, notes


class Command(BaseCommand):
    help = 'Import notes from a Markdown file'

    def add_arguments(self, parser):
        parser.add_argument(
            'file_path',
            type=str,
            help='Path to the Markdown file to import'
        )
        parser.add_argument(
            '--org',
            type=str,
            required=True,
            help='Organization slug'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be imported without actually importing'
        )
        parser.add_argument(
            '--note-type',
            type=str,
            default=None,
            help='Note type slug to assign to imported notes'
        )

    @transaction.atomic
    def handle(self, *args, **options):
        file_path = Path(options['file_path'])
        dry_run = options['dry_run']

        # Validate file exists
        if not file_path.exists():
            self.stderr.write(self.style.ERROR(f"File not found: {file_path}"))
            return

        # Get organization
        try:
            org = Organization.objects.get(slug=options['org'])
        except Organization.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Organization '{options['org']}' not found"))
            return

        # Get note type if specified
        note_type = None
        if options['note_type']:
            try:
                note_type = NoteType.objects.get(organization=org, slug=options['note_type'])
            except NoteType.DoesNotExist:
                self.stderr.write(self.style.WARNING(
                    f"Note type '{options['note_type']}' not found, notes will have no type"
                ))

        # Read and parse the file
        self.stdout.write(f"Reading {file_path}...")
        content = file_path.read_text(encoding='utf-8')

        company_name, notes = parse_md_file(content)

        if not company_name:
            self.stderr.write(self.style.ERROR("Could not find company name in file"))
            return

        self.stdout.write(f"Company: {company_name}")
        self.stdout.write(f"Found {len(notes)} notes")

        # Find or prompt for company
        companies = Company.objects.filter(
            organization=org,
            name__icontains=company_name.split()[0],  # Search by first word
            is_deleted=False
        )

        if not companies.exists():
            # Try exact match
            companies = Company.objects.filter(
                organization=org,
                is_deleted=False
            )
            self.stdout.write(f"\nNo company matching '{company_name}' found.")
            self.stdout.write("Available companies:")
            for c in companies[:10]:
                self.stdout.write(f"  - {c.name} ({c.slug})")
            self.stderr.write(self.style.ERROR(
                f"Please create the company first or check the name in the file."
            ))
            return

        company = companies.first()
        if companies.count() > 1:
            self.stdout.write(f"\nMultiple matches found, using: {company.name}")

        self.stdout.write(f"\nImporting to company: {company.name}")

        if dry_run:
            self.stdout.write(self.style.WARNING('\nDRY RUN - No changes will be made\n'))

        # Import notes
        created_count = 0
        for note_data in notes:
            title = note_data['title'][:500] if note_data['title'] else 'Imported note'

            # Truncate very long titles
            if len(title) > 100:
                title = title[:97] + '...'

            if dry_run:
                date_display = note_data['written_at'].strftime('%Y-%m-%d') if note_data['written_at'] else 'No date'
                self.stdout.write(f"  [{date_display}] {title}")
                if note_data['content']:
                    preview = note_data['content'][:100].replace('\n', ' ')
                    self.stdout.write(f"    Content: {preview}...")
            else:
                Note.objects.create(
                    organization=org,
                    company=company,
                    title=title,
                    content=note_data['content'],
                    note_type=note_type,
                    written_at=note_data['written_at'],
                    created_by=None,  # Could pass a user if needed
                )
                self.stdout.write(f"  Created: {title}")

            created_count += 1

        if dry_run:
            self.stdout.write(self.style.SUCCESS(f'\nWould create {created_count} notes'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\nCreated {created_count} notes'))
