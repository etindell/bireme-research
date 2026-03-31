"""
Management command to sync Google Tasks -> Bireme Research todos.

Polls Google Tasks API for tasks prefixed with 'br:' and creates
corresponding Todo objects. Uses GoogleTasksSyncState for incremental sync.

Usage:
    python manage.py sync_google_tasks
    python manage.py sync_google_tasks --dry-run
    python manage.py sync_google_tasks --full  # ignore last sync time

Designed to run on Railway cron every 5 minutes.
"""
import logging
from datetime import datetime, timezone, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from allauth.socialaccount.models import SocialAccount

from apps.users.models import User
from apps.todos.models import Todo, GoogleTasksSyncState
from apps.todos.google_tasks import (
    get_google_credentials,
    fetch_tasks_from_google,
    filter_bireme_tasks,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync Google Tasks (prefixed with br:) to Bireme Research todos'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be synced without creating todos',
        )
        parser.add_argument(
            '--full',
            action='store_true',
            help='Full sync (ignore last sync timestamp)',
        )
        parser.add_argument(
            '--user',
            type=str,
            help='Specific user email (default: all users with Google tokens)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        full_sync = options['full']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes will be made'))

        # Get users to sync
        if options['user']:
            users = User.objects.filter(email=options['user'], is_active=True)
            if not users.exists():
                self.stderr.write(self.style.ERROR(f"User '{options['user']}' not found"))
                return
        else:
            google_user_ids = SocialAccount.objects.filter(
                provider='google'
            ).values_list('user_id', flat=True)
            users = User.objects.filter(id__in=google_user_ids, is_active=True)

        total_created = 0

        for user in users:
            self.stdout.write(f"\nSyncing for user: {user.email}")

            creds = get_google_credentials(user)
            if not creds:
                self.stdout.write(self.style.WARNING(
                    f"  Skipping - no valid Google credentials"
                ))
                continue

            # Determine updatedMin for incremental sync
            updated_min = None
            if not full_sync:
                try:
                    sync_state = GoogleTasksSyncState.objects.get(user=user)
                    updated_min = sync_state.last_synced_at.isoformat()
                except GoogleTasksSyncState.DoesNotExist:
                    # First sync: look back 24 hours
                    updated_min = (
                        datetime.now(timezone.utc) - timedelta(hours=24)
                    ).isoformat()

            self.stdout.write(f"  Updated since: {updated_min or 'all time'}")

            # Fetch from Google
            try:
                raw_tasks = fetch_tasks_from_google(creds, updated_min=updated_min)
                self.stdout.write(f"  Fetched {len(raw_tasks)} tasks from Google")
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"  API error: {e}"))
                continue

            # Filter for br: prefix
            bireme_tasks = filter_bireme_tasks(raw_tasks)
            self.stdout.write(f"  Found {len(bireme_tasks)} with 'br:' prefix")

            # Get user's organization
            org = user.get_default_organization()
            if not org:
                self.stdout.write(self.style.WARNING(
                    f"  Skipping - no organization"
                ))
                continue

            # Create todos
            created = 0
            for task_data in bireme_tasks:
                if Todo.objects.filter(
                    google_task_id=task_data['google_task_id']
                ).exists():
                    self.stdout.write(f"  Skipping (exists): {task_data['title']}")
                    continue

                if dry_run:
                    self.stdout.write(
                        f"  [DRY RUN] Would create: {task_data['title']}"
                    )
                    created += 1
                    continue

                with transaction.atomic():
                    Todo.objects.create(
                        organization=org,
                        title=task_data['title'],
                        description=task_data['notes'],
                        todo_type=Todo.TodoType.CUSTOM,
                        is_auto_generated=True,
                        scope=Todo.Scope.PERSONAL,
                        assigned_to=user,
                        created_by=user,
                        google_task_id=task_data['google_task_id'],
                    )
                    self.stdout.write(
                        self.style.SUCCESS(f"  Created: {task_data['title']}")
                    )
                    created += 1

            # Update last sync time
            if not dry_run:
                GoogleTasksSyncState.objects.update_or_create(
                    user=user,
                    defaults={'last_synced_at': datetime.now(timezone.utc)},
                )

            total_created += created

        self.stdout.write(
            self.style.SUCCESS(f'\nDone! Created {total_created} todos total.')
        )
