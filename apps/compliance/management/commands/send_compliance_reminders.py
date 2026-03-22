from datetime import timedelta

from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone

from apps.compliance.models import ComplianceTask
from apps.organizations.models import Organization


class Command(BaseCommand):
    help = 'Send compliance task reminders at 90, 30, and 7 day thresholds'

    def add_arguments(self, parser):
        parser.add_argument('--org', type=str, help='Organization slug (all orgs if omitted)')
        parser.add_argument('--dry-run', action='store_true', help='Preview without sending')

    def handle(self, *args, **options):
        orgs = Organization.objects.all()
        if options['org']:
            orgs = orgs.filter(slug=options['org'])

        today = timezone.now().date()
        total_sent = 0

        for org in orgs:
            tasks = ComplianceTask.objects.filter(
                organization=org,
                status__in=[
                    ComplianceTask.Status.NOT_STARTED,
                    ComplianceTask.Status.IN_PROGRESS,
                ],
                due_date__isnull=False,
            )

            for task in tasks:
                days_until = (task.due_date - today).days

                reminders = []
                if days_until <= 90 and not task.reminder_sent_90:
                    reminders.append(('90-day', 'reminder_sent_90'))
                if days_until <= 30 and not task.reminder_sent_30:
                    reminders.append(('30-day', 'reminder_sent_30'))
                if days_until <= 7 and not task.reminder_sent_7:
                    reminders.append(('7-day', 'reminder_sent_7'))

                for label, field in reminders:
                    if options['dry_run']:
                        self.stdout.write(f'  [DRY RUN] Would send {label} reminder: {task.title} (due {task.due_date})')
                    else:
                        subject = f'[Keelhaul] {label} reminder: {task.title}'
                        body = (
                            f'Compliance task reminder ({label}):\n\n'
                            f'Task: {task.title}\n'
                            f'Due: {task.due_date}\n'
                            f'Status: {task.get_status_display()}\n'
                            f'Days remaining: {days_until}\n'
                        )
                        if task.delegated_to_name:
                            body += f'Delegated to: {task.delegated_to_name}\n'

                        try:
                            send_mail(
                                subject,
                                body,
                                settings.DEFAULT_FROM_EMAIL,
                                [m.user.email for m in org.memberships.filter(is_deleted=False)],
                                fail_silently=False,
                            )
                        except Exception as e:
                            self.stderr.write(f'  Failed to send {label} reminder for {task.title}: {e}')
                            continue

                        setattr(task, field, True)
                        task.save(update_fields=[field, 'updated_at'])
                        total_sent += 1
                        self.stdout.write(f'  Sent {label} reminder: {task.title}')

        self.stdout.write(self.style.SUCCESS(f'Done. {total_sent} reminders sent.'))
