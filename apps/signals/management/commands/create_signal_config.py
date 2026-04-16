"""
Management command to create or update a SignalSourceConfig.

Usage:
    python manage.py create_signal_config --company-slug cybozu --source cybozu_ct_subdomains
    python manage.py create_signal_config --company-slug cybozu --source cybozu_ct_subdomains --org bireme
"""
from django.core.management.base import BaseCommand, CommandError

from apps.companies.models import Company
from apps.organizations.models import Organization
from apps.signals.models import SignalSourceConfig


class Command(BaseCommand):
    help = 'Create or update a signal source config for a company'

    def add_arguments(self, parser):
        parser.add_argument(
            '--company-slug', type=str, required=True,
            help='Slug of the company to configure',
        )
        parser.add_argument(
            '--source', type=str, required=True,
            choices=[c[0] for c in SignalSourceConfig.Source.choices],
            help='Signal source type',
        )
        parser.add_argument(
            '--org', type=str, default=None,
            help='Organization slug (uses first org if not specified)',
        )
        parser.add_argument(
            '--name', type=str, default=None,
            help='Display name (auto-generated if not specified)',
        )
        parser.add_argument(
            '--disable', action='store_true',
            help='Create the config in disabled state',
        )

    def handle(self, *args, **options):
        # Resolve organization
        if options['org']:
            try:
                org = Organization.objects.get(slug=options['org'])
            except Organization.DoesNotExist:
                raise CommandError(f'Organization "{options["org"]}" not found')
        else:
            org = Organization.objects.first()
            if not org:
                raise CommandError('No organizations found. Create one first.')

        # Resolve company
        try:
            company = Company.objects.get(
                slug=options['company_slug'],
                organization=org,
            )
        except Company.DoesNotExist:
            raise CommandError(
                f'Company "{options["company_slug"]}" not found in org "{org.name}"'
            )

        source = options['source']
        name = options['name'] or f'{company.name} - {SignalSourceConfig.Source(source).label}'

        # Get source-specific defaults
        defaults = {}
        if source == SignalSourceConfig.Source.CYBOZU_CT_SUBDOMAINS:
            defaults = SignalSourceConfig.get_cybozu_defaults()

        config, created = SignalSourceConfig.objects.update_or_create(
            organization=org,
            company=company,
            source=source,
            defaults={
                'name': name,
                'is_enabled': not options['disable'],
                **defaults,
            },
        )

        action = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(
            f'{action} signal config: {config.name}\n'
            f'  Organization: {org.name}\n'
            f'  Company: {company.name}\n'
            f'  Source: {config.get_source_display()}\n'
            f'  Enabled: {config.is_enabled}\n'
            f'  Settings: {config.settings_json}\n'
            f'  Ignore keywords: {config.ignore_keywords}'
        ))
