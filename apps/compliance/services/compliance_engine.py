"""
Compliance Engine — scans triggers and creates tasks for what needs doing.

Idempotent: running multiple times won't create duplicate tasks.
Driven by actual data (NASAA EFD filings, fund dates, principal residency)
rather than static templates.
"""

from datetime import date, timedelta

from django.utils import timezone

from apps.compliance.models import (
    ComplianceSettings, ComplianceObligation, ComplianceTask,
    Fund, FundPrincipal, InvestorJurisdiction,
)


def _find_or_create_obligation(org, title, category, frequency, jurisdiction='SEC', **kwargs):
    """Get or create an obligation template for a given trigger."""
    obj, _ = ComplianceObligation.objects.get_or_create(
        organization=org,
        title=title,
        defaults={
            'category': category,
            'frequency': frequency,
            'jurisdiction': jurisdiction,
            'is_active': True,
            **kwargs,
        }
    )
    return obj


def _task_exists(org, obligation, year, fund=None):
    """Check if a task already exists for this obligation/year/fund combo."""
    return ComplianceTask.objects.filter(
        organization=org,
        obligation=obligation,
        year=year,
        fund=fund,
    ).exclude(
        status=ComplianceTask.Status.NOT_APPLICABLE,
    ).exists()


def _create_task(org, obligation, title, due_date, fund=None, description='', **kwargs):
    """Create a compliance task if one doesn't already exist."""
    year = due_date.year if due_date else date.today().year
    month = due_date.month if due_date else 1

    if _task_exists(org, obligation, year, fund):
        return None

    task = ComplianceTask.objects.create(
        organization=org,
        obligation=obligation,
        template=obligation,  # backwards compat
        fund=fund,
        title=title,
        description=description,
        due_date=due_date,
        year=year,
        month=month,
        period_label=str(year),
        **kwargs,
    )
    return task


def check_form_adv_triggers(org, settings_obj):
    """
    Form ADV triggers (adviser-level):
    - Annual amendment due 90 days after fiscal year end
    """
    tasks_created = []
    today = date.today()
    current_year = today.year

    # Annual ADV amendment — due 90 days after FYE
    fye_month = settings_obj.fiscal_year_end_month or 12
    fye_day = settings_obj.fiscal_year_end_day or 31
    # FYE for the prior year triggers filing in current year
    fye_date = date(current_year - 1, fye_month, min(fye_day, 28))
    adv_due = fye_date + timedelta(days=90)

    obligation = _find_or_create_obligation(
        org, 'Form ADV annual amendment', 'FORM_ADV', 'ANNUAL',
        description='File Form ADV Part 1A annual updating amendment on IARD within 90 days of fiscal year-end. ERAs file Part 1A only.',
        filing_url='https://www.iard.com/',
    )
    task = _create_task(
        org, obligation,
        f'Form ADV annual amendment ({current_year})',
        adv_due,
        description=f'Annual updating amendment for fiscal year ending {fye_date.strftime("%b %d, %Y")}. File on IARD.',
        delegated_to='COMPLIANCE_COUNSEL',
        delegated_to_name=settings_obj.primary_compliance_counsel or '',
    )
    if task:
        tasks_created.append(task)

    return tasks_created


def check_form_adv_nr_triggers(org, settings_obj):
    """
    Form ADV-NR triggers:
    - Annual renewal for each non-US principal, due with ADV amendment
    """
    tasks_created = []
    today = date.today()
    current_year = today.year

    fye_month = settings_obj.fiscal_year_end_month or 12
    fye_day = settings_obj.fiscal_year_end_day or 31
    fye_date = date(current_year - 1, fye_month, min(fye_day, 28))
    adv_due = fye_date + timedelta(days=90)

    non_us_principals = FundPrincipal.objects.filter(
        organization=org, requires_adv_nr=True
    ).select_related('fund')

    for principal in non_us_principals:
        obligation = _find_or_create_obligation(
            org, f'Form ADV-NR — {principal.name}', 'FORM_ADV', 'ANNUAL',
            description=f'File/renew Form ADV-NR for {principal.name} ({principal.residency_jurisdiction}). Required for non-US principals.',
        )
        task = _create_task(
            org, obligation,
            f'Form ADV-NR renewal — {principal.name} ({current_year})',
            adv_due,
            fund=principal.fund,
            description=f'Renew ADV-NR for {principal.name} (residency: {principal.residency_jurisdiction}). File with annual ADV amendment.',
            delegated_to='COMPLIANCE_COUNSEL',
            delegated_to_name=settings_obj.primary_compliance_counsel or '',
        )
        if task:
            tasks_created.append(task)

    return tasks_created


