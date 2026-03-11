from apps.compliance.models import ComplianceAuditLog


def log_action(task, action_type, user, old_value=None, new_value=None, description=''):
    """Create an immutable audit log entry for a compliance task."""
    ComplianceAuditLog.objects.create(
        task=task,
        organization=task.organization,
        action_type=action_type,
        old_value=old_value,
        new_value=new_value,
        description=description,
        user=user,
    )
