"""
Views for Organization management.
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView, ListView, View

from .models import Organization, OrganizationMembership, OrganizationInvite
from .forms import OrganizationForm, AddMemberForm


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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['add_member_form'] = AddMemberForm()
        # Add pending invites
        if self.request.organization:
            context['pending_invites'] = OrganizationInvite.objects.filter(
                organization=self.request.organization,
                is_deleted=False,
                accepted_at__isnull=True
            ).order_by('-created_at')
        return context


class AddMemberView(LoginRequiredMixin, View):
    """Add an existing user to the organization by email."""

    def post(self, request):
        # Check that user is admin of current organization
        if not request.organization:
            messages.error(request, 'No organization selected.')
            return redirect('organizations:members')

        membership = OrganizationMembership.objects.filter(
            organization=request.organization,
            user=request.user,
            is_deleted=False
        ).first()

        if not membership or not membership.is_admin:
            messages.error(request, 'You do not have permission to add members.')
            return redirect('organizations:members')

        form = AddMemberForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            role = form.cleaned_data['role']

            # Find user by email
            from apps.users.models import User
            user = User.objects.filter(email__iexact=email).first()

            if not user:
                # User doesn't exist - create an invite
                existing_invite = OrganizationInvite.objects.filter(
                    organization=request.organization,
                    email__iexact=email,
                    is_deleted=False,
                    accepted_at__isnull=True
                ).first()

                if existing_invite:
                    messages.warning(request, f'An invitation for {email} already exists.')
                    return redirect('organizations:members')

                OrganizationInvite.objects.create(
                    organization=request.organization,
                    email=email,
                    role=role,
                    invited_by=request.user,
                    created_by=request.user
                )
                messages.success(request, f'Invitation sent to {email}. They will be added when they sign up.')
                return redirect('organizations:members')

            # Check if already a member
            existing = OrganizationMembership.objects.filter(
                organization=request.organization,
                user=user,
                is_deleted=False
            ).first()

            if existing:
                messages.warning(request, f'{user.email} is already a member of this organization.')
                return redirect('organizations:members')

            # Add member
            request.organization.add_member(
                user=user,
                role=role,
                created_by=request.user
            )

            messages.success(request, f'{user.email} has been added as {role}.')
        else:
            messages.error(request, 'Invalid form submission.')

        return redirect('organizations:members')


class RemoveMemberView(LoginRequiredMixin, View):
    """Remove a member from the organization."""

    def post(self, request, pk):
        if not request.organization:
            messages.error(request, 'No organization selected.')
            return redirect('organizations:members')

        # Check that user is admin
        current_membership = OrganizationMembership.objects.filter(
            organization=request.organization,
            user=request.user,
            is_deleted=False
        ).first()

        if not current_membership or not current_membership.is_admin:
            messages.error(request, 'You do not have permission to remove members.')
            return redirect('organizations:members')

        # Get the membership to remove
        membership = get_object_or_404(
            OrganizationMembership,
            pk=pk,
            organization=request.organization,
            is_deleted=False
        )

        # Prevent removing yourself
        if membership.user == request.user:
            messages.error(request, 'You cannot remove yourself from the organization.')
            return redirect('organizations:members')

        # Prevent removing the last owner
        if membership.role == OrganizationMembership.Role.OWNER:
            owner_count = OrganizationMembership.objects.filter(
                organization=request.organization,
                role=OrganizationMembership.Role.OWNER,
                is_deleted=False
            ).count()
            if owner_count <= 1:
                messages.error(request, 'Cannot remove the last owner of the organization.')
                return redirect('organizations:members')

        # Soft delete the membership
        membership.delete(user=request.user)
        messages.success(request, f'{membership.user.email} has been removed from the organization.')

        return redirect('organizations:members')


class CancelInviteView(LoginRequiredMixin, View):
    """Cancel a pending invitation."""

    def post(self, request, pk):
        if not request.organization:
            messages.error(request, 'No organization selected.')
            return redirect('organizations:members')

        # Check that user is admin
        current_membership = OrganizationMembership.objects.filter(
            organization=request.organization,
            user=request.user,
            is_deleted=False
        ).first()

        if not current_membership or not current_membership.is_admin:
            messages.error(request, 'You do not have permission to cancel invitations.')
            return redirect('organizations:members')

        # Get the invite to cancel
        invite = get_object_or_404(
            OrganizationInvite,
            pk=pk,
            organization=request.organization,
            is_deleted=False,
            accepted_at__isnull=True
        )

        # Soft delete the invite
        invite.delete(user=request.user)
        messages.success(request, f'Invitation for {invite.email} has been cancelled.')

        return redirect('organizations:members')
