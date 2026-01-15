"""
Management command to fetch and process news for portfolio companies.
Designed to be run as a scheduled job (e.g., daily via Railway cron).
"""
from django.core.management.base import BaseCommand

from apps.companies.models import Company
from apps.news.services import fetch_and_store_news
from apps.organizations.models import Organization


class Command(BaseCommand):
    help = 'Fetch and process news for Long Book and Short Book companies'

    def add_arguments(self, parser):
        parser.add_argument(
            '--org',
            type=str,
            help='Organization slug (default: all organizations)'
        )
        parser.add_argument(
            '--company',
            type=str,
            help='Specific company slug (fetches for this company only)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fetched without actually fetching'
        )
        parser.add_argument(
            '--all-statuses',
            action='store_true',
            help='Fetch for all statuses, not just Long Book and Short Book'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        all_statuses = options['all_statuses']

        # Build company queryset
        companies = Company.objects.filter(is_deleted=False)

        # Filter by status (default: Long Book + Short Book only)
        if not all_statuses:
            companies = companies.filter(
                status__in=[Company.Status.LONG_BOOK, Company.Status.SHORT_BOOK]
            )

        # Filter by organization
        if options['org']:
            try:
                org = Organization.objects.get(slug=options['org'])
                companies = companies.filter(organization=org)
            except Organization.DoesNotExist:
                self.stderr.write(
                    self.style.ERROR(f"Organization not found: {options['org']}")
                )
                return

        # Filter by specific company
        if options['company']:
            companies = companies.filter(slug=options['company'])

        companies = companies.select_related('organization').prefetch_related('tickers')

        if not companies.exists():
            self.stdout.write(self.style.WARNING('No companies found matching criteria'))
            return

        self.stdout.write(f"Found {companies.count()} companies to process")
        self.stdout.write('-' * 50)

        total_new = 0
        for company in companies:
            if dry_run:
                self.stdout.write(
                    f"[DRY RUN] Would fetch news for: {company.name} "
                    f"({company.get_status_display()})"
                )
            else:
                self.stdout.write(f"Fetching news for: {company.name}...")
                try:
                    count = fetch_and_store_news(company)
                    total_new += count
                    if count > 0:
                        self.stdout.write(
                            self.style.SUCCESS(f"  -> {count} new items")
                        )
                    else:
                        self.stdout.write(f"  -> No new items")
                except Exception as e:
                    self.stderr.write(
                        self.style.ERROR(f"  -> Error: {e}")
                    )

        self.stdout.write('-' * 50)
        if dry_run:
            self.stdout.write(self.style.WARNING('Dry run complete - no changes made'))
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Complete! {total_new} total new items stored")
            )
