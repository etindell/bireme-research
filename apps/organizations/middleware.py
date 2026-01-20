"""
Organization middleware for multi-tenancy.

This middleware injects the current organization into every request,
making it available as request.organization throughout the application.
"""
from django.shortcuts import redirect
from django.urls import reverse

from .models import OrganizationMembership


class OrganizationMiddleware:
    """
    Middleware to inject current organization into request.

    Organization is determined by:
    1. Session-stored organization_id (if user switched orgs)
    2. User's default organization
    3. User's first organization (fallback)

    If user has no organization, they are redirected to create one.
    """

    # URLs that don't require an organization
    EXEMPT_URLS = [
        '/accounts/',
        '/admin/',
        '/__reload__/',
        '/organizations/create/',
        '/organizations/join/',
        '/share/',
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.organization = None
        request.membership = None

        # Skip for anonymous users
        if not request.user.is_authenticated:
            return self.get_response(request)

        # Skip for exempt URLs
        for exempt in self.EXEMPT_URLS:
            if request.path.startswith(exempt):
                return self.get_response(request)

        # Try to get organization from session
        org_id = request.session.get('organization_id')

        if org_id:
            try:
                membership = OrganizationMembership.objects.select_related(
                    'organization'
                ).get(
                    user=request.user,
                    organization_id=org_id,
                    is_deleted=False,
                    organization__is_deleted=False
                )
                request.organization = membership.organization
                request.membership = membership
            except OrganizationMembership.DoesNotExist:
                # Invalid org in session, clear it
                del request.session['organization_id']

        # If no organization yet, try to get default or first
        if not request.organization:
            membership = OrganizationMembership.objects.select_related(
                'organization'
            ).filter(
                user=request.user,
                is_deleted=False,
                organization__is_deleted=False
            ).order_by('-is_default', 'organization__name').first()

            if membership:
                request.organization = membership.organization
                request.membership = membership
                request.session['organization_id'] = membership.organization_id
            else:
                # No organization - redirect to create one
                create_url = reverse('organizations:create')
                if request.path != create_url:
                    return redirect(create_url)

        return self.get_response(request)
