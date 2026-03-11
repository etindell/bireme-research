from datetime import date
from apps.compliance.models import ComplianceTaskTemplate, ComplianceTask, ComplianceSettings


def _max_day(month):
    """Return the maximum valid day for a month."""
    if month == 2:
        return 28
    if month in (4, 6, 9, 11):
        return 30
    return 31


def generate_tasks(organization, year, regenerate=False, dry_run=False):
    """
    Generate ComplianceTask instances from active templates for a given year.

    Returns (created_count, skipped_count).
    """
    settings = ComplianceSettings.objects.filter(organization=organization).first()

    templates = ComplianceTaskTemplate.objects.filter(
        organization=organization, is_active=True
    )

    created_count = 0
    skipped_count = 0

    for template in templates:
        # Check conditional flag
        if template.conditional_flag:
            if settings:
                flag_value = getattr(settings, template.conditional_flag, False)
            else:
                flag_value = False
            if not flag_value:
                skipped_count += 1
                continue

        instances_to_create = []

        if template.frequency == ComplianceTaskTemplate.Frequency.MONTHLY:
            for month in range(1, 13):
                due_day = template.default_due_day or (settings.monthly_close_due_day if settings else 10)
                # Due date is in the following month
                if month == 12:
                    d = date(year + 1, 1, min(due_day, 28))
                else:
                    d = date(year, month + 1, min(due_day, _max_day(month + 1)))
                month_name = date(year, month, 1).strftime('%B %Y')
                instances_to_create.append({
                    'month': month,
                    'due_date': d,
                    'title': f"{template.title} ({month_name})",
                })

        elif template.frequency == ComplianceTaskTemplate.Frequency.QUARTERLY:
            quarter_info = [
                (1, date(year, 4, 30)),
                (2, date(year, 7, 30)),
                (3, date(year, 10, 30)),
                (4, date(year, 1, 30)),
            ]
            for q, default_due in quarter_info:
                if template.quarter and template.quarter != q:
                    continue
                due_date = default_due
                if template.default_due_month and template.default_due_day:
                    dm = template.default_due_month
                    dd = template.default_due_day
                    due_date = date(year, dm, min(dd, _max_day(dm)))
                quarter_label = f"Q{q}"
                title = template.title
                if "(Q" in title:
                    for i in range(1, 5):
                        title = title.replace(f"(Q{i})", f"({quarter_label})")
                else:
                    title = f"{title} ({quarter_label})"
                instances_to_create.append({
                    'month': due_date.month,
                    'due_date': due_date,
                    'title': title,
                })

        elif template.frequency == ComplianceTaskTemplate.Frequency.ANNUAL:
            dm = template.default_due_month or 12
            dd = template.default_due_day or 31
            due_date = date(year, dm, min(dd, _max_day(dm)))
            instances_to_create.append({
                'month': dm,
                'due_date': due_date,
                'title': template.title,
            })

        elif template.frequency == ComplianceTaskTemplate.Frequency.ONE_TIME:
            if template.default_due_month and template.default_due_day:
                dm = template.default_due_month
                dd = template.default_due_day
                due_date = date(year, dm, min(dd, _max_day(dm)))
                instances_to_create.append({
                    'month': dm,
                    'due_date': due_date,
                    'title': template.title,
                })

        for inst in instances_to_create:
            existing = ComplianceTask.all_objects.filter(
                template=template,
                year=year,
                due_date=inst['due_date'],
                organization=organization,
            ).first()

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
                    template=template,
                    title=inst['title'],
                    description=template.description,
                    year=year,
                    month=inst['month'],
                    due_date=inst['due_date'],
                    tags=template.tags,
                    conditional_flag=template.conditional_flag,
                    is_conditional=bool(template.conditional_flag),
                )
            created_count += 1

    return created_count, skipped_count
