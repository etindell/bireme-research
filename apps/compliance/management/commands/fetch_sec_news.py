from django.core.management.base import BaseCommand
from apps.organizations.models import Organization
from apps.compliance.models import SECNewsItem
from apps.compliance.services.rss import fetch_all_feeds


class Command(BaseCommand):
    help = 'Fetch SEC news from RSS feeds'

    def add_arguments(self, parser):
        parser.add_argument('--org', type=str, help='Organization slug (all orgs if omitted)')
        parser.add_argument('--all', action='store_true', help='Fetch all items, not just RIA-relevant')

    def handle(self, *args, **options):
        filter_relevant = not options['all']

        if options['org']:
            orgs = Organization.objects.filter(slug=options['org'])
            if not orgs.exists():
                self.stderr.write(f"Organization '{options['org']}' not found.")
                return
        else:
            orgs = Organization.objects.filter(is_deleted=False)

        items = fetch_all_feeds(filter_relevant=filter_relevant)
        self.stdout.write(f'Fetched {len(items)} items from SEC feeds.')

        for org in orgs:
            created = 0
            for item in items:
                _, was_created = SECNewsItem.objects.get_or_create(
                    organization=org,
                    guid=item['guid'],
                    defaults={
                        'title': item['title'],
                        'link': item['link'],
                        'description': item['description'],
                        'published_at': item['published_at'],
                        'source': item['source'],
                        'is_relevant': item.get('is_relevant', True),
                    },
                )
                if was_created:
                    created += 1
            self.stdout.write(self.style.SUCCESS(
                f'{org.name}: {created} new items stored.'
            ))
