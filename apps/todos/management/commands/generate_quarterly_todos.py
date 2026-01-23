"""
Management command to generate quarterly todos.

Run 3 weeks after quarter end via cron/scheduler.
Schedule: Run on the 21st of Jan, Apr, Jul, Oct

Usage:
    python manage.py generate_quarterly_todos
    python manage.py generate_quarterly_todos --org my-org
    python manage.py generate_quarterly_todos --dry-run
    python manage.py generate_quarterly_todos --quarter 2024-Q1
"""
from datetime import date
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.organizations.models import Organization
from apps.companies.models import Company
from apps.todos.models import Todo, TodoCategory


def get_quarter_info(reference_date=None):
    """
    Get the previous quarter's info based on reference date.
    Returns tuple: (quarter_string, fiscal_year)

    Logic:
    - If we're in Jan-Mar, previous quarter was Q4 of last year
    - If we're in Apr-Jun, previous quarter was Q1
    - If we're in Jul-Sep, previous quarter was Q2
    - If we're in Oct-Dec, previous quarter was Q3
    """
    if reference_date is None:
        reference_date = date.today()

    month = reference_date.month
    year = reference_date.year

    if month in [1, 2, 3]:
        return f"{year - 1}-Q4", year - 1
    elif month in [4, 5, 6]:
        return f"{year}-Q1", year
    elif month in [7, 8, 9]:
        return f"{year}-Q2", year
    else:
        return f"{year}-Q3", year


class Command(BaseCommand):
    help = 'Generate quarterly update todos for Long Book, Short Book, and On Deck companies'

    def add_arguments(self, parser):
        parser.add_argument(
            '--org',
            type=str,
            help='Organization slug (if not specified, runs for all organizations)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without actually creating'
        )
        parser.add_argument(
            '--quarter',
            type=str,
            help='Override quarter (e.g., 2024-Q1). Defaults to previous quarter.'
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # Get organizations
        if options['org']:
            organizations = Organization.objects.filter(slug=options['org'])
            if not organizations.exists():
                self.stderr.write(
                    self.style.ERROR(f"Organization '{options['org']}' not found")
                )
                return
        else:
            organizations = Organization.objects.filter(is_deleted=False)

        # Determine quarter
        if options['quarter']:
            quarter = options['quarter']
            try:
                fiscal_year = int(quarter.split('-')[0])
            except (ValueError, IndexError):
                self.stderr.write(
                    self.style.ERROR(f"Invalid quarter format: {quarter}. Use YYYY-QN format.")
                )
                return
        else:
            quarter, fiscal_year = get_quarter_info()

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes will be made'))

        self.stdout.write(f"\nGenerating todos for quarter: {quarter}\n")

        total_created = 0

        for org in organizations:
            self.stdout.write(f"\nProcessing organization: {org.name}")
            org_created = 0

            # Get or create categories
            maintenance_cat = self._get_or_create_category(
                org, 'Maintenance', 'maintenance', '#10B981', dry_run
            )
            research_cat = self._get_or_create_category(
                org, 'Research', 'research', '#3B82F6', dry_run
            )

            # Long Book / Short Book companies -> Maintenance todos
            book_companies = Company.objects.filter(
                organization=org,
                status__in=[Company.Status.LONG_BOOK, Company.Status.SHORT_BOOK],
                is_deleted=False
            )
            self.stdout.write(f"  Long/Short Book companies: {book_companies.count()}")

            for company in book_companies:
                created = self._create_quarterly_todo(
                    org, company, quarter, fiscal_year, maintenance_cat, dry_run
                )
                if created:
                    org_created += 1

            # On Deck companies -> Research todos
            on_deck_companies = Company.objects.filter(
                organization=org,
                status=Company.Status.ON_DECK,
                is_deleted=False
            )
            self.stdout.write(f"  On Deck companies: {on_deck_companies.count()}")

            for company in on_deck_companies:
                created = self._create_quarterly_todo(
                    org, company, quarter, fiscal_year, research_cat, dry_run
                )
                if created:
                    org_created += 1

            # Create investor letter review todo
            letter_created = self._create_investor_letter_todo(
                org, quarter, fiscal_year, research_cat, dry_run
            )
            if letter_created:
                org_created += 1

            self.stdout.write(
                self.style.SUCCESS(f"  Created {org_created} todos")
            )
            total_created += org_created

        self.stdout.write(
            self.style.SUCCESS(f'\nDone! Created {total_created} todos total.')
        )

    def _get_or_create_category(self, org, name, category_type, color, dry_run):
        """Get or create a todo category."""
        try:
            return TodoCategory.objects.get(
                organization=org,
                category_type=category_type
            )
        except TodoCategory.DoesNotExist:
            if dry_run:
                self.stdout.write(f"    [DRY RUN] Would create category: {name}")
                return None
            return TodoCategory.objects.create(
                organization=org,
                name=name,
                slug=category_type,
                category_type=category_type,
                color=color,
                order=1 if category_type == 'maintenance' else 2
            )

    def _create_quarterly_todo(self, org, company, quarter, fiscal_year, category, dry_run):
        """Create a quarterly update todo for a company if it doesn't exist."""
        # Check if todo already exists for this company/quarter
        exists = Todo.objects.filter(
            organization=org,
            company=company,
            quarter=quarter,
            todo_type=Todo.TodoType.QUARTERLY_UPDATE
        ).exists()

        if exists:
            return False

        if dry_run:
            self.stdout.write(
                f"    [DRY RUN] Would create: {quarter} update for {company.name}"
            )
            return True

        Todo.objects.create(
            organization=org,
            company=company,
            title=f"{quarter} Quarterly Update: {company.name}",
            description=f"Review {company.name}'s {quarter} results, filings, and any material updates.",
            category=category,
            todo_type=Todo.TodoType.QUARTERLY_UPDATE,
            is_auto_generated=True,
            quarter=quarter,
            fiscal_year=fiscal_year
        )
        self.stdout.write(f"    Created: {quarter} update for {company.name}")
        return True

    def _create_investor_letter_todo(self, org, quarter, fiscal_year, category, dry_run):
        """Create the quarterly investor letter review todo."""
        exists = Todo.objects.filter(
            organization=org,
            quarter=quarter,
            todo_type=Todo.TodoType.INVESTOR_LETTER
        ).exists()

        if exists:
            self.stdout.write(f"    Skipping investor letter todo - already exists")
            return False

        if dry_run:
            self.stdout.write(
                f"    [DRY RUN] Would create: {quarter} Investor Letter Review"
            )
            return True

        Todo.objects.create(
            organization=org,
            company=None,
            title=f"{quarter} Investor Letter Review",
            description=(
                f"Review investor letters from {quarter}. "
                "Document key insights and add interesting companies to watchlist."
            ),
            category=category,
            todo_type=Todo.TodoType.INVESTOR_LETTER,
            is_auto_generated=True,
            quarter=quarter,
            fiscal_year=fiscal_year
        )
        self.stdout.write(f"    Created: {quarter} Investor Letter Review")
        return True