def check_form_d_triggers(org):
    """
    Form D triggers (per-fund):
    - Annual amendment before anniversary of last filing (if offering is continuous/open)
    - We detect this from NASAA EFD filing dates
    """
    tasks_created = []
    today = date.today()

    for fund in Fund.objects.filter(organization=org, is_active=True):
        # Find the most recent filing date from NASAA EFD data
        latest_jur = fund.investor_jurisdictions.filter(
            blue_sky_filing_date__isnull=False
        ).order_by('-blue_sky_filing_date').first()

        if not latest_jur:
            continue

        last_filing = latest_jur.blue_sky_filing_date
        # Anniversary is 1 year after the most recent filing
        anniversary = date(last_filing.year + 1, last_filing.month, min(last_filing.day, 28))

        # If anniversary is in the past for this year, push to next year
        if anniversary < today:
            anniversary = date(anniversary.year + 1, anniversary.month, min(anniversary.day, 28))

        obligation = _find_or_create_obligation(
            org, 'Form D annual amendment', 'FORM_D', 'ANNUAL',
            description='File Form D/A on EDGAR before the anniversary of the most recent filing. Required for continuous offerings (funds still accepting investors).',
            filing_url='https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=D&dateb=&owner=include&count=40&search_text=&action=getcompany',
        )
        task = _create_task(
            org, obligation,
            f'Form D amendment — {fund.name} (due {anniversary.strftime("%b %d, %Y")})',
            anniversary,
            fund=fund,
            description=f'Annual Form D/A for {fund.name}. Anniversary of last filing: {last_filing.strftime("%b %d, %Y")}. File on EDGAR before this date if offering is still continuous.',
        )
        if task:
            tasks_created.append(task)

    return tasks_created


def check_blue_sky_triggers(org):
    """
    Blue sky triggers (per-fund, per-state):
    - State filing expiry → renewal task
    - Form D amendment filed → need to amend state notices
    """
    tasks_created = []
    today = date.today()

    # 1. Expiring filings — create renewal tasks
    expiring = InvestorJurisdiction.objects.filter(
        organization=org,
        blue_sky_expires__isnull=False,
    ).select_related('fund')

    for jur in expiring:
        # Create renewal task 90 days before expiry
        renewal_due = jur.blue_sky_expires - timedelta(days=90)
        if renewal_due < today:
            renewal_due = today  # Already due

        obligation = _find_or_create_obligation(
            org,
            f'Blue sky renewal — {jur.jurisdiction_name}',
            'BLUE_SKY', 'EVENT_DRIVEN',
            jurisdiction=jur.jurisdiction_code,
            description=f'Renew state notice filing in {jur.jurisdiction_name} before expiry.',
            filing_url='https://nasaaefd.org/',
        )
        task = _create_task(
            org, obligation,
            f'Blue sky renewal — {jur.jurisdiction_name} — {jur.fund.name} (expires {jur.blue_sky_expires.strftime("%b %d, %Y")})',
            renewal_due,
            fund=jur.fund,
            description=f'Filing in {jur.jurisdiction_name} expires {jur.blue_sky_expires.strftime("%b %d, %Y")}. Renew via NASAA EFD before expiry.',
        )
        if task:
            tasks_created.append(task)

    # 2. Form D amendment propagation — if a Form D task exists for this year,
    #    create "amend state notices" tasks for each state
    form_d_tasks = ComplianceTask.objects.filter(
        organization=org,
        obligation__category='FORM_D',
        year=today.year,
        status__in=[ComplianceTask.Status.COMPLETED],
    ).select_related('fund')

    for fd_task in form_d_tasks:
        if not fd_task.fund:
            continue
        states = InvestorJurisdiction.objects.filter(
            fund=fd_task.fund, blue_sky_filed=True
        )
        for jur in states:
            if jur.jurisdiction_code == 'US-CA':
                continue  # CA doesn't require separate filing

            obligation = _find_or_create_obligation(
                org,
                f'Amend state notice — {jur.jurisdiction_name}',
                'BLUE_SKY', 'EVENT_DRIVEN',
                jurisdiction=jur.jurisdiction_code,
                filing_url='https://nasaaefd.org/',
            )
            task = _create_task(
                org, obligation,
                f'Amend state notice — {jur.jurisdiction_name} — {fd_task.fund.name} ({today.year})',
                fd_task.completed_at.date() + timedelta(days=30) if fd_task.completed_at else today + timedelta(days=30),
                fund=fd_task.fund,
                description=f'Form D/A was filed for {fd_task.fund.name}. Amend the state notice in {jur.jurisdiction_name} via NASAA EFD.',
            )
            if task:
                tasks_created.append(task)

    return tasks_created


