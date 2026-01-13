"""
Management command to check and fix imported notes flags.
"""
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.notes.models import Note


class Command(BaseCommand):
    help = 'Check and fix is_imported flags for notes'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Actually fix the notes (without this flag, just reports)'
        )
        parser.add_argument(
            '--days',
            type=int,
            default=1,
            help='Check notes created in the last N days (default: 1)'
        )

    def handle(self, *args, **options):
        fix = options['fix']
        days = options['days']

        cutoff = timezone.now() - timedelta(days=days)

        self.stdout.write(f"\n=== Notes Summary ===")

        total = Note.objects.count()
        imported_true = Note.objects.filter(is_imported=True).count()
        imported_false = Note.objects.filter(is_imported=False).count()
        with_written_at = Note.objects.filter(written_at__isnull=False).count()

        self.stdout.write(f"Total notes: {total}")
        self.stdout.write(f"is_imported=True: {imported_true}")
        self.stdout.write(f"is_imported=False: {imported_false}")
        self.stdout.write(f"Has written_at: {with_written_at}")

        # Check for notes that have written_at but is_imported=False (should be fixed)
        missed = Note.objects.filter(written_at__isnull=False, is_imported=False).count()
        if missed:
            self.stdout.write(self.style.WARNING(
                f"\nFound {missed} notes with written_at but is_imported=False"
            ))
            if fix:
                updated = Note.objects.filter(
                    written_at__isnull=False,
                    is_imported=False
                ).update(is_imported=True)
                self.stdout.write(self.style.SUCCESS(f"Fixed {updated} notes"))

        # Check recent notes
        self.stdout.write(f"\n=== Notes created in last {days} day(s) ===")

        recent = Note.objects.filter(created_at__gte=cutoff)
        recent_total = recent.count()
        recent_imported = recent.filter(is_imported=True).count()
        recent_manual = recent.filter(is_imported=False).count()

        self.stdout.write(f"Total recent: {recent_total}")
        self.stdout.write(f"Marked as imported: {recent_imported}")
        self.stdout.write(f"Marked as manual: {recent_manual}")

        if recent_manual > 0:
            self.stdout.write(f"\nRecent 'manual' notes (is_imported=False):")
            for note in recent.filter(is_imported=False)[:20]:
                self.stdout.write(
                    f"  [{note.pk}] {note.title[:60]} "
                    f"(written_at: {note.written_at}, created: {note.created_at.date()})"
                )

            if recent_manual > 20:
                self.stdout.write(f"  ... and {recent_manual - 20} more")

        self.stdout.write("")
