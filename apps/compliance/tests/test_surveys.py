from django.test import TestCase
from django.utils import timezone
from apps.organizations.models import Organization
from apps.users.models import User
from apps.compliance.models import (
    SurveyTemplate, SurveyVersion, SurveyQuestion, 
    SurveyAssignment, SurveyResponse, SurveyException,
    EmployeeCertificationStatus
)
from apps.compliance.services.surveys import (
    assign_periodic_surveys, process_survey_submission
)
from apps.compliance.management.commands.seed_compliance_surveys import Command as SeedCommand

class SurveySystemTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test RIA", slug="test-ria")
        self.user = User.objects.create(email="employee@test.com")
        self.org.add_member(self.user, role='member')
        
        # Create certification status
        EmployeeCertificationStatus.objects.create(
            organization=self.org,
            user=self.user,
            is_access_person=True
        )

    def test_seeding(self):
        """Test that the seed command creates templates and versions."""
        cmd = SeedCommand()
        cmd.handle()
        
        self.assertTrue(SurveyTemplate.objects.filter(slug='annual-holdings-and-accounts-report').exists())
        template = SurveyTemplate.objects.get(slug='annual-holdings-and-accounts-report')
        version = template.versions.first()
        self.assertIsNotNone(version)
        self.assertTrue(version.questions.exists())

    def test_assignment_logic(self):
        """Test that surveys are correctly assigned based on audience."""
        # Seed first
        SeedCommand().handle()
        
        # Assign annual surveys for 2026
        created, skipped = assign_periodic_surveys(self.org, 2026)
        
        # Should assign Annual Holdings (access person) and Code of Ethics (all supervised)
        # etc.
        self.assertGreater(created, 0)
        
        # Verify assignment
        assignment = SurveyAssignment.objects.filter(user=self.user, year=2026).first()
        self.assertIsNotNone(assignment)
        self.assertEqual(assignment.status, SurveyAssignment.Status.NOT_STARTED)

    def test_submission_and_exception(self):
        """Test that submitting a 'Yes' to a flagged question creates an exception."""
        template = SurveyTemplate.objects.create(
            organization=self.org, name="Test Survey", slug="test", cadence='ANNUAL'
        )
        version = SurveyVersion.objects.create(
            organization=self.org, template=template, version_number=1, is_published=True
        )
        question = SurveyQuestion.objects.create(
            version=version, question_key="violation", prompt="Any violations?",
            field_type='YES_NO', exception_trigger_rules={'trigger_on': 'true', 'severity': 'CRITICAL'}
        )
        
        assignment = SurveyAssignment.objects.create(
            organization=self.org, version=version, user=self.user, 
            year=2026, due_date=timezone.now().date()
        )
        
        # Submit with "true" (Yes)
        data = {
            f'q_{question.pk}': True,
            'attested_name': 'Test User',
            'attestation_consent': True
        }
        
        process_survey_submission(assignment, data, self.user)
        
        # Verify submission
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, SurveyAssignment.Status.SUBMITTED)
        
        # Verify exception creation
        self.assertTrue(SurveyException.objects.filter(assignment=assignment).exists())
        exc = SurveyException.objects.get(assignment=assignment)
        self.assertEqual(exc.severity, 'CRITICAL')
        self.assertIn("Any violations?", exc.details)