def check_aml_cft_triggers(org, settings_obj):
    """
    FinCEN AML/CFT program (2028):
    - Preparation milestones starting 2027
    """
    tasks_created = []
    today = date.today()
    target = settings_obj.aml_cft_target_date or date(2028, 1, 1)

    if today.year < target.year - 1:
        return tasks_created  # Too early to start prep

    obligation = _find_or_create_obligation(
        org, 'FinCEN AML/CFT program', 'AML_CFT', 'ONE_TIME',
        description='Written AML/CFT compliance program required by FinCEN rule. Includes CIP, SAR procedures, beneficial ownership tracking.',
    )

    if today.year == target.year - 1:
        # Prep year — create planning task
        task = _create_task(
            org, obligation,
            f'AML/CFT program preparation — begin planning ({target.year - 1})',
            date(target.year - 1, 6, 30),
            description=f'FinCEN AML/CFT program deadline is {target.strftime("%b %d, %Y")}. Begin planning: engage counsel, draft policies, identify CIP/SAR requirements.',
            delegated_to='COMPLIANCE_COUNSEL',
            delegated_to_name=settings_obj.primary_compliance_counsel or '',
        )
        if task:
            tasks_created.append(task)
    elif today.year == target.year:
        # Deadline year
        task = _create_task(
            org, obligation,
            f'AML/CFT program — finalize and implement (due {target.strftime("%b %d, %Y")})',
            target,
            description='Finalize written AML/CFT compliance program. Must be in place by deadline.',
            delegated_to='COMPLIANCE_COUNSEL',
            delegated_to_name=settings_obj.primary_compliance_counsel or '',
        )
        if task:
            tasks_created.append(task)

    return tasks_created


def run_compliance_engine(org):
    """
    Run all compliance trigger checks for an organization.
    Creates tasks for anything that needs action.
    Returns a summary dict.
    """
    settings_obj = ComplianceSettings.objects.filter(organization=org).first()
    if not settings_obj:
        return {'error': 'No compliance settings configured', 'tasks_created': []}

    all_tasks = []

    # Run each trigger check
    all_tasks.extend(check_form_adv_triggers(org, settings_obj))
    all_tasks.extend(check_form_adv_nr_triggers(org, settings_obj))
    all_tasks.extend(check_form_d_triggers(org))
    all_tasks.extend(check_blue_sky_triggers(org))
    all_tasks.extend(check_aml_cft_triggers(org, settings_obj))

    return {
        'error': None,
        'tasks_created': all_tasks,
        'summary': {
            'total': len(all_tasks),
            'form_adv': len([t for t in all_tasks if t.obligation and t.obligation.category == 'FORM_ADV']),
            'form_d': len([t for t in all_tasks if t.obligation and t.obligation.category == 'FORM_D']),
            'blue_sky': len([t for t in all_tasks if t.obligation and t.obligation.category == 'BLUE_SKY']),
            'aml_cft': len([t for t in all_tasks if t.obligation and t.obligation.category == 'AML_CFT']),
        }
    }
