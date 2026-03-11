from datetime import date, timedelta
from django.utils import timezone
from apps.compliance.models import (
    SurveyTemplate, SurveyVersion, SurveyAssignment, 
    EmployeeCertificationStatus, SurveyException
)
from apps.users.models import User

def get_audience_users(organization, audience_type):
    """Return a queryset of users matching the audience type for an organization."""
    qs = User.objects.filter(
        organization_memberships__organization=organization,
        organization_memberships__is_deleted=False
    ).distinct()

    if audience_type == SurveyTemplate.AudienceType.ACCESS_PERSONS:
        # We look for the EmployeeCertificationStatus flag
        return qs.filter(compliance_status__is_access_person=True)
    elif audience_type == SurveyTemplate.AudienceType.COVERED_ASSOCIATES:
        return qs.filter(compliance_status__is_covered_associate=True)
    elif audience_type == SurveyTemplate.AudienceType.CCO_ONLY:
        # Assuming admin/cco roles in membership
        return qs.filter(organization_memberships__role='admin')
    elif audience_type == SurveyTemplate.AudienceType.ALL_SUPERVISED:
        return qs
    
    return qs.none()

def assign_periodic_surveys(organization, year, quarter=None):
    """Assign periodic (Annual/Quarterly) surveys to appropriate users."""
    templates = SurveyTemplate.objects.filter(
        organization=organization,
        is_active=True
    )

    created_count = 0
    skipped_count = 0

    for template in templates:
        # Determine if template matches the period
        if template.cadence == SurveyTemplate.Cadence.QUARTERLY and quarter is None:
            continue
        if template.cadence == SurveyTemplate.Cadence.ANNUAL and quarter is not None:
            # Annual surveys usually assigned at year end or year start
            # For this logic, we'll assign annuals if quarter is None
            continue
        
        # We need the latest published version
        version = template.versions.filter(is_published=True).order_by('-version_number').first()
        if not version:
            continue

        users = get_audience_users(organization, template.audience_type)
        
        # Default due date: 30 days from now
        due_date = date.today() + timedelta(days=30)

        for user in users:
            # Check for existing assignment
            exists = SurveyAssignment.objects.filter(
                version=version,
                user=user,
                year=year,
                quarter=quarter
            ).exists()

            if not exists:
                SurveyAssignment.objects.create(
                    organization=organization,
                    version=version,
                    user=user,
                    year=year,
                    quarter=quarter,
                    due_date=due_date
                )
                created_count += 1
            else:
                skipped_count += 1
    
    return created_count, skipped_count

def process_survey_submission(assignment, response_data, user, files=None):
    """Process a survey submission, creating response, answers, and exceptions."""
    from apps.compliance.models import SurveyResponse, SurveyAnswer, SurveyEvidenceUpload
    import json

    # 1. Create Response
    response = SurveyResponse.objects.create(
        organization=assignment.organization,
        assignment=assignment,
        attested_name=response_data.get('attested_name', user.get_full_name()),
        certification_text_snapshot=assignment.version.attestation_text,
        # In a real view, we'd pass IP and User Agent
    )

    # 2. Iterate Questions and save Answers
    for question in assignment.version.questions.all():
        value = response_data.get(f'q_{question.pk}')
        if value is None:
            continue
        
        is_exception = False
        exc_summary = ""

        # Trigger logic
        if question.exception_trigger_rules:
            rules = question.exception_trigger_rules
            trigger_val = rules.get('trigger_on')
            if str(value).lower() == str(trigger_val).lower():
                is_exception = True
                severity = rules.get('severity', 'WARNING')
                exc_summary = f"Triggered by {question.question_key}"
                
                # Create the exception record
                SurveyException.objects.create(
                    organization=assignment.organization,
                    assignment=assignment,
                    response=response,
                    severity=severity,
                    category=SurveyException.Category.OTHER, # We could map this better
                    summary=f"Exception in {assignment.version.template.name}",
                    details=f"User answered '{value}' to: {question.prompt}"
                )

        answer = SurveyAnswer.objects.create(
            response=response,
            question=question,
            value_json=value,
            is_exception_flag=is_exception,
            exception_summary=exc_summary
        )

        # Handle files if this is a file field
        if question.field_type == 'FILE' and files:
            file_obj = files.get(f'q_{question.pk}')
            if file_obj:
                SurveyEvidenceUpload.objects.create(
                    organization=assignment.organization,
                    response=response,
                    answer=answer,
                    file=file_obj,
                    original_filename=file_obj.name,
                    uploaded_by=user
                )

    # 3. Update Assignment
    assignment.status = SurveyAssignment.Status.SUBMITTED
    assignment.submitted_at = timezone.now()
    assignment.save()

    return response
