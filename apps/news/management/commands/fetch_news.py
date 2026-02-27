"""
Management command to fetch and process news for portfolio companies.
Designed to be run as a scheduled job (e.g., daily via Railway cron).
"""
from django.core.management.base import BaseCommand

from apps.companies.models import Company
from apps.news.models import CompanyNews
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
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear all existing news before fetching'
        )

    def handle(self, *args, **options):
        # Clear existing news if requested
        if options['clear']:
            from apps.news.models import CompanyNews
            count = CompanyNews.objects.count()
            CompanyNews.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Cleared {count} existing news items"))

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
        if dry_run:
            for company in companies:
                self.stdout.write(
                    f"[DRY RUN] Would fetch news for: {company.name} "
                    f"({company.get_status_display()})"
                )
        else:
            from apps.news.services import fetch_news_for_companies

            self.stdout.write(f"Fetching news for {companies.count()} companies concurrently...")
            total_new, errors = fetch_news_for_companies(companies)

            for error in errors:
                self.stderr.write(self.style.ERROR(f"  -> Error: {error}"))

        self.stdout.write('-' * 50)
        if dry_run:
            self.stdout.write(self.style.WARNING('Dry run complete - no changes made'))
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Complete! {total_new} total new items stored")
            )

            # Regenerate preference profiles for orgs that have feedback
            self._update_preference_profiles(companies)

    def _update_preference_profiles(self, companies):
        """Regenerate preference profiles for orgs that have feedback."""
        from django.core.management import call_command

        org_ids = companies.values_list('organization_id', flat=True).distinct()
        orgs_with_feedback = Organization.objects.filter(
            pk__in=org_ids,
            news_items__feedback__isnull=False,
        ).distinct()

        if not orgs_with_feedback:
            return

        self.stdout.write('-' * 50)
        self.stdout.write('Updating news preference profiles...')
        for org in orgs_with_feedback:
            try:
                call_command('generate_news_profile', org=org.slug, stdout=self.stdout)
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"  Profile update failed for {org.slug}: {e}"))
