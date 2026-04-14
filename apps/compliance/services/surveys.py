from datetime import date, timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

from apps.compliance.models import (
    SurveyTemplate, SurveyVersion, SurveyAssignment, SurveyDistribution,
    EmployeeCertificationStatus, SurveyException, ComplianceTask,
)
from apps.compliance.services.audit import log_action
from apps.compliance.models import ComplianceAuditLog
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

    # 2. Build a lookup of all answers by question_key for conditional logic
    all_questions = list(assignment.version.questions.all())
    # First pass: collect all submitted values keyed by question_key
    answers_by_key = {}
    for q in all_questions:
        val = response_data.get(f'q_{q.pk}')
        if val is not None:
            answers_by_key[q.question_key] = str(val).lower()

    # 3. Iterate Questions and save Answers
    for question in all_questions:
        value = response_data.get(f'q_{question.pk}')

        # Check conditional logic — skip if parent condition not met
        if question.conditional_logic:
            show_if = question.conditional_logic.get('show_if', {})
            parent_key = show_if.get('question_key', '')
            required_val = str(show_if.get('equals', '')).lower()
            parent_answer = answers_by_key.get(parent_key, '')
            if parent_answer != required_val:
                # Condition not met — question was hidden, skip entirely
                continue

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
                category = rules.get('category', 'OTHER')
                exc_summary = f"Triggered by {question.question_key}"

                # Map category string to enum
                try:
                    cat_enum = SurveyException.Category(category)
                except ValueError:
                    cat_enum = SurveyException.Category.OTHER

                SurveyException.objects.create(
                    organization=assignment.organization,
                    assignment=assignment,
                    response=response,
                    severity=severity,
                    category=cat_enum,
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

    # 4. Check if all assignments in distribution are complete
    check_distribution_complete(assignment)

    return response


def send_survey(organization, version, user_ids, due_date, send_email_flag, sent_by,
                year=None, quarter=None, existing_task=None):
    """
    Create assignments for selected users, optionally email them,
    and create/link a ComplianceTask.
    """
    if existing_task:
        task = existing_task
        task.status = ComplianceTask.Status.IN_PROGRESS
        task.save(update_fields=['status', 'updated_at'])
        log_action(
            task, ComplianceAuditLog.ActionType.STATUS_CHANGE,
            sent_by,
            description=f"Survey distributed to {len(user_ids)} employee(s)",
        )
    else:
        task = ComplianceTask.objects.create(
            organization=organization,
            title=f"Survey: {version.template.name} (due {due_date})",
            description=f"Distributed to {len(user_ids)} employee(s).",
            year=due_date.year,
            month=due_date.month,
            due_date=due_date,
            status=ComplianceTask.Status.IN_PROGRESS,
            tags='survey',
        )
        log_action(
            task, ComplianceAuditLog.ActionType.TASK_CREATED,
            sent_by,
            description=f"Survey distributed to {len(user_ids)} employee(s)",
        )

    # Create distribution record
    distribution = SurveyDistribution.objects.create(
        organization=organization,
        version=version,
        compliance_task=task,
        sent_by=sent_by,
        email_sent=send_email_flag,
    )

    # Create assignments
    created = 0
    for uid in user_ids:
        _, was_created = SurveyAssignment.objects.get_or_create(
            organization=organization,
            version=version,
            user_id=uid,
            year=year,
            quarter=quarter,
            defaults={
                'distribution': distribution,
                'due_date': due_date,
            },
        )
        if was_created:
            created += 1

    # Send emails
    if send_email_flag and created > 0:
        _send_survey_emails(distribution)

    return distribution


def _send_survey_emails(distribution):
    site_url = getattr(settings, 'SITE_URL', '')
    for assignment in distribution.assignments.select_related('user'):
        link = f"{site_url}/compliance/surveys/respond/{assignment.token}/"
        subject = f"Action Required: {distribution.version.template.name}"
        body = (
            f"Hi {assignment.user.first_name or assignment.user.email},\n\n"
            f"You have been assigned a compliance survey: "
            f"{distribution.version.template.name}.\n\n"
            f"Due date: {assignment.due_date.strftime('%B %d, %Y')}\n\n"
            f"Please complete it using this link:\n{link}\n\n"
            f"Thank you."
        )
        send_mail(
            subject=subject,
            message=body,
            from_email=None,
            recipient_list=[assignment.user.email],
            fail_silently=True,
        )


def send_rejection_email(assignment):
    """Notify the employee that their survey submission was rejected."""
    site_url = getattr(settings, 'SITE_URL', '')
    link = f"{site_url}/compliance/surveys/respond/{assignment.token}/"
    reason_block = ''
    if assignment.rejection_reason:
        reason_block = (
            f"\nReason from reviewer:\n"
            f"{assignment.rejection_reason}\n"
        )
    body = (
        f"Hi {assignment.user.first_name or assignment.user.email},\n\n"
        f"Your submission for \"{assignment.version.template.name}\" has been "
        f"returned for revision by {assignment.reviewed_by.get_full_name()}.\n"
        f"{reason_block}\n"
        f"Please resubmit using this link:\n{link}\n\n"
        f"Due date: {assignment.due_date.strftime('%B %d, %Y')}\n\n"
        f"Thank you."
    )
    send_mail(
        subject=f"Action Required: {assignment.version.template.name} — Revision Needed",
        message=body,
        from_email=None,
        recipient_list=[assignment.user.email],
        fail_silently=True,
    )


def check_distribution_complete(assignment):
    """If all assignments in this distribution are done, mark the ComplianceTask complete."""
    dist = assignment.distribution
    if not dist or not dist.compliance_task:
        return

    terminal = [SurveyAssignment.Status.SUBMITTED, SurveyAssignment.Status.APPROVED,
                SurveyAssignment.Status.NOT_APPLICABLE]
    pending = dist.assignments.exclude(status__in=terminal).exists()

    if not pending:
        task = dist.compliance_task
        task.status = ComplianceTask.Status.COMPLETED
        task.completed_at = timezone.now()
        task.save(update_fields=['status', 'completed_at', 'updated_at'])
