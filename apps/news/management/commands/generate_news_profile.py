"""
Management command to generate a news preference profile from user feedback.

Collects thumbs-up/down feedback on news items, sends to Gemini to produce
a natural language preference profile, and stores it on the Organization.
"""
import json
import os

from django.core.management.base import BaseCommand

from apps.news.models import CompanyNews
from apps.organizations.models import Organization


PROFILE_PROMPT = """You are analyzing a user's feedback on financial news items to build a preference profile.

Below is a list of news items the user has marked as LIKED (thumbs up) or DISLIKED (thumbs down).

Based on these signals, write a 2-4 sentence preference profile that describes:
- What types of news this user considers important
- What types of news this user considers unimportant or distracting
- Any patterns in company types, event types, or importance levels they prefer

Be specific and actionable — this profile will be injected into a news classification prompt to help an AI calibrate importance ratings and story selection.

FEEDBACK DATA:
{feedback_items}

Write ONLY the preference profile (2-4 sentences), no preamble or explanation."""


class Command(BaseCommand):
    help = 'Generate a news preference profile from user feedback (thumbs up/down)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--org',
            type=str,
            help='Organization slug (default: all organizations)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print the generated profile without saving',
        )

    def handle(self, *args, **options):
        orgs = Organization.objects.all()
        if options['org']:
            orgs = orgs.filter(slug=options['org'])
            if not orgs.exists():
                self.stderr.write(
                    self.style.ERROR(f"Organization not found: {options['org']}")
                )
                return

        for org in orgs:
            self._generate_for_org(org, dry_run=options['dry_run'])

    def _generate_for_org(self, org, dry_run=False):
        # Collect feedback items (up to 100 most recent)
        feedback_qs = CompanyNews.objects.filter(
            organization=org,
            feedback__isnull=False,
        ).select_related('company').order_by('-published_at')[:100]

        if not feedback_qs:
            self.stdout.write(
                self.style.WARNING(f"[{org.slug}] No feedback items found — skipping")
            )
            return

        # Format feedback for the prompt
        lines = []
        for item in feedback_qs:
            label = 'LIKED' if item.feedback == CompanyNews.Feedback.THUMBS_UP else 'DISLIKED'
            lines.append(
                f"[{label}] {item.headline} | "
                f"Summary: {item.summary[:200]} | "
                f"Company: {item.company.name} | "
                f"Event type: {item.event_type} | "
                f"Importance: {item.importance}"
            )

        feedback_text = '\n'.join(lines)
        self.stdout.write(f"[{org.slug}] Collected {len(lines)} feedback items")

        # Call Gemini
        try:
            from google import genai
        except ImportError:
            self.stderr.write(self.style.ERROR("google-genai package not installed"))
            return

        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            self.stderr.write(self.style.ERROR("GEMINI_API_KEY not set"))
            return

        prompt = PROFILE_PROMPT.format(feedback_items=feedback_text)

        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=prompt,
            )
            profile = response.text.strip()
        except Exception as e:
            self.stderr.write(
                self.style.ERROR(f"[{org.slug}] Gemini call failed: {e}")
            )
            return

        self.stdout.write(f"[{org.slug}] Generated profile:")
        self.stdout.write(f"  {profile}")

        if dry_run:
            self.stdout.write(self.style.WARNING("  (dry run — not saved)"))
        else:
            org.set_news_preference_profile(profile)
            self.stdout.write(self.style.SUCCESS(f"  Saved to organization settings"))
