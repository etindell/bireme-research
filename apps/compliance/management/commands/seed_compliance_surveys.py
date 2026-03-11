from django.core.management.base import BaseCommand
from django.utils.text import slugify
from apps.organizations.models import Organization
from apps.compliance.models import SurveyTemplate, SurveyVersion, SurveyQuestion


class Command(BaseCommand):
    help = 'Seed built-in compliance survey templates and versions'

    def handle(self, *args, **options):
        # We'll seed for the first organization found or a default if none
        org = Organization.objects.first()
        if not org:
            self.stdout.write(self.style.WARNING("No organization found. Please create one first."))
            return

        templates_to_seed = [
            {
                'name': 'Quarterly Access Person Certification',
                'cadence': SurveyTemplate.Cadence.QUARTERLY,
                'audience': SurveyTemplate.AudienceType.ACCESS_PERSONS,
                'questions': [
                    ('any_reportable_transactions', 'Any reportable securities transactions this quarter?', SurveyQuestion.FieldType.YES_NO, True),
                    ('upload_statements', 'Please upload statements or enter transactions if yes.', SurveyQuestion.FieldType.FILE, False),
                    ('new_accounts', 'Any new brokerage / crypto / custodial accounts opened?', SurveyQuestion.FieldType.YES_NO, True),
                    ('ipo_private_placement', 'Any IPO or private placement purchases?', SurveyQuestion.FieldType.YES_NO, True),
                    ('pre_approval_obtained', 'If yes to above, was pre-approval obtained?', SurveyQuestion.FieldType.YES_NO, False),
                    ('restricted_list_trades', 'Any restricted list trades?', SurveyQuestion.FieldType.YES_NO, True),
                    ('trade_errors', 'Any trade errors to report?', SurveyQuestion.FieldType.YES_NO, True),
                    ('client_complaints', 'Any client complaints received?', SurveyQuestion.FieldType.YES_NO, True),
                    ('compliance_violations', 'Any suspected compliance violations?', SurveyQuestion.FieldType.YES_NO, True),
                    ('gifts_entertainment', 'Any gifts/entertainment above policy threshold?', SurveyQuestion.FieldType.YES_NO, True),
                    ('unapproved_comms', 'Any use of unapproved communication channels for business?', SurveyQuestion.FieldType.YES_NO, True),
                ]
            },
            {
                'name': 'Annual Holdings and Accounts Report',
                'cadence': SurveyTemplate.Cadence.ANNUAL,
                'audience': SurveyTemplate.AudienceType.ACCESS_PERSONS,
                'questions': [
                    ('holdings_list', 'List all reportable securities holdings as of year-end (or upload statement).', SurveyQuestion.FieldType.FILE, True),
                    ('accounts_list', 'List all brokerage / custodial / crypto accounts.', SurveyQuestion.FieldType.LONG_TEXT, True),
                    ('undisclosed_beneficial_ownership', 'Any undisclosed beneficial ownership accounts?', SurveyQuestion.FieldType.YES_NO, True),
                ]
            },
            {
                'name': 'Annual Code of Ethics and Compliance Manual Attestation',
                'cadence': SurveyTemplate.Cadence.ANNUAL,
                'audience': SurveyTemplate.AudienceType.ALL_SUPERVISED,
                'questions': [
                    ('received_coe', 'I received the current Code of Ethics.', SurveyQuestion.FieldType.YES_NO, True),
                    ('received_manual', 'I received the current Compliance Manual.', SurveyQuestion.FieldType.YES_NO, True),
                    ('read_both', 'I have read both documents.', SurveyQuestion.FieldType.YES_NO, True),
                    ('understand_obligations', 'I understand my obligations under these policies.', SurveyQuestion.FieldType.YES_NO, True),
                    ('complied_during_year', 'I complied with all requirements during the year except as disclosed below.', SurveyQuestion.FieldType.YES_NO, True),
                    ('exceptions_disclosure', 'Disclose any exceptions or violations here.', SurveyQuestion.FieldType.LONG_TEXT, False),
                ]
            },
            {
                'name': 'Annual OBA / Conflicts / Political Contributions Survey',
                'cadence': SurveyTemplate.Cadence.ANNUAL,
                'audience': SurveyTemplate.AudienceType.ALL_SUPERVISED,
                'questions': [
                    ('any_oba', 'Any outside business activities (OBA)?', SurveyQuestion.FieldType.YES_NO, True),
                    ('oba_details', 'List any board seats / consulting / side businesses.', SurveyQuestion.FieldType.LONG_TEXT, False),
                    ('referral_arrangements', 'Any referral / compensation arrangements?', SurveyQuestion.FieldType.YES_NO, True),
                    ('conflicts_disclosure', 'Any conflicts involving vendors / issuers / clients / prospects?', SurveyQuestion.FieldType.YES_NO, True),
                    ('political_contributions', 'Any political contributions to covered officials/candidates?', SurveyQuestion.FieldType.YES_NO, True),
                    ('fundraising_solicitation', 'Any fundraising/solicitation for such officials?', SurveyQuestion.FieldType.YES_NO, True),
                ]
            },
            {
                'name': 'Annual Cybersecurity / Communications Attestation',
                'cadence': SurveyTemplate.Cadence.ANNUAL,
                'audience': SurveyTemplate.AudienceType.ALL_SUPERVISED,
                'questions': [
                    ('mfa_enabled', 'MFA enabled on all required systems.', SurveyQuestion.FieldType.YES_NO, True),
                    ('approved_devices', 'Only approved devices/accounts used for business.', SurveyQuestion.FieldType.YES_NO, True),
                    ('no_off_channel', 'I did not use prohibited off-channel business communications.', SurveyQuestion.FieldType.YES_NO, True),
                    ('report_incidents', 'I have reported any suspected cybersecurity incidents.', SurveyQuestion.FieldType.YES_NO, True),
                    ('completed_training', 'I have completed annual cybersecurity training.', SurveyQuestion.FieldType.YES_NO, True),
                ]
            },
            {
                'name': 'Event-Driven Incident Report',
                'cadence': SurveyTemplate.Cadence.EVENT_DRIVEN,
                'audience': SurveyTemplate.AudienceType.SELECTED_USERS,
                'questions': [
                    ('category', 'Incident category', SurveyQuestion.FieldType.SINGLE_SELECT, True),
                    ('incident_date', 'Date of Incident', SurveyQuestion.FieldType.DATE, True),
                    ('description', 'Description of events', SurveyQuestion.FieldType.LONG_TEXT, True),
                    ('affected_clients', 'Affected clients/accounts if any', SurveyQuestion.FieldType.TEXT, False),
                    ('remediation', 'Immediate remediation taken', SurveyQuestion.FieldType.LONG_TEXT, True),
                    ('evidence', 'Evidence upload', SurveyQuestion.FieldType.FILE, False),
                    ('severity', 'Severity level', SurveyQuestion.FieldType.SINGLE_SELECT, True),
                ]
            }
        ]

        for t_data in templates_to_seed:
            template, created = SurveyTemplate.objects.get_or_create(
                organization=org,
                slug=slugify(t_data['name']),
                defaults={
                    'name': t_data['name'],
                    'cadence': t_data['cadence'],
                    'audience_type': t_data['audience'],
                }
            )

            if created:
                self.stdout.write(f"Created template: {template.name}")
            
            # Create Version 1
            version, v_created = SurveyVersion.objects.get_or_create(
                template=template,
                version_number=1,
                defaults={
                    'organization': org,
                    'is_published': True,
                    'instructions': f"Please complete this {template.get_cadence_display()} survey accurately.",
                }
            )

            if v_created:
                self.stdout.write(f"  Created Version 1 for {template.name}")
                
                # Create Questions
                for i, (key, prompt, ftype, req) in enumerate(t_data['questions']):
                    # Simple rule: if YES_NO and key is in certain list, trigger exception
                    rules = None
                    if ftype == SurveyQuestion.FieldType.YES_NO and key in [
                        'trade_errors', 'client_complaints', 'compliance_violations', 
                        'unapproved_comms', 'political_contributions', 'any_reportable_transactions'
                    ]:
                        rules = {'trigger_on': 'true', 'severity': 'WARNING'}
                        if key == 'compliance_violations':
                            rules['severity'] = 'CRITICAL'

                    SurveyQuestion.objects.create(
                        version=version,
                        question_key=key,
                        prompt=prompt,
                        field_type=ftype,
                        is_required=req,
                        sort_order=i * 10,
                        exception_trigger_rules=rules
                    )
        
        self.stdout.write(self.style.SUCCESS("Successfully seeded compliance surveys."))
