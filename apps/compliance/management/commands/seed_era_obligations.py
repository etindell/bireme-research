from django.core.management.base import BaseCommand
from apps.organizations.models import Organization
from apps.compliance.models import ComplianceObligation, ComplianceSettings


ANNUAL_OBLIGATIONS = [
    {
        'title': 'Form ADV annual amendment',
        'description': 'File Form ADV annual updating amendment with the SEC via IARD within 90 days of fiscal year end.',
        'frequency': 'ANNUAL',
        'default_due_month': 3,
        'default_due_day': 31,
        'category': 'FORM_ADV',
        'jurisdiction': 'SEC',
        'tags': 'annual,regulatory,adv,filing',
        'owner_role': 'CCO',
    },
    {
        'title': 'Form ADV-NR filing',
        'description': 'File Form ADV-NR for non-US principals with the SEC.',
        'frequency': 'ANNUAL',
        'default_due_month': 3,
        'default_due_day': 31,
        'category': 'FORM_ADV',
        'jurisdiction': 'SEC',
        'tags': 'annual,regulatory,adv-nr,filing',
        'owner_role': 'CCO',
    },
    {
        'title': 'Form PF (if AUM > $150M)',
        'description': 'File Form PF if required based on AUM exceeding $150M threshold.',
        'frequency': 'ANNUAL',
        'default_due_month': 4,
        'default_due_day': 30,
        'category': 'FORM_PF',
        'jurisdiction': 'SEC',
        'conditional_flag': 'is_form_pf_applicable',
        'tags': 'annual,regulatory,form-pf,filing',
        'owner_role': 'CCO',
    },
    {
        'title': 'Blue sky renewal — NY',
        'description': 'Annual blue sky renewal filing for New York.',
        'frequency': 'ANNUAL',
        'category': 'BLUE_SKY',
        'jurisdiction': 'US-NY',
        'tags': 'annual,blue-sky,ny',
        'owner_role': 'CCO',
    },
    {
        'title': 'Blue sky renewal — CT',
        'description': 'Annual blue sky renewal filing for Connecticut.',
        'frequency': 'ANNUAL',
        'category': 'BLUE_SKY',
        'jurisdiction': 'US-CT',
        'tags': 'annual,blue-sky,ct',
        'owner_role': 'CCO',
    },
    {
        'title': 'Blue sky renewal — TX',
        'description': 'Annual blue sky renewal filing for Texas.',
        'frequency': 'ANNUAL',
        'category': 'BLUE_SKY',
        'jurisdiction': 'US-TX',
        'tags': 'annual,blue-sky,tx',
        'owner_role': 'CCO',
    },
]


EVENT_DRIVEN_OBLIGATIONS = [
    {
        'title': 'Form D filing',
        'description': 'File Form D with the SEC within 15 days of first sale.',
        'frequency': 'EVENT_DRIVEN',
        'category': 'FORM_D',
        'jurisdiction': 'SEC',
        'advance_notice_days': 15,
        'tags': 'event-driven,regulatory,form-d,filing',
        'owner_role': 'CCO',
    },
    {
        'title': 'Blue sky notice — NY — Form 99',
        'description': 'Form 99 notice filing via NASAA EFD for New York.',
        'frequency': 'EVENT_DRIVEN',
        'category': 'BLUE_SKY',
        'jurisdiction': 'US-NY',
        'due_date_reference': 'BEFORE_EVENT',
        'tags': 'event-driven,blue-sky,ny',
        'owner_role': 'CCO',
    },
    {
        'title': 'Blue sky notice — CT — NASAA EFD',
        'description': 'NASAA EFD notice filing for Connecticut.',
        'frequency': 'EVENT_DRIVEN',
        'category': 'BLUE_SKY',
        'jurisdiction': 'US-CT',
        'tags': 'event-driven,blue-sky,ct',
        'owner_role': 'CCO',
    },
    {
        'title': 'Blue sky notice — TX — NASAA EFD',
        'description': 'NASAA EFD notice filing for Texas.',
        'frequency': 'EVENT_DRIVEN',
        'category': 'BLUE_SKY',
        'jurisdiction': 'US-TX',
        'tags': 'event-driven,blue-sky,tx',
        'owner_role': 'CCO',
    },
    {
        'title': 'New investor jurisdiction assessment',
        'description': 'Assess blue sky filing requirements for a new investor jurisdiction.',
        'frequency': 'EVENT_DRIVEN',
        'category': 'BLUE_SKY',
        'tags': 'event-driven,blue-sky',
        'owner_role': 'CCO',
    },
    {
        'title': 'Form ADV other-than-annual amendment',
        'description': 'File other-than-annual amendment to Form ADV with the SEC when material changes occur.',
        'frequency': 'EVENT_DRIVEN',
        'category': 'FORM_ADV',
        'jurisdiction': 'SEC',
        'tags': 'event-driven,regulatory,adv,filing',
        'owner_role': 'CCO',
    },
]


