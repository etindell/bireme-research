"""
Management command to backfill historical CT log data for Cybozu/Kintone.

Usage:
    python manage.py backfill_cybozu_ct --company-slug cybozu
    python manage.py backfill_cybozu_ct --company-slug cybozu --org bireme
"""
from django.core.management.base import BaseCommand, CommandError

from apps.companies.models import Company
from apps.organizations.models import Organization
from apps.signals.models import SignalSourceConfig
from apps.signals.services.cybozu_ct import run_sync


class Command(BaseCommand):
    help = 'Backfill historical CT log data for Cybozu/Kintone base domains'

    def add_arguments(self, parser):
        parser.add_argument(
            '--company-slug', type=str, required=True,
            help='Slug of the company to backfill',
        )
        parser.add_argument(
            '--org', type=str, default=None,
            help='Organization slug (uses first org if not specified)',
        )

    def handle(self, *args, **options):
        if options['org']:
            try:
                org = Organization.objects.get(slug=options['org'])
            except Organization.DoesNotExist:
                raise CommandError(f'Organization "{options["org"]}" not found')
        else:
            org = Organization.objects.first()
            if not org:
                raise CommandError('No organizations found.')

        try:
            company = Company.objects.get(
                slug=options['company_slug'],
                organization=org,
            )
        except Company.DoesNotExist:
            raise CommandError(
                f'Company "{options["company_slug"]}" not found in org "{org.name}"'
            )

        try:
            config = SignalSourceConfig.objects.get(
                company=company,
                organization=org,
                source=SignalSourceConfig.Source.CYBOZU_CT_SUBDOMAINS,
            )
        except SignalSourceConfig.DoesNotExist:
            raise CommandError(
                f'No cybozu_ct_subdomains config for {company.name}. '
                f'Run: manage.py create_signal_config --company-slug {company.slug} '
                f'--source cybozu_ct_subdomains'
            )

        self.stdout.write(f'Starting backfill for {company.name}...')
        self.stdout.write(
            f'Base domains: {config.settings_json.get("base_domains", [])}'
        )

        sync_run = run_sync(config)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Backfill complete!'))
        self.stdout.write(f'  Status: {sync_run.status}')
        self.stdout.write(f'  Raw CT entries seen: {sync_run.raw_items_seen}')
        self.stdout.write(f'  Unique domains parsed: {sync_run.unique_domains_parsed}')
        self.stdout.write(f'  Created: {sync_run.created_count}')
        self.stdout.write(f'  Updated: {sync_run.updated_count}')
        self.stdout.write(f'  Excluded: {sync_run.excluded_count}')
        if sync_run.error_text:
            self.stderr.write(f'  Errors: {sync_run.error_text}')
