import logging
from datetime import date

from django.conf import settings
from django.core.mail import send_mail

from apps.compliance.models import ComplianceObligation, ComplianceTask, ComplianceSettings

logger = logging.getLogger(__name__)


def _max_day(month):
    """Return the maximum valid day for a month."""
    if month == 2:
        return 28
    if month in (4, 6, 9, 11):
        return 30
    return 31


def _period_label(frequency, month=None, quarter=None, year=None):
    """Build a human-readable period label for a task instance."""
    if frequency == ComplianceObligation.Frequency.MONTHLY and month and year:
        return date(year, month, 1).strftime('%B %Y')
    if frequency == ComplianceObligation.Frequency.QUARTERLY and quarter:
        return f"Q{quarter} {year}" if year else f"Q{quarter}"
    if frequency == ComplianceObligation.Frequency.ANNUAL and year:
        return str(year)
    if frequency == ComplianceObligation.Frequency.ONE_TIME and year:
        return str(year)
    return ''


def generate_tasks(organization, year, regenerate=False, dry_run=False):
    """
    Generate ComplianceTask instances from active ComplianceObligation records
    for a given year.

    EVENT_DRIVEN obligations are skipped -- those tasks are created by explicit
    user actions (e.g. adding an InvestorJurisdiction).

    Deduplication key: year + obligation + fund (fund is NULL for firm-level).

    Returns (created_count, skipped_count).
    """
    comp_settings = ComplianceSettings.objects.filter(organization=organization).first()

    obligations = ComplianceObligation.objects.filter(
        organization=organization, is_active=True
    )

    created_count = 0
    skipped_count = 0

    for obligation in obligations:
        # Skip event-driven obligations -- they are created by user actions
        if obligation.frequency == ComplianceObligation.Frequency.EVENT_DRIVEN:
            skipped_count += 1
            continue

        # Check conditional flag
        if obligation.conditional_flag:
            if comp_settings:
                flag_value = getattr(comp_settings, obligation.conditional_flag, False)
            else:
                flag_value = False
            if not flag_value:
                skipped_count += 1
                continue

        instances_to_create = []

        if obligation.frequency == ComplianceObligation.Frequency.MONTHLY:
            for month in range(1, 13):
                due_day = obligation.default_due_day or (
                    comp_settings.monthly_close_due_day if comp_settings else 10
                )
                # Due date is in the following month
                if month == 12:
                    d = date(year + 1, 1, min(due_day, 28))
                else:
                    d = date(year, month + 1, min(due_day, _max_day(month + 1)))
                month_name = date(year, month, 1).strftime('%B %Y')
                instances_to_create.append({
                    'month': month,
                    'due_date': d,
                    'title': f"{obligation.title} ({month_name})",
                    'period_label': month_name,
                    'fund': None,
                })

        elif obligation.frequency == ComplianceObligation.Frequency.QUARTERLY:
            quarter_info = [
                (1, date(year, 4, 30)),
                (2, date(year, 7, 30)),
                (3, date(year, 10, 30)),
                (4, date(year, 1, 30)),
            ]
            for q, default_due in quarter_info:
                if obligation.quarter and obligation.quarter != q:
                    continue
                due_date = default_due
                if obligation.default_due_month and obligation.default_due_day:
                    dm = obligation.default_due_month
                    dd = obligation.default_due_day
                    due_date = date(year, dm, min(dd, _max_day(dm)))
                quarter_label = f"Q{q}"
                title = obligation.title
                if "(Q" in title:
                    for i in range(1, 5):
                        title = title.replace(f"(Q{i})", f"({quarter_label})")
                else:
                    title = f"{title} ({quarter_label})"
                instances_to_create.append({
                    'month': due_date.month,
                    'due_date': due_date,
                    'title': title,
                    'period_label': f"Q{q} {year}",
                    'fund': None,
                })

        elif obligation.frequency == ComplianceObligation.Frequency.ANNUAL:
            dm = obligation.default_due_month or 12
            dd = obligation.default_due_day or 31
            due_date = date(year, dm, min(dd, _max_day(dm)))
            instances_to_create.append({
                'month': dm,
                'due_date': due_date,
                'title': obligation.title,
                'period_label': str(year),
                'fund': None,
            })

        elif obligation.frequency == ComplianceObligation.Frequency.ONE_TIME:
            if obligation.default_due_month and obligation.default_due_day:
                dm = obligation.default_due_month
                dd = obligation.default_due_day
                due_date = date(year, dm, min(dd, _max_day(dm)))
                instances_to_create.append({
                    'month': dm,
                    'due_date': due_date,
                    'title': obligation.title,
                    'period_label': str(year),
                    'fund': None,
                })

        for inst in instances_to_create:
            # Fund-level dedup: year + obligation + fund (fund can be None)
            existing = ComplianceTask.all_objects.filter(
                obligation=obligation,
                year=year,
                fund=inst['fund'],
                organization=organization,
            )
            # For monthly/quarterly, also match on due_date to allow multiple per year
            if obligation.frequency in (
                ComplianceObligation.Frequency.MONTHLY,
                ComplianceObligation.Frequency.QUARTERLY,
            ):
                existing = existing.filter(due_date=inst['due_date'])

            existing = existing.first()

            if existing and not regenerate:
                skipped_count += 1
                continue

            if existing and regenerate:
                if existing.status == ComplianceTask.Status.COMPLETED:
                    skipped_count += 1
                    continue
                if not dry_run:
                    existing.delete(hard=True)

            if not dry_run:
                ComplianceTask.objects.create(
                    organization=organization,
                    template=obligation,
                    obligation=obligation,
                    fund=inst['fund'],
                    title=inst['title'],
                    description=obligation.description,
                    year=year,
                    month=inst['month'],
                    due_date=inst['due_date'],
                    tags=obligation.tags,
                    conditional_flag=obligation.conditional_flag,
                    is_conditional=bool(obligation.conditional_flag),
                    period_label=inst['period_label'],
                )
            created_count += 1

    # Send email notification
    _send_generation_notification(organization, year, created_count, skipped_count, dry_run)

    return created_count, skipped_count


def _send_generation_notification(organization, year, created_count, skipped_count, dry_run):
    """Send email notification after task generation completes."""
    if dry_run:
        return

    subject = f"Compliance tasks generated for {organization} — {year}"
    message = (
        f"Task generation completed for {organization}, year {year}.\n\n"
        f"Created: {created_count}\n"
        f"Skipped: {skipped_count}\n"
    )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.DEFAULT_FROM_EMAIL],
            fail_silently=True,
        )
    except Exception:
        logger.exception("Failed to send task generation notification email")
