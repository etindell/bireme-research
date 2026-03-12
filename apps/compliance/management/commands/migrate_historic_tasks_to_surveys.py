from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.compliance.models import (
    ComplianceTask, SurveyTemplate, SurveyVersion, 
    SurveyAssignment, SurveyResponse, SurveyAnswer, 
    SurveyEvidenceUpload
)

class Command(BaseCommand):
    help = 'Migrate historic compliance tasks to the new survey system'

    def handle(self, *args, **options):
        # Mapping of Task Title fragments to Survey Template slugs
        MAPPING = {
            'Personal Securities Transactions': 'quarterly-access-person-certification',
            'Quarterly Access Person': 'quarterly-access-person-certification',
            'Code of Ethics': 'annual-code-of-ethics-and-compliance-manual-attestation',
            'Compliance Manual': 'annual-code-of-ethics-and-compliance-manual-attestation',
            'Holdings': 'annual-holdings-and-accounts-report',
            'Outside Business': 'annual-oba-conflicts-political-contributions-survey',
            'Political Contributions': 'annual-oba-conflicts-political-contributions-survey',
            'Cybersecurity': 'annual-cybersecurity-communications-attestation',
        }

        tasks = ComplianceTask.objects.filter(
            status=ComplianceTask.Status.COMPLETED,
            migrated_to_survey__isnull=True
        ).select_related('completed_by', 'organization')

        migrated_count = 0

        for task in tasks:
            template_slug = None
            for fragment, slug in MAPPING.items():
                if fragment.lower() in task.title.lower():
                    template_slug = slug
                    break
            
            if not template_slug:
                continue

            template = SurveyTemplate.objects.filter(
                organization=task.organization,
                slug=template_slug
            ).first()

            if not template:
                self.stdout.write(f"Template not found for slug: {template_slug}")
                continue

            version = template.versions.filter(is_published=True).order_by('-version_number').first()
            if not version:
                continue

            # Create Assignment
            assignment, created = SurveyAssignment.objects.get_or_create(
                organization=task.organization,
                version=version,
                user=task.completed_by,
                year=task.year,
                quarter=task.template.quarter if task.template else None,
                defaults={
                    'due_date': task.due_date,
                    'status': SurveyAssignment.Status.APPROVED,
                    'submitted_at': task.completed_at,
                    'reviewed_at': task.completed_at,
                    'reviewed_by': task.completed_by, # Self-reviewed for history
                }
            )

            if created:
                # Create Response
                response = SurveyResponse.objects.create(
                    organization=task.organization,
                    assignment=assignment,
                    attested_name=task.completed_by.get_full_name() or task.completed_by.email,
                    attested_at=task.completed_at or timezone.now(),
                    certification_text_snapshot=version.attestation_text,
                    description=f"Migrated from Task ID {task.id}: {task.title}"
                )

                # Migrate Evidence
                for evidence in task.evidence_items.all():
                    SurveyEvidenceUpload.objects.create(
                        organization=task.organization,
                        response=response,
                        file=evidence.file,
                        original_filename=evidence.original_filename,
                        uploaded_by=evidence.uploaded_by or task.completed_by,
                        description=evidence.description or f"Migrated from task evidence"
                    )

                # Mark task as migrated
                task.migrated_to_survey = assignment
                task.save()
                migrated_count += 1

        self.stdout.write(self.style.SUCCESS(f"Successfully migrated {migrated_count} tasks to surveys."))
