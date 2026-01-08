"""
Management command to seed default note types for an organization.
"""
from django.core.management.base import BaseCommand, CommandError

from apps.organizations.models import Organization
from apps.notes.models import NoteType


DEFAULT_NOTE_TYPES = [
    {'name': 'Earnings Call', 'color': '#3B82F6', 'order': 1},      # Blue
    {'name': 'Expert Call', 'color': '#8B5CF6', 'order': 2},        # Purple
    {'name': 'Competitor Intel', 'color': '#F97316', 'order': 3},   # Orange
    {'name': 'Management Meeting', 'color': '#10B981', 'order': 4}, # Green
    {'name': 'General Research', 'color': '#6B7280', 'order': 5},   # Gray
    {'name': 'Thesis Update', 'color': '#EF4444', 'order': 6},      # Red
    {'name': 'Industry Note', 'color': '#06B6D4', 'order': 7},      # Cyan
    {'name': 'Regulatory Filing', 'color': '#EC4899', 'order': 8},  # Pink
]


class Command(BaseCommand):
    help = 'Seed default note types for an organization'

    def add_arguments(self, parser):
        parser.add_argument(
            '--org',
            type=str,
            help='Organization slug to seed note types for'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Seed note types for all organizations'
        )

    def handle(self, *args, **options):
        if options['all']:
            organizations = Organization.objects.all()
        elif options['org']:
            try:
                organizations = [Organization.objects.get(slug=options['org'])]
            except Organization.DoesNotExist:
                raise CommandError(f'Organization "{options["org"]}" does not exist')
        else:
            raise CommandError('Please specify --org <slug> or --all')

        for org in organizations:
            self.stdout.write(f'Seeding note types for {org.name}...')
            created_count = 0

            for note_type_data in DEFAULT_NOTE_TYPES:
                _, created = NoteType.objects.get_or_create(
                    organization=org,
                    name=note_type_data['name'],
                    defaults={
                        'color': note_type_data['color'],
                        'order': note_type_data['order'],
                    }
                )
                if created:
                    created_count += 1

            self.stdout.write(
                self.style.SUCCESS(f'  Created {created_count} new note types')
            )

        self.stdout.write(self.style.SUCCESS('Done!'))
