"""
View and model mixins for Bireme Research platform.
"""
from django.db import models
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied


class OrganizationMixin(models.Model):
    """
    Model mixin for organization-scoped models.

    All models that need to be scoped to an organization should
    inherit from this mixin.
    """
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.CASCADE,
        related_name='%(app_label)s_%(class)ss'
    )

    class Meta:
        abstract = True


class OrganizationQuerySetMixin:
    """
    QuerySet mixin to filter by organization.

    Use this in custom QuerySet classes to add organization filtering.
    """
    def for_organization(self, organization):
        """Filter queryset to only include records for the given organization."""
        return self.filter(organization=organization)


class OrganizationViewMixin(LoginRequiredMixin):
    """
    View mixin that:
    1. Requires login
    2. Filters queryset by current organization
    3. Auto-sets organization and created_by on form save
    """

    def get_queryset(self):
        """Filter queryset to current organization."""
        qs = super().get_queryset()
        if hasattr(self.request, 'organization') and self.request.organization:
            return qs.filter(organization=self.request.organization)
        return qs.none()

    def form_valid(self, form):
        """Auto-set organization and created_by on save."""
        if not form.instance.pk:
            # New object
            form.instance.organization = self.request.organization
            form.instance.created_by = self.request.user
        else:
            # Existing object
            form.instance.updated_by = self.request.user
        return super().form_valid(form)

    def get_form_kwargs(self):
        """Pass organization to form if it accepts it."""
        kwargs = super().get_form_kwargs()
        if hasattr(self, 'request') and hasattr(self.request, 'organization'):
            kwargs['organization'] = self.request.organization
        return kwargs


class MembershipRequiredMixin:
    """
    View mixin that requires user to have a specific role in the organization.

    Usage:
        class MyView(MembershipRequiredMixin, View):
            required_roles = ['admin', 'owner']
    """
    required_roles = []  # Override in subclass

    def dispatch(self, request, *args, **kwargs):
        if not hasattr(request, 'membership') or not request.membership:
            raise PermissionDenied('No organization membership')

        if self.required_roles and request.membership.role not in self.required_roles:
            raise PermissionDenied('Insufficient permissions')

        return super().dispatch(request, *args, **kwargs)
