"""
Views for Organization management.
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView, ListView, View

from .models import Organization, OrganizationMembership
from .forms import OrganizationForm


class OrganizationCreateView(LoginRequiredMixin, CreateView):
    """Create a new organization."""
    model = Organization
    form_class = OrganizationForm
    template_name = 'organizations/organization_form.html'
    success_url = reverse_lazy('dashboard')

    def form_valid(self, form):
        # Save organization
        form.instance.created_by = self.request.user
        response = super().form_valid(form)

        # Add creator as owner
        OrganizationMembership.objects.create(
            organization=self.object,
            user=self.request.user,
            role=OrganizationMembership.Role.OWNER,
            is_default=True,
            created_by=self.request.user
        )

        # Set as current organization
        self.request.session['organization_id'] = self.object.id

        messages.success(self.request, f'Organization "{self.object.name}" created successfully.')
        return response


class OrganizationUpdateView(LoginRequiredMixin, UpdateView):
    """Update organization settings."""
    model = Organization
    form_class = OrganizationForm
    template_name = 'organizations/organization_form.html'
    success_url = reverse_lazy('organizations:settings')

    def get_queryset(self):
        # Only allow admins/owners to edit
        return Organization.objects.filter(
            memberships__user=self.request.user,
            memberships__role__in=[OrganizationMembership.Role.OWNER, OrganizationMembership.Role.ADMIN],
            memberships__is_deleted=False
        )

    def get_object(self, queryset=None):
        # Use current organization
        return self.request.organization

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, 'Organization settings updated.')
        return super().form_valid(form)


class OrganizationSwitchView(LoginRequiredMixin, View):
    """Switch to a different organization."""

    def post(self, request, pk):
        # Verify user has access to this organization
        membership = get_object_or_404(
            OrganizationMembership,
            organization_id=pk,
            user=request.user,
            is_deleted=False,
            organization__is_deleted=False
        )

        # Update session
        request.session['organization_id'] = pk

        messages.success(request, f'Switched to {membership.organization.name}')

        # Redirect to where they came from, or dashboard
        next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or '/'
        return redirect(next_url)


class OrganizationMembersView(LoginRequiredMixin, ListView):
    """List organization members."""
    model = OrganizationMembership
    template_name = 'organizations/members.html'
    context_object_name = 'members'

    def get_queryset(self):
        if not self.request.organization:
            return OrganizationMembership.objects.none()
        return OrganizationMembership.objects.filter(
            organization=self.request.organization,
            is_deleted=False
        ).select_related('user').order_by('user__email')
