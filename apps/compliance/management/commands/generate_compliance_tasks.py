from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.organizations.models import Organization
from apps.compliance.services.task_generation import generate_tasks


class Command(BaseCommand):
    help = 'Generate compliance task instances from templates'

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int, default=timezone.now().year)
        parser.add_argument('--org', type=str, help='Organization slug (all orgs if omitted)')
        parser.add_argument('--regenerate', action='store_true', help='Regenerate non-completed tasks')
        parser.add_argument('--dry-run', action='store_true', help='Preview without creating')

    def handle(self, *args, **options):
        year = options['year']
        dry_run = options['dry_run']
        regenerate = options['regenerate']

        if options['org']:
            orgs = Organization.objects.filter(slug=options['org'])
            if not orgs.exists():
                self.stderr.write(f"Organization '{options['org']}' not found.")
                return
        else:
            orgs = Organization.objects.filter(is_deleted=False)

        for org in orgs:
            self.stdout.write(f'\nOrganization: {org.name}')
            created, skipped = generate_tasks(org, year, regenerate=regenerate, dry_run=dry_run)
            prefix = '[DRY RUN] ' if dry_run else ''
            self.stdout.write(self.style.SUCCESS(
                f'{prefix}Created {created}, skipped {skipped} for {year}'
            ))
