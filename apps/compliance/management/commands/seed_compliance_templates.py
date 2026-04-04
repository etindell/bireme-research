from django.core.management.base import BaseCommand
from apps.organizations.models import Organization
from apps.compliance.models import ComplianceTaskTemplate, ComplianceSettings, SurveyTemplate


TEMPLATES = [
    # MONTHLY
    {'title': 'Monthly close: QuickBooks expenses review & approval', 'description': 'Review and approve all expenses in QuickBooks for the month.', 'frequency': 'MONTHLY', 'default_due_day': 10, 'tags': 'monthly-close,financial', 'owner_role': 'Fund Admin', 'suggested_evidence': 'Screenshot/PDF of QB expense approval, notes on exceptions.'},
    {'title': 'Monthly close: Record management fee accruals', 'description': 'Record management fee accruals in QuickBooks.', 'frequency': 'MONTHLY', 'default_due_day': 10, 'tags': 'monthly-close,financial', 'owner_role': 'Fund Admin', 'suggested_evidence': 'QB journal entry screenshot + calculation file link.'},
    {'title': 'Monthly close: Save bank statements & key invoices to Drive', 'description': 'Archive bank statements and important invoices to Google Drive.', 'frequency': 'MONTHLY', 'default_due_day': 10, 'tags': 'monthly-close,archiving', 'owner_role': 'Fund Admin', 'suggested_evidence': 'Bank statement PDF upload or link + folder path noted.'},
    {'title': 'Monthly check: Communications/marketing archiving health check', 'description': 'Verify that all communications and marketing materials are being properly archived.', 'frequency': 'MONTHLY', 'default_due_day': 15, 'tags': 'monthly-check,archiving,marketing', 'owner_role': 'CCO', 'suggested_evidence': 'Archive vendor screenshot or internal capture log.'},
    {'title': 'Monthly check: Exception log (trade errors / complaints / gifts / OBA / political contrib)', 'description': 'Review and update the exception log for trade errors, complaints, gifts, outside business activities, and political contributions.', 'frequency': 'MONTHLY', 'default_due_day': 15, 'tags': 'monthly-check,compliance', 'owner_role': 'CCO', 'suggested_evidence': "Updated log file upload/link; note 'no exceptions' if none."},
    # QUARTERLY ACCESS PERSON CERTIFICATION
    {'title': 'Quarterly access person certification and transaction report (Q4)', 'description': 'Collect Q4 access person certification and personal securities transaction reports.', 'frequency': 'QUARTERLY', 'quarter': 4, 'default_due_month': 1, 'default_due_day': 30, 'tags': 'quarterly,code-of-ethics,access-person', 'owner_role': 'CCO', 'suggested_evidence': 'Completed survey responses; report PDF; attestation note.', 'survey_template_slug': 'quarterly-access-person-certification'},
    {'title': 'Quarterly access person certification and transaction report (Q1)', 'description': 'Collect Q1 access person certification and personal securities transaction reports.', 'frequency': 'QUARTERLY', 'quarter': 1, 'default_due_month': 4, 'default_due_day': 30, 'tags': 'quarterly,code-of-ethics,access-person', 'owner_role': 'CCO', 'suggested_evidence': 'Completed survey responses; report PDF; attestation note.', 'survey_template_slug': 'quarterly-access-person-certification'},
    {'title': 'Quarterly access person certification and transaction report (Q2)', 'description': 'Collect Q2 access person certification and personal securities transaction reports.', 'frequency': 'QUARTERLY', 'quarter': 2, 'default_due_month': 7, 'default_due_day': 30, 'tags': 'quarterly,code-of-ethics,access-person', 'owner_role': 'CCO', 'suggested_evidence': 'Completed survey responses; report PDF; attestation note.', 'survey_template_slug': 'quarterly-access-person-certification'},
    {'title': 'Quarterly access person certification and transaction report (Q3)', 'description': 'Collect Q3 access person certification and personal securities transaction reports.', 'frequency': 'QUARTERLY', 'quarter': 3, 'default_due_month': 10, 'default_due_day': 30, 'tags': 'quarterly,code-of-ethics,access-person', 'owner_role': 'CCO', 'suggested_evidence': 'Completed survey responses; report PDF; attestation note.', 'survey_template_slug': 'quarterly-access-person-certification'},
    # QUARTERLY MARKETING
    {'title': 'Quarterly marketing/performance substantiation tie-out (Q1)', 'description': 'Verify marketing materials and performance claims are substantiated.', 'frequency': 'QUARTERLY', 'quarter': 1, 'default_due_month': 4, 'default_due_day': 30, 'tags': 'quarterly,marketing', 'owner_role': 'CCO', 'suggested_evidence': 'Review memo with tie-out documentation.'},
    {'title': 'Quarterly marketing/performance substantiation tie-out (Q2)', 'description': 'Verify marketing materials and performance claims are substantiated.', 'frequency': 'QUARTERLY', 'quarter': 2, 'default_due_month': 7, 'default_due_day': 31, 'tags': 'quarterly,marketing', 'owner_role': 'CCO', 'suggested_evidence': 'Review memo with tie-out documentation.'},
    {'title': 'Quarterly marketing/performance substantiation tie-out (Q3)', 'description': 'Verify marketing materials and performance claims are substantiated.', 'frequency': 'QUARTERLY', 'quarter': 3, 'default_due_month': 10, 'default_due_day': 31, 'tags': 'quarterly,marketing', 'owner_role': 'CCO', 'suggested_evidence': 'Review memo with tie-out documentation.'},
    # ANNUAL
    {'title': 'CIMA: Pay annual fees', 'description': 'Pay annual CIMA (Cayman Islands Monetary Authority) registration fees.', 'frequency': 'ANNUAL', 'default_due_month': 1, 'default_due_day': 15, 'tags': 'annual,regulatory,cayman', 'owner_role': 'CCO', 'suggested_evidence': 'Receipt / registered office confirmation email.'},
    {'title': 'IARD/CRD: Renewal reconciliation (Final Statement / renewals cleanup)', 'description': 'Reconcile IARD/CRD renewals and review final statement.', 'frequency': 'ANNUAL', 'default_due_month': 1, 'default_due_day': 31, 'tags': 'annual,regulatory,iard', 'owner_role': 'CCO', 'suggested_evidence': 'IARD billing screenshot; payment confirmation.'},
    {'title': 'Annual review: Initiate annual compliance review workplan', 'description': 'Begin planning and documenting the annual compliance review.', 'frequency': 'ANNUAL', 'default_due_month': 1, 'default_due_day': 31, 'tags': 'annual,compliance-review', 'owner_role': 'CCO', 'suggested_evidence': 'Workplan doc upload/link.'},
    {'title': 'Form ADV: Annual update drafting (internal draft ready)', 'description': 'Prepare internal draft of Form ADV annual update.', 'frequency': 'ANNUAL', 'default_due_month': 2, 'default_due_day': 28, 'tags': 'annual,regulatory,adv', 'owner_role': 'CCO', 'suggested_evidence': 'Draft ADV parts / change log.'},
    {'title': 'Form ADV: File annual updating amendment (within 90 days of FYE)', 'description': 'File Form ADV annual updating amendment with the SEC via IARD.', 'frequency': 'ANNUAL', 'default_due_month': 3, 'default_due_day': 31, 'tags': 'annual,regulatory,adv,filing', 'owner_role': 'CCO', 'suggested_evidence': 'IARD confirmation; filed PDF.'},
    {'title': 'Brochure delivery: Deliver updated ADV brochure to clients (if material changes)', 'description': 'Deliver updated Form ADV Part 2A brochure to clients if there were material changes.', 'frequency': 'ANNUAL', 'default_due_month': 4, 'default_due_day': 30, 'tags': 'annual,regulatory,adv,client-communication', 'conditional_flag': 'has_material_brochure_changes', 'owner_role': 'CCO', 'suggested_evidence': 'Client email distribution proof / mailing log.'},
    {'title': 'Custody audit approach: Distribute audited fund financials to investors (if applicable)', 'description': 'Distribute audited financial statements to fund investors.', 'frequency': 'ANNUAL', 'default_due_month': 4, 'default_due_day': 30, 'tags': 'annual,custody,investor-communication', 'owner_role': 'Fund Admin', 'suggested_evidence': 'Audited financials PDF; investor distribution proof.'},
    {'title': 'CIMA: File audited financial statements + FAR (within 6 months of FYE)', 'description': 'File audited financial statements and Fund Annual Return with CIMA.', 'frequency': 'ANNUAL', 'default_due_month': 6, 'default_due_day': 30, 'tags': 'annual,regulatory,cayman,filing', 'owner_role': 'CCO', 'suggested_evidence': 'Submission confirmation + filed docs.'},
    {'title': 'Mid-year: Best execution & trade allocation review', 'description': 'Conduct mid-year review of best execution practices and trade allocation procedures.', 'frequency': 'ANNUAL', 'default_due_month': 6, 'default_due_day': 30, 'tags': 'annual,trading,review', 'owner_role': 'CCO', 'suggested_evidence': 'Review memo; committee notes.'},
    {'title': 'Annual: BCP drill + cybersecurity tabletop', 'description': 'Conduct business continuity plan drill and cybersecurity tabletop exercise.', 'frequency': 'ANNUAL', 'default_due_month': 6, 'default_due_day': 30, 'tags': 'annual,bcp,cybersecurity', 'owner_role': 'CCO', 'suggested_evidence': 'Drill results; attendee notes.', 'survey_template_slug': 'annual-cybersecurity-communications-attestation'},
    {'title': 'FATCA/CRS: Submit annual reporting (Cayman fund)', 'description': 'Submit FATCA and CRS annual reports for Cayman fund.', 'frequency': 'ANNUAL', 'default_due_month': 7, 'default_due_day': 31, 'tags': 'annual,regulatory,cayman,tax', 'owner_role': 'Fund Admin', 'suggested_evidence': 'Submission receipt; XML/portal confirmation.'},
    {'title': 'CRS Compliance Form: Submit (Cayman/DITC)', 'description': 'Submit CRS Compliance Form to Cayman DITC.', 'frequency': 'ANNUAL', 'default_due_month': 9, 'default_due_day': 15, 'tags': 'annual,regulatory,cayman,tax', 'owner_role': 'Fund Admin', 'suggested_evidence': 'Submission confirmation.'},
    {'title': 'IARD Renewal Program: Monitor bulletin and prepare renewal funding', 'description': 'Monitor IARD renewal bulletin and prepare funding for renewals.', 'frequency': 'ANNUAL', 'default_due_month': 11, 'default_due_day': 30, 'tags': 'annual,regulatory,iard', 'owner_role': 'CCO', 'suggested_evidence': 'Renewal calendar note + funding confirmation.'},
    {'title': 'IARD Renewal Program: Complete renewals during window', 'description': 'Complete all IARD renewals during the renewal window.', 'frequency': 'ANNUAL', 'default_due_month': 12, 'default_due_day': 31, 'tags': 'annual,regulatory,iard', 'owner_role': 'CCO', 'suggested_evidence': 'IARD filing confirmation / proof.'},
    # ANNUAL SURVEY-LINKED
    {'title': 'Annual holdings and accounts report', 'description': 'Collect annual holdings and accounts disclosures from access persons.', 'frequency': 'ANNUAL', 'default_due_month': 1, 'default_due_day': 31, 'tags': 'annual,code-of-ethics,access-person', 'owner_role': 'CCO', 'suggested_evidence': 'Completed survey responses; holdings attestation.', 'survey_template_slug': 'annual-holdings-and-accounts-report'},
    {'title': 'Annual Code of Ethics and Compliance Manual attestation', 'description': 'Annual attestation confirming receipt and understanding of Code of Ethics and Compliance Manual.', 'frequency': 'ANNUAL', 'default_due_month': 1, 'default_due_day': 31, 'tags': 'annual,code-of-ethics,attestation', 'owner_role': 'CCO', 'suggested_evidence': 'Completed attestation survey responses.', 'survey_template_slug': 'annual-code-of-ethics-and-compliance-manual-attestation'},
    {'title': 'Annual OBA / Conflicts / Political Contributions survey', 'description': 'Annual survey on outside business activities, conflicts of interest, and political contributions.', 'frequency': 'ANNUAL', 'default_due_month': 1, 'default_due_day': 31, 'tags': 'annual,oba,conflicts', 'owner_role': 'CCO', 'suggested_evidence': 'Completed survey responses; exception follow-ups.', 'survey_template_slug': 'annual-oba-conflicts-political-contributions-survey'},
    # ONE-TIME
    {'title': 'Reg S-P amendments: Compliance deadline (smaller entities)', 'description': 'Ensure compliance with Reg S-P amendments for smaller entities.', 'frequency': 'ONE_TIME', 'default_due_month': 6, 'default_due_day': 3, 'tags': 'one-time,regulatory,privacy', 'owner_role': 'CCO', 'suggested_evidence': 'Updated policies; incident response docs; vendor oversight.'},
    # CONDITIONAL
    {'title': 'Form 13F: Quarterly filing (Q4)', 'description': 'File Form 13F quarterly report for Q4 holdings.', 'frequency': 'QUARTERLY', 'quarter': 4, 'default_due_month': 2, 'default_due_day': 14, 'tags': 'quarterly,regulatory,13f,filing', 'conditional_flag': 'is_form_13f_applicable', 'owner_role': 'CCO', 'suggested_evidence': 'EDGAR submission confirmation.'},
    {'title': 'Form 13F: Quarterly filing (Q1)', 'description': 'File Form 13F quarterly report for Q1 holdings.', 'frequency': 'QUARTERLY', 'quarter': 1, 'default_due_month': 5, 'default_due_day': 15, 'tags': 'quarterly,regulatory,13f,filing', 'conditional_flag': 'is_form_13f_applicable', 'owner_role': 'CCO', 'suggested_evidence': 'EDGAR submission confirmation.'},
    {'title': 'Form 13F: Quarterly filing (Q2)', 'description': 'File Form 13F quarterly report for Q2 holdings.', 'frequency': 'QUARTERLY', 'quarter': 2, 'default_due_month': 8, 'default_due_day': 14, 'tags': 'quarterly,regulatory,13f,filing', 'conditional_flag': 'is_form_13f_applicable', 'owner_role': 'CCO', 'suggested_evidence': 'EDGAR submission confirmation.'},
    {'title': 'Form 13F: Quarterly filing (Q3)', 'description': 'File Form 13F quarterly report for Q3 holdings.', 'frequency': 'QUARTERLY', 'quarter': 3, 'default_due_month': 11, 'default_due_day': 14, 'tags': 'quarterly,regulatory,13f,filing', 'conditional_flag': 'is_form_13f_applicable', 'owner_role': 'CCO', 'suggested_evidence': 'EDGAR submission confirmation.'},
    {'title': 'Reg S-P: Annual privacy notice delivery', 'description': 'Deliver annual privacy notice to clients as required by Reg S-P.', 'frequency': 'ANNUAL', 'default_due_month': 3, 'default_due_day': 31, 'tags': 'annual,regulatory,privacy', 'conditional_flag': 'is_privacy_notice_annual_required', 'owner_role': 'CCO', 'suggested_evidence': 'Distribution proof.'},
    {'title': 'Form CRS: Review for material changes (event-driven; document quarterly/annual check)', 'description': 'Review Form CRS for any material changes that would require an update.', 'frequency': 'ANNUAL', 'default_due_month': 3, 'default_due_day': 31, 'tags': 'annual,regulatory,crs', 'conditional_flag': 'is_form_crs_applicable', 'owner_role': 'CCO', 'suggested_evidence': "Memo 'no material changes' or updated CRS."},
    {'title': 'Form PF: File (if required)', 'description': 'File Form PF if required based on AUM thresholds.', 'frequency': 'ANNUAL', 'default_due_month': 4, 'default_due_day': 30, 'tags': 'annual,regulatory,form-pf,filing', 'conditional_flag': 'is_form_pf_applicable', 'owner_role': 'CCO', 'suggested_evidence': 'Filing confirmation.'},
]


class Command(BaseCommand):
    help = 'Seed compliance task templates for an organization'

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

        created = 0
        skipped = 0
        for tpl_data in TEMPLATES:
            tpl_data = dict(tpl_data)  # copy so we can pop
            survey_slug = tpl_data.pop('survey_template_slug', None)
            title = tpl_data['title']
            obj, was_created = ComplianceTaskTemplate.objects.get_or_create(
                organization=org,
                title=title,
                defaults=tpl_data,
            )
            if was_created:
                created += 1
                self.stdout.write(f'  Created: {title}')
            else:
                skipped += 1

            # Link survey template if specified
            if survey_slug and not obj.survey_template:
                survey = SurveyTemplate.objects.filter(
                    organization=org, slug=survey_slug,
                ).first()
                if survey:
                    obj.survey_template = survey
                    obj.save(update_fields=['survey_template'])
                    self.stdout.write(f'    Linked to survey: {survey.name}')

        self.stdout.write(self.style.SUCCESS(
            f'Done. Created {created} templates, skipped {skipped} existing.'
        ))
