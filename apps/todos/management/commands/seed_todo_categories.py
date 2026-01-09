"""
Management command to seed default todo categories for organizations.
"""
from django.core.management.base import BaseCommand, CommandError

from apps.organizations.models import Organization
from apps.todos.models import TodoCategory


DEFAULT_CATEGORIES = [
    {
        'name': 'Maintenance',
        'slug': 'maintenance',
        'category_type': 'maintenance',
        'color': '#10B981',  # Green
        'order': 1
    },
    {
        'name': 'Research',
        'slug': 'research',
        'category_type': 'research',
        'color': '#3B82F6',  # Blue
        'order': 2
    },
]


class Command(BaseCommand):
    help = 'Seed default todo categories for organizations'

    def add_arguments(self, parser):
        parser.add_argument(
            '--org',
            type=str,
            help='Organization slug (if not specified with --all, will error)'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Seed for all organizations'
        )

    def handle(self, *args, **options):
        if options['all']:
            organizations = Organization.objects.filter(is_deleted=False)
        elif options['org']:
            try:
                organizations = [Organization.objects.get(slug=options['org'])]
            except Organization.DoesNotExist:
                raise CommandError(f'Organization "{options["org"]}" does not exist')
        else:
            raise CommandError('Please specify --org <slug> or --all')

        total_created = 0

        for org in organizations:
            self.stdout.write(f'Seeding todo categories for {org.name}...')
            created_count = 0

            for cat_data in DEFAULT_CATEGORIES:
                _, created = TodoCategory.objects.get_or_create(
                    organization=org,
                    slug=cat_data['slug'],
                    defaults={
                        'name': cat_data['name'],
                        'category_type': cat_data['category_type'],
                        'color': cat_data['color'],
                        'order': cat_data['order'],
                    }
                )
                if created:
                    created_count += 1

            self.stdout.write(
                self.style.SUCCESS(f'  Created {created_count} new categories')
            )
            total_created += created_count

        self.stdout.write(
            self.style.SUCCESS(f'\nDone! Created {total_created} categories total.')
        )
