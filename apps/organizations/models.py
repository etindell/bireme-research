"""
Organization models for multi-tenancy.

All data in the application is scoped to an organization.
Users can belong to multiple organizations with different roles.
"""
from django.db import models
from django.conf import settings
from django.utils.text import slugify

from core.models import SoftDeleteModel


class Organization(SoftDeleteModel):
    """
    Top-level tenant model. All data is scoped to an organization.
    """
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, max_length=100)
    description = models.TextField(blank=True)

    # Organization settings stored as JSON
    settings = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'organizations'
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
            # Ensure uniqueness
            original_slug = self.slug
            counter = 1
            while Organization.all_objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f'{original_slug}-{counter}'
                counter += 1
        super().save(*args, **kwargs)

    # Quarterly todo settings defaults
    DEFAULT_QUARTERLY_SETTINGS = {
        'enabled': True,
        'statuses': ['book', 'on_deck'],  # Which company statuses to create todos for
        'investor_letter_enabled': True,
        'days_after_quarter': 21,  # Days after quarter end to generate
    }

    def get_quarterly_settings(self):
        """Get quarterly todo generation settings with defaults."""
        defaults = self.DEFAULT_QUARTERLY_SETTINGS.copy()
        saved = self.settings.get('quarterly_todos', {})
        defaults.update(saved)
        return defaults

    def set_quarterly_settings(self, **kwargs):
        """Update quarterly todo settings."""
        current = self.get_quarterly_settings()
        current.update(kwargs)
        if 'quarterly_todos' not in self.settings:
            self.settings['quarterly_todos'] = {}
        self.settings['quarterly_todos'] = current
        self.save(update_fields=['settings', 'updated_at'])

    def get_news_preference_profile(self):
        """Get the AI-generated news preference profile text."""
        return self.settings.get('news_preference_profile', '')

    def set_news_preference_profile(self, profile_text):
        """Save an AI-generated news preference profile."""
        self.settings['news_preference_profile'] = profile_text
        self.save(update_fields=['settings', 'updated_at'])

    def get_members(self):
        """Return all active members of this organization."""
        return self.memberships.filter(is_deleted=False).select_related('user')

    def get_member_count(self):
        """Return count of active members."""
        return self.memberships.filter(is_deleted=False).count()

    def add_member(self, user, role='member', is_default=False, created_by=None):
        """
        Add a user to this organization.

        Args:
            user: User to add
            role: Role to assign (owner, admin, member, viewer)
            is_default: Whether this should be the user's default organization
            created_by: User performing the action
        """
        membership, created = OrganizationMembership.objects.get_or_create(
            organization=self,
            user=user,
            defaults={
                'role': role,
                'is_default': is_default,
                'created_by': created_by,
            }
        )

        if not created and membership.is_deleted:
            # Restore soft-deleted membership
            membership.restore(user=created_by)
            membership.role = role
            membership.save(update_fields=['role'])

        return membership


class OrganizationMembership(SoftDeleteModel):
    """
    Links users to organizations with role-based access.
    """
    class Role(models.TextChoices):
        OWNER = 'owner', 'Owner'
        ADMIN = 'admin', 'Admin'
        MEMBER = 'member', 'Member'
        VIEWER = 'viewer', 'Viewer'

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='memberships'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='organization_memberships'
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.MEMBER
    )
    is_default = models.BooleanField(
        default=False,
        help_text='Default organization for this user'
    )

    class Meta:
        db_table = 'organization_memberships'
        unique_together = ['organization', 'user']
        ordering = ['-is_default', 'organization__name']

    def __str__(self):
        return f'{self.user.email} - {self.organization.name} ({self.role})'

    def save(self, *args, **kwargs):
        # Ensure only one default per user
        if self.is_default:
            OrganizationMembership.objects.filter(
                user=self.user,
                is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)

    @property
    def is_owner(self):
        return self.role == self.Role.OWNER

    @property
    def is_admin(self):
        return self.role in [self.Role.OWNER, self.Role.ADMIN]

    @property
    def can_edit(self):
        return self.role in [self.Role.OWNER, self.Role.ADMIN, self.Role.MEMBER]

    @property
    def can_view(self):
        return True  # All roles can view


class OrganizationInvite(SoftDeleteModel):
    """
    Pending invitation for users who don't have an account yet.
    When the user signs up with this email, they'll be added to the organization.
    """
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='invites'
    )
    email = models.EmailField()
    role = models.CharField(
        max_length=20,
        choices=OrganizationMembership.Role.choices,
        default=OrganizationMembership.Role.MEMBER
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='sent_invites'
    )
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'organization_invites'
        unique_together = ['organization', 'email']
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.email} invited to {self.organization.name}'

    @property
    def is_pending(self):
        return self.accepted_at is None and not self.is_deleted
