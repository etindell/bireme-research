import logging
from datetime import timedelta

from apps.compliance.models import ComplianceObligation, ComplianceTask, InvestorJurisdiction

logger = logging.getLogger(__name__)


def generate_blue_sky_task(investor_jurisdiction: InvestorJurisdiction):
    """
    Generate a blue sky filing ComplianceTask when an InvestorJurisdiction is
    added.  Called explicitly from the view (not via signal).

    Returns the created ComplianceTask, or None if no task is needed.
    """
    org = investor_jurisdiction.organization
    fund = investor_jurisdiction.fund
    code = investor_jurisdiction.jurisdiction_code
    first_sale = investor_jurisdiction.first_sale_date

    # US-CA: California — no separate filing needed
    if code == 'US-CA':
        return None

    # US-NY: Form 99 notice filing via NASAA EFD
    if code == 'US-NY':
        obligation = _get_or_create_obligation(
            organization=org,
            title='Blue sky notice — NY — Form 99',
            category=ComplianceObligation.Category.BLUE_SKY,
            jurisdiction='US-NY',
            frequency=ComplianceObligation.Frequency.EVENT_DRIVEN,
            due_date_reference=ComplianceObligation.DueDateReference.BEFORE_EVENT,
            description='Form 99 notice filing via NASAA EFD for New York.',
        )
        due_date = None
        if first_sale:
            due_date = first_sale - timedelta(days=1)
        return _create_task(
            obligation=obligation,
            investor_jurisdiction=investor_jurisdiction,
            fund=fund,
            due_date=due_date,
            title=f"Blue sky notice — NY — Form 99 — {fund.name}",
        )

    # US-CT, US-TX: NASAA EFD notice filing, due 15 days after first sale
    if code in ('US-CT', 'US-TX'):
        state_name = 'CT' if code == 'US-CT' else 'TX'
        obligation = _get_or_create_obligation(
            organization=org,
            title=f'Blue sky notice — {state_name} — NASAA EFD',
            category=ComplianceObligation.Category.BLUE_SKY,
            jurisdiction=code,
            frequency=ComplianceObligation.Frequency.EVENT_DRIVEN,
            description=f'NASAA EFD notice filing for {state_name}.',
        )
        due_date = None
        if first_sale:
            due_date = first_sale + timedelta(days=15)
        return _create_task(
            obligation=obligation,
            investor_jurisdiction=investor_jurisdiction,
            fund=fund,
            due_date=due_date,
            title=f"Blue sky notice — {state_name} — NASAA EFD — {fund.name}",
        )

    # CA-AB: Alberta — placeholder requiring legal review
    if code == 'CA-AB':
        obligation = _get_or_create_obligation(
            organization=org,
            title='Alberta Securities Commission — NI 31-103 exemption notice',
            category=ComplianceObligation.Category.INTERNATIONAL,
            jurisdiction='CA-AB',
            frequency=ComplianceObligation.Frequency.EVENT_DRIVEN,
            is_placeholder=True,
            description='REQUIRES LEGAL REVIEW — Alberta securities compliance assessment.',
        )
        return _create_task(
            obligation=obligation,
            investor_jurisdiction=investor_jurisdiction,
            fund=fund,
            due_date=None,
            title=f"Alberta compliance assessment — REQUIRES LEGAL REVIEW — {fund.name}",
            is_placeholder=True,
            description='REQUIRES LEGAL REVIEW — Alberta securities compliance assessment.',
        )

    # Other US states: generic blue sky assessment
    if code.startswith('US-'):
        obligation = _get_or_create_obligation(
            organization=org,
            title='New investor jurisdiction assessment',
            category=ComplianceObligation.Category.BLUE_SKY,
            frequency=ComplianceObligation.Frequency.EVENT_DRIVEN,
            description='Generic blue sky assessment for new investor jurisdiction.',
        )
        state_code = code.split('-', 1)[1] if '-' in code else code
        return _create_task(
            obligation=obligation,
            investor_jurisdiction=investor_jurisdiction,
            fund=fund,
            due_date=None,
            title=f"Blue sky assessment — {state_code} — {fund.name}",
        )

    # Non-US, non-Alberta: no automatic task
    return None


def _get_or_create_obligation(
    organization,
    title,
    category,
    frequency,
    jurisdiction='',
    due_date_reference=ComplianceObligation.DueDateReference.AFTER_EVENT,
    is_placeholder=False,
    description='',
):
    """Look up or create the ComplianceObligation for this filing type."""
    obligation, _ = ComplianceObligation.objects.get_or_create(
        organization=organization,
        title=title,
        defaults={
            'category': category,
            'frequency': frequency,
            'jurisdiction': jurisdiction,
            'due_date_reference': due_date_reference,
            'is_placeholder': is_placeholder,
            'description': description,
            'is_active': True,
        },
    )
    return obligation


def _create_task(
    obligation,
    investor_jurisdiction,
    fund,
    due_date,
    title,
    is_placeholder=False,
    description='',
):
    """Create the ComplianceTask linked to the obligation and fund."""
    from django.utils import timezone

    now = timezone.now().date()
    effective_due = due_date or now

    task = ComplianceTask.objects.create(
        organization=investor_jurisdiction.organization,
        template=obligation,
        obligation=obligation,
        fund=fund,
        title=title,
        description=description or obligation.description,
        year=effective_due.year,
        month=effective_due.month,
        due_date=effective_due,
        tags='blue-sky',
        period_label=f"{investor_jurisdiction.jurisdiction_name}",
    )
    return task