ONE_TIME_OBLIGATIONS = [
    {
        'title': 'FinCEN AML/CFT program',
        'description': 'Establish AML/CFT compliance program per FinCEN requirements.',
        'frequency': 'ONE_TIME',
        'default_due_month': 1,
        'default_due_day': 1,
        'category': 'AML_CFT',
        'tags': 'one-time,regulatory,aml-cft',
        'owner_role': 'CCO',
    },
]


PLACEHOLDER_OBLIGATIONS = [
    {
        'title': 'Alberta Securities Commission — NI 31-103 exemption notice',
        'description': 'REQUIRES LEGAL REVIEW — Alberta NI 31-103 exemption notice filing.',
        'frequency': 'EVENT_DRIVEN',
        'category': 'INTERNATIONAL',
        'jurisdiction': 'CA-AB',
        'is_placeholder': True,
        'tags': 'placeholder,international,alberta',
        'owner_role': 'CCO',
    },
    {
        'title': 'Alberta investor compliance',
        'description': 'REQUIRES LEGAL REVIEW — Alberta investor compliance assessment.',
        'frequency': 'EVENT_DRIVEN',
        'category': 'INTERNATIONAL',
        'jurisdiction': 'CA-AB',
        'is_placeholder': True,
        'tags': 'placeholder,international,alberta',
        'owner_role': 'CCO',
    },
]


MONTHLY_OBLIGATIONS = [
    {
        'title': 'Monthly close: QuickBooks expenses review',
        'description': 'Review and approve all expenses in QuickBooks for the month.',
        'frequency': 'MONTHLY',
        'default_due_day': 10,
        'category': 'MONTHLY_CLOSE',
        'tags': 'monthly-close,financial',
        'owner_role': 'Fund Admin',
    },
    {
        'title': 'Monthly close: Save bank statements to Drive',
        'description': 'Archive bank statements to Google Drive.',
        'frequency': 'MONTHLY',
        'default_due_day': 10,
        'category': 'MONTHLY_CLOSE',
        'tags': 'monthly-close,archiving',
        'owner_role': 'Fund Admin',
    },
]


ALL_OBLIGATIONS = (
    ANNUAL_OBLIGATIONS
    + EVENT_DRIVEN_OBLIGATIONS
    + ONE_TIME_OBLIGATIONS
    + PLACEHOLDER_OBLIGATIONS
    + MONTHLY_OBLIGATIONS
)


class Command(BaseCommand):
    help = 'Seed ERA-specific compliance obligations for an organization'

    def add_arguments(self, parser):
        parser.add_argument('--org', type=str, required=True, help='Organization slug')

    def handle(self, *args, **options):
        try:
            org = Organization.objects.get(slug=options['org'])
        except Organization.DoesNotExist:
            self.stderr.write(f"Organization '{options['org']}' not found.")
            return

        # Ensure settings exist
        ComplianceSettings.objects.get_or_create(organization=org)

        # Deactivate ALL existing obligations for this org (RIA templates)
        deactivated = ComplianceObligation.objects.filter(
            organization=org, is_active=True
        ).update(is_active=False)
        self.stdout.write(f"Deactivated {deactivated} existing obligations.")

        created = 0
        skipped = 0

        for obl_data in ALL_OBLIGATIONS:
            title = obl_data['title']
            defaults = dict(obl_data)
            defaults.pop('title', None)
            defaults['is_active'] = True

            _, was_created = ComplianceObligation.objects.get_or_create(
                organization=org,
                title=title,
                defaults=defaults,
            )
            if was_created:
                created += 1
                self.stdout.write(f'  Created: {title}')
            else:
                # Re-activate if it already exists
                ComplianceObligation.objects.filter(
                    organization=org, title=title
                ).update(is_active=True)
                skipped += 1
                self.stdout.write(f'  Exists (re-activated): {title}')

        self.stdout.write(self.style.SUCCESS(
            f'Done. Created {created} obligations, re-activated {skipped} existing.'
        ))
