"""
Management command to sync CT log data for Cybozu/Kintone.
Intended for recurring scheduled syncs. Idempotent.

Usage:
    python manage.py sync_cybozu_ct
    python manage.py sync_cybozu_ct --company-slug cybozu
"""
from django.core.management.base import BaseCommand, CommandError

from apps.organizations.models import Organization
from apps.signals.models import SignalSourceConfig
from apps.signals.services.cybozu_ct import run_sync


class Command(BaseCommand):
    help = 'Sync CT log data for all enabled Cybozu/Kintone signal configs'

    def add_arguments(self, parser):
        parser.add_argument(
            '--company-slug', type=str, default=None,
            help='Limit to a specific company (by slug)',
        )
        parser.add_argument(
            '--org', type=str, default=None,
            help='Limit to a specific organization (by slug)',
        )

    def handle(self, *args, **options):
        configs = SignalSourceConfig.objects.filter(
            source=SignalSourceConfig.Source.CYBOZU_CT_SUBDOMAINS,
            is_enabled=True,
        ).select_related('company', 'organization')

        if options['org']:
            try:
                org = Organization.objects.get(slug=options['org'])
                configs = configs.filter(organization=org)
            except Organization.DoesNotExist:
                raise CommandError(f'Organization "{options["org"]}" not found')

        if options['company_slug']:
            configs = configs.filter(company__slug=options['company_slug'])

        if not configs.exists():
            self.stdout.write(self.style.WARNING('No enabled configs found.'))
            return

        for config in configs:
            self.stdout.write(
                f'Syncing {config.company.name} ({config.get_source_display()})...'
            )

            sync_run = run_sync(config)

            status_style = (
                self.style.SUCCESS if sync_run.status == 'success'
                else self.style.ERROR
            )
            self.stdout.write(status_style(
                f'  {sync_run.status}: '
                f'{sync_run.created_count} created, '
                f'{sync_run.updated_count} updated, '
                f'{sync_run.excluded_count} excluded'
            ))
            if sync_run.error_text:
                self.stderr.write(f'  Errors: {sync_run.error_text}')

        self.stdout.write(self.style.SUCCESS('Sync complete.'))
