"""
Context processors for organization data.

These make organization-related data available in all templates.
"""
from .models import OrganizationMembership


def organization(request):
    """
    Add organization and membership data to template context.

    Provides:
    - current_organization: The currently active organization
    - current_membership: User's membership in current organization
    - user_organizations: All organizations the user belongs to
    """
    context = {
        'current_organization': getattr(request, 'organization', None),
        'current_membership': getattr(request, 'membership', None),
        'user_organizations': [],
    }

    if request.user.is_authenticated:
        context['user_organizations'] = OrganizationMembership.objects.filter(
            user=request.user,
            is_deleted=False,
            organization__is_deleted=False
        ).select_related('organization').order_by('-is_default', 'organization__name')

    return context
